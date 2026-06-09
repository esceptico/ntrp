"""Consolidate/Lint — the background pass that turns the raw record pile into a
SMALL, CLEAN, CURRENT body. THIS is the memory: records alone are raw atoms.

A periodic health-check of the active record pool. The only stage that removes
records from circulation: MERGE duplicates onto one survivor, SUPERSEDE
stale/contradicted records into a newer one, DROP genuine orphans. It never
authors a new fact and never raises trust.

Watermark-durable, demote/merge-only, O(delta) — never O(corpus). Candidate
selection is only the records confirmed since the last successful sweep, plus
each delta record's recall neighborhood (one cheap LLM call per neighborhood).
Pinned records are inviolable. With no LLM configured, the pass is a no-op.

Adapted from the deleted claim-pipeline `consolidate.py`: scopes,
provenance/feedback/corroboration ordering, CONTRADICTS/SUPERSEDES edges, and the
high-trust flag path are all stripped — records are flat, edge-less, single-axis.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from ntrp.database import connect as db_connect
from ntrp.logging import get_logger
from ntrp.memory.models import Record, now_iso
from ntrp.memory.prompts_consolidate import (
    LINT_RUBRIC,
    DropOrphanOp,
    InvalidateOp,
    LintOps,
    MergeOp,
    RetypeOp,
)

# Function-types a consolidation op may assign (guard against a hallucinated kind).
_KINDS = {"fact", "preference", "action", "note"}
from ntrp.memory.records import RecordStore

_logger = get_logger(__name__)

MAX_ITEMS_PER_SWEEP = 200
NEIGHBORHOOD_LIMIT = 8
WATERMARK_KEY = "consolidate_watermark"


@dataclass
class ConsolidateReport:
    merged: int = 0       # records folded onto a survivor
    retyped: int = 0      # records reclassified to their function-type (note -> fact/...)
    superseded: int = 0   # stale/contradicted records closed (incl. deleted orphans/stale)
    dropped: int = 0      # orphans removed
    survivors: list[Record] = None  # merge survivors (for lens re-scoring)

    def __post_init__(self):
        if self.survivors is None:
            self.survivors = []


class Consolidate:
    def __init__(
        self,
        records: RecordStore,
        llm,                       # completion client (config.memory_model); None -> no-op
        *,
        model: str | None,
        db_path: Path,             # config.memory_db_path — shares the Curator's meta table
        reasoning_effort: str | None = None,
    ) -> None:
        self._records = records
        self._llm = llm
        self._model = model
        self._db_path = db_path
        self._reasoning_effort = reasoning_effort
        self._conn = None
        self._conn_lock = asyncio.Lock()

    # --- one sweep ---------------------------------------------------------

    async def run_once(self) -> ConsolidateReport:
        """One O(delta) sweep over records confirmed since the watermark. No-op
        (and cheap) when nothing changed or no LLM is configured."""
        report = ConsolidateReport()
        if self._llm is None or not self._model:
            return report

        sweep_start = now_iso()
        watermark = await self._read_watermark()

        delta, capped, last_processed = await self._select_delta(watermark)
        if not delta:
            await self._write_watermark(sweep_start)
            return report

        for hood in await self._build_neighborhoods(delta):
            ops = await self._judge(hood)
            if ops is None:
                continue
            await self._apply(ops, hood, report)

        # Durability: a full sweep advances to sweep_start; a capped catch-up
        # advances only to the last processed record's confirm time so the
        # unprocessed tail is not skipped next run.
        await self._write_watermark(last_processed if capped else sweep_start)
        return report

    # --- candidate selection (bounded) ------------------------------------

    async def _select_delta(
        self, watermark: str | None
    ) -> tuple[list[Record], bool, str | None]:
        rows = await self._records.updated_since(watermark, limit=MAX_ITEMS_PER_SWEEP + 1)
        capped = len(rows) > MAX_ITEMS_PER_SWEEP
        if capped:
            rows = rows[:MAX_ITEMS_PER_SWEEP]
        last_processed = rows[-1].last_confirmed_at if rows else None
        return rows, capped, last_processed

    async def _build_neighborhoods(self, delta: list[Record]) -> list[list[Record]]:
        """One neighborhood per delta record: the record plus a handful of active
        records that resemble it (so a new record merges against an older one
        outside the delta). De-duped by frozen id-set so two delta records that
        recall each other aren't judged twice."""
        seen: set[frozenset[str]] = set()
        hoods: list[list[Record]] = []
        for record in delta:
            members = {record.id: record}
            for hit in await self._records.neighborhood(record, limit=NEIGHBORHOOD_LIMIT):
                members.setdefault(hit.id, hit)
            key = frozenset(members)
            if key in seen:
                continue
            seen.add(key)
            hoods.append(list(members.values()))
        return hoods

    # --- LLM judgment -----------------------------------------------------

    async def _judge(self, hood: list[Record]) -> LintOps | None:
        cards = "\n".join(
            json.dumps(
                {
                    "id": r.id,
                    "text": r.text,
                    "kind": r.kind,
                    "last_confirmed_at": r.last_confirmed_at,
                    "pinned": r.pinned,
                }
            )
            for r in hood
        )
        messages = [
            {"role": "system", "content": LINT_RUBRIC},
            {"role": "user", "content": f"NEIGHBORHOOD:\n{cards}"},
        ]
        try:
            resp = await self._llm.completion(
                messages=messages,
                model=self._model,
                reasoning_effort=self._reasoning_effort,
                response_format=LintOps,
            )
        except Exception:
            _logger.warning("consolidate judgment failed for neighborhood", exc_info=True)
            return None
        content = resp.choices[0].message.content if resp.choices else None
        if not content or not content.strip():
            return None
        try:
            return LintOps.model_validate_json(content)
        except Exception:
            _logger.warning("consolidate: unparseable judgment", exc_info=True)
            return None

    # --- apply (idempotent, demote-only) ----------------------------------

    async def _apply(self, ops: LintOps, hood: list[Record], report: ConsolidateReport) -> None:
        live = await self._reload_active(hood)
        for op in ops.merges:
            await self._apply_merge(op, live, report)
        for op in ops.retypes:
            await self._apply_retype(op, live, report)
        for op in ops.invalidations:
            await self._apply_invalidate(op, live, report)
        for op in ops.orphans:
            await self._apply_orphan(op, live, report)

    async def _reload_active(self, hood: list[Record]) -> dict[str, Record]:
        """Re-fetch each member; keep only still-active rows (the idempotency guard
        — an op the previous neighborhood already applied is silently skipped)."""
        live: dict[str, Record] = {}
        for r in hood:
            fresh = await self._records.get(r.id)
            if fresh is not None and fresh.superseded_by is None:
                live[fresh.id] = fresh
        return live

    async def _apply_merge(self, op: MergeOp, live: dict[str, Record], report: ConsolidateReport) -> None:
        members = [live[m] for m in op.member_ids if m in live]
        if len(members) < 2:
            return  # hallucinated/stale ids dropped, not dead-ended
        if any(m.pinned for m in members):
            return  # never merge a pinned record away
        survivor = self._pick_survivor(members)
        loser_ids = [m.id for m in members if m.id != survivor.id]
        kind = op.kind if op.kind in _KINDS else None
        merged = await self._records.merge(survivor.id, loser_ids, text=op.merged_text, kind=kind)
        if merged is None:
            return
        report.merged += len(loser_ids)
        report.survivors.append(merged)
        # Reflect the merge in our live view so a later op in the same hood
        # doesn't act on a now-superseded loser.
        for lid in loser_ids:
            live.pop(lid, None)
        live[survivor.id] = merged

    async def _apply_retype(self, op: RetypeOp, live: dict[str, Record], report: ConsolidateReport) -> None:
        """Reclassify a single record's function-type (e.g. a raw 'note' that is
        actually a standing fact/preference/workflow). Pinned records are untouched."""
        target = live.get(op.record_id)
        if target is None or target.pinned:
            return
        if op.kind not in _KINDS or op.kind == target.kind:
            return
        if await self._records.set_kind(op.record_id, op.kind):
            report.retyped += 1
            live[op.record_id] = await self._records.get(op.record_id)

    async def _apply_invalidate(self, op: InvalidateOp, live: dict[str, Record], report: ConsolidateReport) -> None:
        target = live.get(op.record_id)
        if target is None or target.pinned:
            return
        contra = op.contradicted_by and live.get(op.contradicted_by)
        if contra is not None and contra.id != target.id and not contra.pinned:
            # A newer record supersedes the stale one: close the lineage into it.
            await self._records.supersede(target.id, contra.id)
            report.superseded += 1
        else:
            # Plain stale invalidation with no successor: records have no archived
            # status, so a stale record with nothing to fold into is deleted.
            await self._records.delete(target.id)
            report.superseded += 1
        live.pop(target.id, None)

    async def _apply_orphan(self, op: DropOrphanOp, live: dict[str, Record], report: ConsolidateReport) -> None:
        target = live.get(op.record_id)
        if target is None or target.pinned:
            return
        # Verify orphan-hood against the live store: a record is an orphan only if
        # it has no provenance source (records carry no edges).
        if target.source_ref is not None:
            return
        await self._records.delete(target.id)
        report.dropped += 1
        live.pop(target.id, None)

    @staticmethod
    def _pick_survivor(members: list[Record]) -> Record:
        """The best-grounded survivor: pinned wins, then most-recently confirmed,
        then the longest (most complete) text."""
        return max(members, key=lambda m: (m.pinned, m.last_confirmed_at or "", len(m.text)))

    # --- watermark (shares the Curator's meta table in memory.db) ----------

    async def _ensure_conn(self):
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._conn is None:
                conn = await db_connect(self._db_path)
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
                )
                await conn.commit()
                self._conn = conn
        return self._conn

    async def _read_watermark(self) -> str | None:
        conn = await self._ensure_conn()
        rows = await conn.execute_fetchall(
            "SELECT value FROM meta WHERE key = ?", (WATERMARK_KEY,)
        )
        return rows[0]["value"] if rows else None

    async def _write_watermark(self, value: str | None) -> None:
        if value is None:
            return
        conn = await self._ensure_conn()
        await conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (WATERMARK_KEY, value),
        )
        await conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
