"""ConsolidateLint (§8): background forgetting, dedup, contradiction-flagging.

A periodic health-check of the ACTIVE claim layer. The only stage that removes
claims from circulation — and only ever via invalidate()/supersede(), never a
delete. Operates on kind=CLAIM only; never authors, splits, or touches lenses.

Per-scope, watermark-durable, demote-only. Candidate selection is O(delta),
never O(corpus): only claims updated since the last successful sweep plus each
delta claim's recall neighborhood. One cheap LLM call per neighborhood; the
strong model is reserved for genuinely contested merges. FTS down → neighborhoods
collapse to the delta claim alone and the report is marked degraded.

See pipeline/CONTRACTS.md §8.
"""

import json
from dataclasses import dataclass

from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    Status,
    now_iso,
)
from ntrp.memory.pipeline.prompts_consolidate import (
    LINT_RUBRIC,
    DropOrphanOp,
    InvalidateOp,
    LintOps,
    MergeOp,
)
from ntrp.memory.pipeline.types import LintReport
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)

MAX_ITEMS_PER_SWEEP = 200
NEIGHBORHOOD_LIMIT = 8
WATERMARK_PREFIX = "consolidate_watermark"

# Provenance trust ordinal, high → low. Used to pick a merge survivor and to cap
# the survivor's provenance at INFERRED (lint may never raise trust).
_PROVENANCE_ORDINAL = {
    Provenance.USER_AUTHORED: 3,
    Provenance.RECORDED: 2,
    Provenance.INFERRED: 1,
    Provenance.EXTERNAL: 0,
}


@dataclass
class ConsolidateConfig:
    consolidation_interval: int  # minutes between background sweeps
    max_items_per_sweep: int = MAX_ITEMS_PER_SWEEP
    neighborhood_limit: int = NEIGHBORHOOD_LIMIT


