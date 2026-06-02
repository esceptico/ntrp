"""LensRegistry — the lens VIEW layer (file-backed CRUD + computed projection).

A lens is a VIEW, not memory: a named, criterion-defined projection over claims.
The DEFINITION lives as an editable markdown FILE at
``NTRP_DIR/memory/lenses/<slug>.md`` — this module owns the lifecycle (create /
list / edit-criterion / set-render-mode / delete / split / merge) over those files
(delegated through MemoryStore.lens_files). It NEVER writes to `memory_items` and
NEVER writes an edge. Creating or deleting a lens touches zero claims.

Membership is a COMPUTED PROJECTION: the criterion is run over candidate claims by
the LLM judge (LensMembership), cached in `lens_membership_cache`. The cache is not
graph truth — drop it and projection just recomputes. Criterion edits null the page
and invalidate the cache so membership re-derives on next read.

The absolute ban (§0) holds structurally: this module makes NO membership decision.
Every membership question is delegated to LensMembership (the LLM judge). No
keyword/regex/threshold gate decides anything here.
"""

from typing import Protocol

from ntrp.logging import get_logger
from ntrp.memory.lens.file_store import slugify
from ntrp.memory.models import (
    LensDetailLevel,
    LensProvenance,
    LensRenderMode,
    LensRow,
    Scope,
)
from ntrp.memory.pipeline.types import BackfillReport, CoverageAdvisory
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)


class _Membership(Protocol):
    """The slice of LensMembership the registry consults for advisory coverage.

    The registry never decides membership; coverage is a pure COUNT advisory the
    membership component computes. `refresh_lens_cache` is the lazy backfill the
    projector triggers — exposed here so split/merge can warm the cache.
    """

    async def coverage(self, lens_id: str, scope: Scope) -> CoverageAdvisory: ...

    async def refresh_lens_cache(self, lens_id: str) -> BackfillReport: ...

    async def synthesize_criterion(
        self, name: str, intent: str | None = ...
    ) -> tuple[str, str, str]: ...


