"""Lens lifecycle / CRUD — LENS_CONTRACTS §3.4.

A lens is a materialized view over the knowledge graph (a `kind=LENS` row: name +
NL criterion + editable page + detail level). This component owns the lifecycle
verbs — create / list / edit_criterion / delete / split / merge — over the frozen
Stage-2 store. It is the topic/user-lens generalization of the entity-lens minting
reconcile already does inline (`_mint_subject`, reconcile.py:274); same store
calls, same add-only invariant, no fork.

The absolute ban (§0) is honored structurally: this module makes NO membership
decision. Every membership question is delegated to `LensMembership` (the LLM
judge) via `backfill_lens` / `coverage`. There is no word/keyword/prefix set, no
regex-for-meaning, and no cosine/length cutoff anywhere in this file. The coverage
ratio surfaced by `list_lenses` is the pure-COUNT advisory (§7) computed by
membership — a number, never a gate.

Store invariants (frozen, §1.1): no row delete, no edge delete. `delete_lens`
archives the view via `invalidate`; the lens's claims and `member_of` edges are
untouched and simply never read (reads filter to active lenses). `edit_criterion`
supersedes the lens row and marks it dirty so the next read re-validates members
against the new criterion (re-validate-at-read, §6) — no edge mutation at edit
time. `split`/`merge` re-derive membership via `backfill_lens`, never by
re-pointing edges (`_inherit_members` is claim->lens and is NOT reused here, §3.5).
"""

import uuid
from typing import Protocol

from ntrp.logging import get_logger
from ntrp.memory.models import (
    Kind,
    MemoryItem,
    Provenance,
    Scope,
    Status,
)
from ntrp.memory.pipeline.types import BackfillReport, CoverageAdvisory
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

# A criterion edit marks the lens dirty in the store's meta table (§6), mirroring
# consolidate's watermark pattern (consolidate.py:447-464). The next project /
# retrieval re-validates current members against the new criterion. Pure key/value
# bookkeeping — never a membership decision.
LENS_DIRTY_PREFIX = "lens_dirty"


class _Membership(Protocol):
    """The slice of `LensMembership` (§3.1) lifecycle delegates to.

    Lifecycle never decides membership; it asks the judge to re-derive a lens's
    members (`backfill_lens`) and reports the advisory coverage count
    (`coverage`). Typed as a Protocol so this component builds and tests in
    isolation against the frozen interface, ahead of the membership build.
    """

    async def backfill_lens(self, lens_id: str) -> BackfillReport: ...

    async def coverage(self, lens_id: str, scope: Scope) -> CoverageAdvisory: ...