class ConsolidateLint:
    def __init__(
        self,
        store: MemoryStore,
        cheap_llm: CompletionClient,
        strong_llm: CompletionClient,
        *,
        model: str,
        config: ConsolidateConfig,
        eligible_scopes=None,
    ):
        self.store = store
        self.cheap_llm = cheap_llm
        self.strong_llm = strong_llm
        self.model = model
        self.config = config
        # Callable returning the scopes to sweep this tick. Injected so the loop
        # need not reach into other subsystems to enumerate active scopes.
        self._eligible_scopes = eligible_scopes or (lambda: [])

    # --- background loop --------------------------------------------------

    async def run_loop(self) -> None:
        import asyncio

        interval_s = max(1, self.config.consolidation_interval) * 60
        while True:
            try:
                for scope in self._eligible_scopes():
                    await self.run_once(scope=scope)
            except Exception:
                _logger.exception("consolidate sweep failed")
            await asyncio.sleep(interval_s)

    # --- one scoped sweep -------------------------------------------------

    async def run_once(self, *, scope: Scope) -> LintReport:
        sweep_start = now_iso()
        watermark = await self._read_watermark(scope)

        delta, capped, last_processed = await self._select_delta(scope, watermark)
        if not delta:
            await self._write_watermark(scope, sweep_start)
            return LintReport(scope, 0, 0, 0, 0, degraded=not self.store.has_fts)

        degraded = not self.store.has_fts
        neighborhoods = await self._build_neighborhoods(delta, scope, degraded)

        merged = invalidated = dropped = flagged = 0
        for hood in neighborhoods:
            ops = await self._judge(hood, scope)
            if ops is None:
                continue
            m, i, d, f = await self._apply(ops, hood, scope)
            merged += m
            invalidated += i
            dropped += d
            flagged += f

        # Durability: a full sweep advances the watermark to sweep_start; a capped
        # catch-up advances only to the last processed claim's updated_at, so the
        # unprocessed tail is not skipped on the next run.
        advance_to = last_processed if capped else sweep_start
        await self._write_watermark(scope, advance_to)

        return LintReport(scope, merged, invalidated, dropped, flagged, degraded)

    # --- candidate selection (bounded) ------------------------------------

    async def _select_delta(
        self, scope: Scope, watermark: str | None
    ) -> tuple[list[MemoryItem], bool, str | None]:
        rows = await self.store.query(
            scope=scope,
            status=Status.ACTIVE,
            limit=self.config.max_items_per_sweep + 1,
        )
        if watermark is not None:
            rows = [r for r in rows if (r.updated_at or "") > watermark]
        # query() orders by created_at DESC; process oldest-first so a capped
        # catch-up watermark advances monotonically over a stable prefix.
        rows.sort(key=lambda r: r.updated_at or "")

        capped = len(rows) > self.config.max_items_per_sweep
        if capped:
            rows = rows[: self.config.max_items_per_sweep]
        last_processed = rows[-1].updated_at if rows else None
        return rows, capped, last_processed

    async def _build_neighborhoods(
        self, delta: list[MemoryItem], scope: Scope, degraded: bool
    ) -> list[list[MemoryItem]]:
        """One neighborhood per delta claim: the claim plus a handful of active,
        in-scope claims that lexically resemble it (so a new claim merges against
        an older one outside the delta). FTS down → the delta claim alone.

        Neighborhoods are de-duplicated by frozen id-set so two delta claims that
        recall each other are not judged twice.
        """
        scope_ids = await self._scope_active_claim_ids(scope)
        by_id: dict[str, MemoryItem] = {}
        seen_hoods: set[frozenset[str]] = set()
        hoods: list[list[MemoryItem]] = []

        for claim in delta:
            members = {claim.id: claim}
            if not degraded:
                hits = await self.store.search(
                    claim.content, limit=self.config.neighborhood_limit
                )
                for h in hits:
                    if h.id not in scope_ids:
                        continue
                    members.setdefault(h.id, h)
            key = frozenset(members)
            if key in seen_hoods or len(members) < 1:
                continue
            seen_hoods.add(key)
            by_id.update(members)
            hoods.append(list(members.values()))
        return hoods

    async def _scope_active_claim_ids(self, scope: Scope) -> set[str]:
        rows = await self.store.query(scope=scope, status=Status.ACTIVE, limit=10_000)
        return {r.id for r in rows}

    # --- LLM judgment -----------------------------------------------------

    async def _judge(self, hood: list[MemoryItem], scope: Scope) -> LintOps | None:
        # A singleton neighborhood with FTS available can still be an orphan; with
        # FTS down it can only be an orphan. Either way the call is cheap and the
        # rubric NOOPs when there is nothing to do.
        cards = await self._render_hood(hood)
        scope_label = f"{scope.kind}" + (f":{scope.key}" if scope.key else "")
        messages = [
            {"role": "system", "content": LINT_RUBRIC},
            {
                "role": "user",
                "content": f"SCOPE: {scope_label}\n\nNEIGHBORHOOD:\n{cards}",
            },
        ]
        try:
            resp = await self.cheap_llm.completion(
                messages=messages,
                model=self.model,
                response_format=LintOps,
            )
            raw = resp.choices[0].message.content
            return LintOps.model_validate_json(raw)
        except Exception:
            _logger.exception("lint judgment failed for neighborhood")
            return None

    async def _render_hood(self, hood: list[MemoryItem]) -> str:
        lines = []
        for c in hood:
            edges = await self.store.list_edges(c.id, direction="from")
            edge_note = (
                ", ".join(sorted({str(e.role) for e in edges})) or "none"
            )
            src = "; ".join(f"{r.kind}:{r.ref}" for r in c.source_refs) or "none"
            lines.append(
                json.dumps(
                    {
                        "id": c.id,
                        "content": c.content,
                        "provenance": str(c.provenance),
                        "corroboration": c.corroboration,
                        "feedback": str(c.feedback),
                        "valid_from": c.valid_from,
                        "invalid_at": c.invalid_at,
                        "source_refs": src,
                        "edges": edge_note,
                    }
                )
            )
        return "\n".join(lines)

    # --- apply ops (idempotent, demote-only) ------------------------------

    async def _apply(
        self, ops: LintOps, hood: list[MemoryItem], scope: Scope
    ) -> tuple[int, int, int, int]:
        live = await self._reload_active(hood)
        merged = invalidated = dropped = flagged = 0

        for op in ops.merges:
            done = await self._apply_merge(op, live)
            merged += done

        for op in ops.invalidations:
            kind = await self._apply_invalidate(op, live)
            if kind == "invalidate":
                invalidated += 1
            elif kind == "flag":
                flagged += 1

        for op in ops.orphans:
            if await self._apply_orphan(op, live):
                dropped += 1

        return merged, invalidated, dropped, flagged

    async def _reload_active(self, hood: list[MemoryItem]) -> dict[str, MemoryItem]:
        live: dict[str, MemoryItem] = {}
        for c in hood:
            fresh = await self.store.get(c.id)
            if fresh is not None and fresh.status is Status.ACTIVE:
                live[fresh.id] = fresh
        return live

    async def _apply_merge(self, op: MergeOp, live: dict[str, MemoryItem]) -> int:
        members = [live[m] for m in op.member_ids if m in live]
        if len(members) < 2:
            return 0  # hallucinated/stale ids dropped, not dead-ended
        # Never merge away a user-confirmed claim; if any member is confirmed,
        # leave the whole group (the rubric forbids it, this enforces it).
        if any(m.feedback is Feedback.CONFIRMED for m in members):
            _logger.info("skip merge touching a confirmed claim")
            return 0

        survivor = self._pick_survivor(members)
        losers = [m for m in members if m.id != survivor.id]

        union_refs = list(survivor.source_refs)
        seen = {(r.kind, r.ref) for r in union_refs}
        for loser in losers:
            for r in loser.source_refs:
                if (r.kind, r.ref) not in seen:
                    union_refs.append(r)
                    seen.add((r.kind, r.ref))

        new_survivor = self._clone_for_supersede(
            survivor,
            content=op.merged_text or survivor.content,
            source_refs=union_refs,
            provenance=self._capped_provenance(members),
        )

        # Mint the unified survivor by superseding the old survivor row (closes it
        # as superseded, links SUPERSEDES, one transaction). Then fold every loser
        # onto the new survivor: close the loser (superseded) and link it. Losers
        # cannot reuse store.supersede() (that would mint a row per loser), so we
        # invalidate + add the SUPERSEDES edge by hand — same end state. The
        # successor keeps the survivor's canonical_subject; lens membership
        # recomputes (claims carry no membership edge).
        await self.store.supersede(old_id=survivor.id, new_item=new_survivor)

        # Fold each loser atomically: close it + link the SUPERSEDES edge under ONE
        # transaction (commit=False per step, one commit after) so a crash mid-fold
        # can't leave a superseded loser with no edge — orphaning its history.
        for loser in losers:
            await self.store.invalidate(loser.id, status=Status.SUPERSEDED, commit=False)
            await self.store.add_edge(
                MemoryEdge(
                    child_id=new_survivor.id, parent_id=loser.id, role=EdgeRole.SUPERSEDES
                ),
                commit=False,
            )
        if losers:
            await self.store.conn.commit()

        await self.store.bump_corroboration(new_survivor.id)
        return len(losers)

    async def _apply_invalidate(self, op: InvalidateOp, live: dict[str, MemoryItem]) -> str:
        target = live.get(op.claim_id)
        if target is None:
            return ""
        if target.feedback is Feedback.CONFIRMED:
            _logger.info("skip invalidate of a confirmed claim")
            return ""

        # Genuine contradiction by a newer claim shown in the hood: keep history
        # as a supersede + CONTRADICTS edge rather than a bare archive. We do NOT
        # synthesize a successor here (we have no new fact); a true contradiction
        # with a successor flows through Reconcile. Lint only flags it: emit the
        # CONTRADICTS edge between the two existing rows, leave both active.
        contra = op.contradicted_by and live.get(op.contradicted_by)
        if contra is not None:
            if self._is_high_trust(target) and self._is_high_trust(contra):
                # Two contradictory high-provenance claims: never auto-pick a
                # winner. Flag only.
                await self.store.add_edge(
                    MemoryEdge(
                        child_id=contra.id,
                        parent_id=target.id,
                        role=EdgeRole.CONTRADICTS,
                    )
                )
                return "flag"
            # Newer/better-grounded claim wins: archive the stale target and link
            # the contradiction for walkability — atomically (one transaction).
            await self.store.invalidate(target.id, status=Status.ARCHIVED, commit=False)
            await self.store.add_edge(
                MemoryEdge(
                    child_id=contra.id, parent_id=target.id, role=EdgeRole.CONTRADICTS
                ),
                commit=False,
            )
            await self.store.conn.commit()
            return "invalidate"

        # Plain stale invalidation.
        ok = await self.store.invalidate(target.id, status=Status.ARCHIVED)
        return "invalidate" if ok else ""

    async def _apply_orphan(self, op: DropOrphanOp, live: dict[str, MemoryItem]) -> bool:
        target = live.get(op.claim_id)
        if target is None:
            return False
        if target.feedback is Feedback.CONFIRMED:
            return False
        # Verify orphan-hood against the live store, not the model's word.
        if target.source_refs:
            return False
        edges_from = await self.store.list_edges(target.id, direction="from")
        edges_to = await self.store.list_edges(target.id, direction="to")
        if edges_from or edges_to:
            return False
        return await self.store.invalidate(target.id, status=Status.ARCHIVED)

    # --- helpers ----------------------------------------------------------

    def _pick_survivor(self, members: list[MemoryItem]) -> MemoryItem:
        return max(
            members,
            key=lambda m: (
                _PROVENANCE_ORDINAL.get(m.provenance, 0),
                m.corroboration,
                len(m.source_refs),
                m.updated_at or "",
            ),
        )

    def _capped_provenance(self, members: list[MemoryItem]) -> Provenance:
        """Survivor trust = max of inputs, but capped at INFERRED because the
        merge itself is the LLM's inference. Lint may never raise trust."""
        best = max(members, key=lambda m: _PROVENANCE_ORDINAL.get(m.provenance, 0))
        if _PROVENANCE_ORDINAL.get(best.provenance, 0) > _PROVENANCE_ORDINAL[Provenance.INFERRED]:
            return Provenance.INFERRED
        return best.provenance

    def _is_high_trust(self, item: MemoryItem) -> bool:
        return (
            item.provenance is Provenance.USER_AUTHORED
            or item.feedback is Feedback.CONFIRMED
        )

    def _clone_for_supersede(
        self,
        base: MemoryItem,
        *,
        content: str,
        source_refs,
        provenance: Provenance,
    ) -> MemoryItem:
        import uuid

        now = now_iso()
        return MemoryItem(
            id=str(uuid.uuid4()),
            content=content,
            canonical_subject=base.canonical_subject,
            scope=base.scope,
            provenance=provenance,
            status=Status.ACTIVE,
            valid_from=base.valid_from,
            invalid_at=None,
            source_refs=source_refs,
            corroboration=base.corroboration,
            last_relevant_at=base.last_relevant_at,
            feedback=Feedback.NONE,
            created_at=now,
            updated_at=now,
        )

    # --- watermark (in the store's meta table) ----------------------------

    def _watermark_key(self, scope: Scope) -> str:
        return f"{WATERMARK_PREFIX}:{scope.kind}:{scope.key or ''}"

    async def _read_watermark(self, scope: Scope) -> str | None:
        rows = await self.store.conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = ?", (self._watermark_key(scope),)
        )
        return rows[0]["value"] if rows else None

    async def _write_watermark(self, scope: Scope, value: str) -> None:
        await self.store.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._watermark_key(scope), value),
        )
        await self.store.conn.commit()