class LensRegistry:
    def __init__(self, store: MemoryStore, membership: _Membership, projector=None):
        self.store = store
        self.membership = membership
        # The projector is the read surface the `lens` tool's `show` action uses
        # (registry CRUD + projected page behind one service slot). Set by runtime.
        self.projector = projector

    # --- create (touches zero claims) -------------------------------

    async def create_lens(
        self,
        name: str,
        criterion: str | None = None,
        scope: Scope | None = None,
        *,
        render_mode: LensRenderMode | None = None,
        detail_level: LensDetailLevel = LensDetailLevel.STRUCTURED,
        provenance: LensProvenance = LensProvenance.USER_AUTHORED,
        entity_type: str = "thing",
    ) -> LensRow:
        """Write one lens DEFINITION file. NO backfill, NO edges, NO claim writes (C7).

        When no criterion is given, the LLM synthesizes the body (## Belongs [+
        ## Profile shape]), the render mode AND the entity_type from the name (a
        pure text call — still touches zero claims, makes no membership decision).
        The page is None; membership/page are computed lazily on first projection.
        """
        if scope is None:
            raise ValueError("create_lens requires a scope")
        # A blank/whitespace name slugifies to the fallback "lens" and writes a file
        # with an empty directory that _parse_file rejects on read — a write-then-
        # can't-read silent disappearance. Reject categorically (covers all callers:
        # tool, REST router, split/merge).
        if not name or not name.strip():
            raise ValueError("lens name cannot be empty")
        if not (criterion or "").strip():
            # The synth drafts the criterion body and entity_type from the name.
            # render_mode is ALWAYS "flat" (membership.synthesize_criterion; no auto
            # subject-grouping); grouping is only ever a manual choice. Only adopt the
            # synth's mode when the caller did NOT pass one — else an explicit
            # render_mode (e.g. grouped_by_subject from the REST endpoint) is silently
            # discarded.
            criterion, synth_mode, entity_type = await self.membership.synthesize_criterion(name)
            if render_mode is None:
                render_mode = LensRenderMode(synth_mode)
        if render_mode is None:
            render_mode = LensRenderMode.FLAT
        lens = LensRow(
            id=self._unique_slug(name),
            name=name,
            criterion=criterion,
            scope=scope,
            entity_type=entity_type,
            render_mode=render_mode,
            detail_level=detail_level,
            provenance=provenance,
        )
        await self.store.create_lens_row(lens)
        _logger.info("lens created %s name=%r (file; zero claims touched)", lens.id, name)
        return lens

    def _unique_slug(self, name: str) -> str:
        """Derive a file slug from the name, suffixing on collision so two lenses
        with the same name get distinct files. The base is truncated to leave room
        for the `-{n}` suffix so the result never exceeds the 64-char slug limit —
        an over-length slug would fail _SLUG_RE and produce an unreadable file."""
        base = slugify(name)
        slug = base
        n = 2
        while self.store.lens_files.read(slug) is not None:
            suffix = f"-{n}"
            slug = f"{base[: 64 - len(suffix)]}{suffix}"
            n += 1
        return slug

    # --- render mode (presentation dial; no membership impact) ------

    async def set_render_mode(self, lens_id: str, render_mode: LensRenderMode) -> LensRow:
        """Flip a lens between flat and grouped-by-subject layout by editing the
        file's frontmatter. Membership is mode-independent (left cached), but the
        cached PAGE markdown is layout-specific — flat and grouped reconstruct it
        differently — so a mode change must null the page so the next read re-derives
        in the new format. Serving the old-format markdown through the new mode's path
        misrenders (e.g. a flat page becomes one bogus "Profile" group)."""
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            raise ValueError(f"not a lens: {lens_id}")
        if lens.render_mode == render_mode:
            return lens
        updated = await self.store.update_lens(lens_id, render_mode=render_mode, page=None)
        assert updated is not None
        return updated

    # --- list (with advisory coverage) ------------------------------

    async def list_lenses(self, scope: Scope) -> list[tuple[LensRow, CoverageAdvisory]]:
        lenses = await self.store.list_lenses(scope=scope)
        out: list[tuple[LensRow, CoverageAdvisory]] = []
        for lens in lenses:
            advisory = await self.membership.coverage(lens.id, lens.scope)
            out.append((lens, advisory))
        return out

    # --- edit criterion (re-derive at next read) --------------------

    async def edit_criterion(self, lens_id: str, new_criterion: str) -> LensRow:
        """Rewrite the criterion in place + invalidate the projection.

        UPDATE the registry row (criterion + page=NULL) and drop the membership
        cache. Membership re-derives on the next projection. Zero claim impact.
        """
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            raise ValueError(f"not a lens: {lens_id}")
        # Write the new criterion file FIRST, then invalidate last. Each await yields
        # the event loop; if we wiped the cache before the file write, a concurrent
        # projection could refresh_lens_cache against the OLD criterion file and
        # repopulate stale verdicts that survive. File-first + invalidate-last means
        # any refresh starting after the edit reads the new criterion, and the final
        # invalidate is the last write (mirrors delete_lens's durable ordering).
        updated = await self.store.update_lens(lens_id, criterion=new_criterion, page=None)
        assert updated is not None
        await self.store.invalidate_lens_membership(lens_id)
        return updated

    # --- delete (the view; never the claims) ------------------------

    async def delete_lens(self, lens_id: str) -> bool:
        """Drop the registry row + cache. Claims are untouched (C7)."""
        return await self.store.delete_lens(lens_id)

    # --- split / merge (pure registry ops + cache invalidation) -----

    async def split_lens(
        self,
        lens_id: str,
        into: list[tuple[str, str]],
        *,
        archive_parent: bool = True,
    ) -> list[LensRow]:
        """Split into narrower child views: create N registry rows, optionally
        delete the parent. Re-points nothing; membership re-derives per child."""
        parent = await self.store.get_lens(lens_id)
        if parent is None:
            raise ValueError(f"not a lens: {lens_id}")
        if not into:
            raise ValueError("split requires at least one child (name, criterion)")
        children: list[LensRow] = []
        for name, criterion in into:
            child = await self.create_lens(name, criterion, parent.scope)
            children.append(child)
        if archive_parent:
            await self.store.delete_lens(parent.id)
        return children

    async def merge_lenses(
        self, lens_ids: list[str], name: str, criterion: str
    ) -> LensRow:
        """Merge into one union view: create the union row, delete the inputs.
        Re-points nothing; the union re-derives its members from the criterion."""
        if len(lens_ids) < 2:
            raise ValueError("merge requires at least two lenses")
        inputs: list[LensRow] = []
        for lid in lens_ids:
            lens = await self.store.get_lens(lid)
            if lens is None:
                raise ValueError(f"not a lens: {lid}")
            inputs.append(lens)
        scope = inputs[0].scope
        # Recall/resolution is scope-isolated: a union inherits one scope, so it
        # could only ever surface inputs[0]'s scope — claims from a differently-
        # scoped input would be silently dropped while that source lens is deleted.
        # Refuse the lossy merge (categorical scope-equality, not a lexical gate).
        if not all(i.scope == scope for i in inputs):
            raise ValueError(
                f"cannot merge lenses across scopes: {sorted({str(i.scope) for i in inputs})}"
            )
        union = await self.create_lens(name, criterion, scope)
        for lens in inputs:
            await self.store.delete_lens(lens.id)
        return union