class LensService:
    def __init__(self, store: MemoryStore, membership: _Membership, projector, writeback):
        self.store = store
        self.membership = membership
        self.projector = projector  # held for page reads; lifecycle never synthesizes
        self.writeback = writeback  # held for structured page edits; not a lifecycle verb

    # --- create ------------------------------------------------------

    async def create_lens(
        self,
        name: str,
        criterion: str,
        scope: Scope,
        *,
        lens_kind: str = "topic",
    ) -> MemoryItem:
        """Mint a topic/user lens, then backfill its members once (Mode 3, §3.6).

        Mirrors reconcile's entity mint (`_mint_subject`) with the two entity
        narrowings relaxed: the criterion is authored (not `f"about {subject}"`)
        and `lens_exclusive=False` (topic/user lenses are non-exclusive; entity
        is the constrained special case). Provenance is USER_AUTHORED — the user
        authored this view. The page is synthesized lazily on first `project`;
        creation never synthesizes.
        """
        lens = MemoryItem(
            id=uuid.uuid4().hex,
            kind=Kind.LENS,
            content=name,
            scope=scope,
            provenance=Provenance.USER_AUTHORED,
            lens_name=name,
            lens_criterion=criterion,
            lens_kind=lens_kind,
            lens_exclusive=False,
        )
        await self.store.create_item(lens)
        report = await self.membership.backfill_lens(lens.id)
        _logger.info(
            "lens created %s name=%r kind=%s backfilled=%d/%d capped=%s",
            lens.id,
            name,
            lens_kind,
            report.members_added,
            report.scanned,
            report.capped,
        )
        return lens

    # --- list --------------------------------------------------------

    async def list_lenses(
        self, scope: Scope
    ) -> list[tuple[MemoryItem, CoverageAdvisory]]:
        """Active lenses in scope, each with its advisory coverage ratio (§7).

        The advisory is a pure COUNT computed by membership; it is surfaced for
        split/narrow suggestions and never auto-acts.
        """
        lenses = await self.store.query(
            kind=Kind.LENS, scope=scope, status=Status.ACTIVE, limit=200
        )
        out: list[tuple[MemoryItem, CoverageAdvisory]] = []
        for lens in lenses:
            advisory = await self.membership.coverage(lens.id, scope)
            out.append((lens, advisory))
        return out

    # --- edit criterion (re-validate-at-read, §6) --------------------

    async def edit_criterion(self, lens_id: str, new_criterion: str) -> MemoryItem:
        """Rewrite the criterion: supersede the lens row, mark it dirty.

        No edge mutation at edit time (§1.1). The successor lens carries the new
        criterion and every other lens field forward (the `_append_alias`
        append-only pattern, reconcile.py:288-309). Membership re-derives at the
        next read — the projector re-scores current `member_of` members against
        the new criterion and renders only those still `in`; now-`out` edges
        dangle harmlessly (§6).
        """
        lens = await self.store.get(lens_id)
        if lens is None or lens.kind is not Kind.LENS:
            raise ValueError(f"not a lens: {lens_id}")
        if lens.status is not Status.ACTIVE:
            raise ValueError(f"lens not active: {lens_id}")
        successor = self._respin(lens, lens_criterion=new_criterion)
        await self.store.supersede(old_id=lens.id, new_item=successor)
        await self._mark_dirty(successor.id)
        return successor

    # --- delete (archive the view, never the claims, §3.4) -----------

    async def delete_lens(self, lens_id: str) -> bool:
        """Archive the view. Claims + `member_of` edges are untouched.

        The store has no claim-delete and no edge-delete path; `invalidate`
        moves the lens row off `active`. Orphaned `member_of` edges to the
        archived lens are simply never read (reads filter to active lenses).
        This is the spec's "delete the view, never the claims" invariant for free.
        """
        return await self.store.invalidate(lens_id, status=Status.ARCHIVED)

    # --- split (user-invoked off an advisory, §3.4 / §7) -------------

    async def split_lens(
        self,
        lens_id: str,
        into: list[tuple[str, str]],
        *,
        archive_parent: bool = True,
    ) -> list[MemoryItem]:
        """Split one (typically generic) lens into narrower children.

        Each child is created + backfilled against its own narrower criterion
        (the children re-derive their members from the claim pool, §1.1 / §3.4).
        The parent is optionally archived; its claims and edges are untouched and
        re-derive per child criterion at the children's reads. Never automatic —
        only invoked by the user off a coverage advisory (§7).
        """
        parent = await self.store.get(lens_id)
        if parent is None or parent.kind is not Kind.LENS:
            raise ValueError(f"not a lens: {lens_id}")
        if not into:
            raise ValueError("split requires at least one child (name, criterion)")
        children: list[MemoryItem] = []
        for name, criterion in into:
            child = await self.create_lens(
                name, criterion, parent.scope, lens_kind=parent.lens_kind or "topic"
            )
            children.append(child)
        if archive_parent:
            await self.store.invalidate(parent.id, status=Status.ARCHIVED)
        return children

    # --- merge (re-derive via backfill, NOT _inherit_members, §3.5) --

    async def merge_lenses(
        self, lens_ids: list[str], name: str, criterion: str
    ) -> MemoryItem:
        """Merge lenses into one union lens, then archive the inputs.

        The union lens is created and `backfill_lens`-ed against the merged
        criterion, so it re-derives its members from the claim pool (correct +
        consistent with §1.1). `_inherit_members` is claim->lens and is NOT
        reused to re-point a lens's members here (§3.5). Inputs are archived
        after the union exists; their claims + edges are untouched.
        """
        if len(lens_ids) < 2:
            raise ValueError("merge requires at least two lenses")
        inputs: list[MemoryItem] = []
        for lid in lens_ids:
            lens = await self.store.get(lid)
            if lens is None or lens.kind is not Kind.LENS:
                raise ValueError(f"not a lens: {lid}")
            inputs.append(lens)
        scope = inputs[0].scope
        lens_kind = inputs[0].lens_kind or "topic"
        union = await self.create_lens(name, criterion, scope, lens_kind=lens_kind)
        for lens in inputs:
            await self.store.invalidate(lens.id, status=Status.ARCHIVED)
        return union

    # --- internals ---------------------------------------------------

    def _respin(self, lens: MemoryItem, *, lens_criterion: str) -> MemoryItem:
        """A fresh lens row carrying every field forward except the new criterion.

        The append-only successor pattern (reconcile.py `_append_alias`): history
        stays walkable via the SUPERSEDES edge `supersede` mints.
        """
        return MemoryItem(
            id=uuid.uuid4().hex,
            kind=Kind.LENS,
            content=lens.content,
            scope=lens.scope,
            provenance=lens.provenance,
            valid_from=lens.valid_from,
            source_refs=lens.source_refs,
            corroboration=lens.corroboration,
            feedback=lens.feedback,
            lens_name=lens.lens_name,
            lens_criterion=lens_criterion,
            lens_kind=lens.lens_kind,
            lens_page=lens.lens_page,
            lens_detail_level=lens.lens_detail_level,
            lens_exclusive=lens.lens_exclusive,
        )

    def _dirty_key(self, lens_id: str) -> str:
        return f"{LENS_DIRTY_PREFIX}:{lens_id}"

    async def _mark_dirty(self, lens_id: str) -> None:
        """Watermark the lens dirty in the store's meta table (§6).

        Pure key/value bookkeeping mirroring consolidate's watermark
        (consolidate.py:458-464); no schema change, no membership decision.
        """
        await self.store.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._dirty_key(lens_id), lens_id),
        )
        await self.store.conn.commit()
