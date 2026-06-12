"""Consolidate/Lint — the background pass that turns the raw record pile into a
SMALL, CLEAN, CURRENT body. THIS is the memory: records alone are raw atoms.

A periodic health-check of the active record pool. The only stage that removes
records from circulation: MERGE duplicates onto one survivor, SUPERSEDE
stale/contradicted records into a newer one, DROP genuine orphans. It never
authors a new fact and never raises trust. Each sweep also runs ONE bounded
label-hygiene call over the whole label vocabulary, folding near-duplicate
names (case/synonym variants) via rename_label.

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
from ntrp.memory.lens_page import LensPage
from ntrp.memory.models import Record, now_iso
from ntrp.memory.prompts_consolidate import (
    LABEL_HYGIENE_RUBRIC,
    LINT_RUBRIC,
    DropOrphanOp,
    InvalidateOp,
    LabelOps,
    LintOps,
    MergeOp,
    RetypeOp,
)
from ntrp.memory.prompts_derive import (
    DREAM_RUBRIC,
    REJUDGE_RUBRIC,
    VERIFY_RUBRIC,
    DreamOps,
    RejudgeOp,
    VerifyVerdict,
)
from ntrp.memory.records import RecordStore

_logger = get_logger(__name__)

# Function-types a consolidation op may assign (guard against a hallucinated kind).
_KINDS = {"fact", "preference", "action", "note"}

MAX_ITEMS_PER_SWEEP = 200
NEIGHBORHOOD_LIMIT = 8
WATERMARK_KEY = "consolidate_watermark"
# Derivation (the recursive memory): bounded per sweep — bulk derivation is the
# fabrication regime. Depth capped so speculation can't tower.
MAX_DERIVATIONS_PER_SWEEP = 6
MAX_REJUDGE_PER_SWEEP = 10
DERIVATION_DEPTH_CAP = 3
_DERIVE_MODES = {"deduction", "induction", "abduction"}


@dataclass
class ConsolidateReport:
    merged: int = 0       # records folded onto a survivor
    retyped: int = 0      # records reclassified to their function-type (note -> fact/...)
    superseded: int = 0   # stale/contradicted records closed (incl. deleted orphans/stale)
    dropped: int = 0      # orphans removed
    relabeled: int = 0    # label spellings folded into a canonical name
    derived: int = 0      # NEW inferred records (the dream)
    corroborated: int = 0 # re-derivations that landed as extra justifications
    reaffirmed: int = 0   # unresolved derivations re-grounded on live premises
    revised: int = 0      # unresolved derivations corrected (superseded into new)
    retired: int = 0      # derivations retired (re-judgment or hygiene), nogood kept


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
        self._page_synth = LensPage(llm, model=model, reasoning_effort=reasoning_effort)
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
            # Quiet sweep: no record work, but re-judge any unresolved derivations.
            await self._rejudge_unresolved(report)
            await self._write_watermark(sweep_start)
            return report

        hoods = await self._build_neighborhoods(delta)
        for hood in hoods:
            ops = await self._judge(hood)
            if ops is None:
                continue
            await self._apply(ops, hood, report)

        await self._lint_labels(report)
        # Restore knowledge before building on it: re-judge premises-died
        # derivations first, THEN dream over the (now clean) neighborhoods.
        await self._rejudge_unresolved(report)
        await self._dream(hoods, report)

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

    # --- label hygiene (one bounded call per sweep) -------------------------

    async def _lint_labels(self, report: ConsolidateReport) -> None:
        """Canonicalize the label vocabulary: ONE LLM call over the whole
        list_labels() (it is small) spots near-duplicate names — case/synonym
        variants like "dex"/"Dex memory" — applied as rename_label folds.
        Skipped when the vocabulary has fewer than 2 labels; the empty-delta
        early return in run_once covers the no-new-records sweep."""
        labels = await self._records.list_labels()
        if len(labels) < 2:
            return
        ops = await self._judge_labels(labels)
        if ops is None:
            return
        names = {entry["label"] for entry in labels}
        for op in ops.renames:
            new = op.new.strip()
            if not new or op.old == new or op.old not in names:
                continue  # hallucinated/echoed names dropped, not dead-ended
            await self._records.rename_label(op.old, new)
            names.discard(op.old)
            names.add(new)
            report.relabeled += 1

    async def _judge_labels(self, labels: list[dict]) -> LabelOps | None:
        listing = "\n".join(f"{entry['label']}: {entry['count']}" for entry in labels)
        messages = [
            {"role": "system", "content": LABEL_HYGIENE_RUBRIC},
            {"role": "user", "content": f"VOCABULARY (label: active records):\n{listing}"},
        ]
        try:
            resp = await self._llm.completion(
                messages=messages,
                model=self._model,
                reasoning_effort=self._reasoning_effort,
                response_format=LabelOps,
            )
        except Exception:
            _logger.warning("label hygiene judgment failed", exc_info=True)
            return None
        content = resp.choices[0].message.content if resp.choices else None
        if not content or not content.strip():
            return None
        try:
            return LabelOps.model_validate_json(content)
        except Exception:
            _logger.warning("label hygiene: unparseable judgment", exc_info=True)
            return None

    # --- derivation: the dream (spec §3) + re-judgment (spec §4) ------------

    async def _complete(self, system: str, user: str, schema):
        """One structured judgment; None on failure (caller NOOPs)."""
        try:
            resp = await self._llm.completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                model=self._model,
                reasoning_effort=self._reasoning_effort,
                response_format=schema,
            )
        except Exception:
            _logger.warning("derivation judgment failed", exc_info=True)
            return None
        content = resp.choices[0].message.content if resp.choices else None
        if not content or not content.strip():
            return None
        try:
            return schema.model_validate_json(content)
        except Exception:
            _logger.warning("derivation: unparseable judgment", exc_info=True)
            return None

    @staticmethod
    def _card(r: Record) -> str:
        tag = " [inferred]" if r.provenance == "derived" else ""
        return f"- {r.id}{tag}: {r.text}"

    async def _dream(self, hoods: list[list[Record]], report: ConsolidateReport) -> None:
        """Question-first derivation over the sweep's neighborhoods, budgeted.
        Each committed conclusion cites its premises (cite-or-void) and passes a
        reversed-framing verification before it may enter the pool."""
        budget = MAX_DERIVATIONS_PER_SWEEP
        for hood in hoods:
            if budget <= 0:
                return
            live = list((await self._reload_active(hood)).values())
            live = [r for r in live if r.standing == "active"]
            if len(live) < 2:
                continue
            by_id = {r.id: r for r in live}
            nogoods = await self._records.nogoods_for(list(by_id))
            user = "NEIGHBORHOOD:\n" + "\n".join(self._card(r) for r in live)
            if nogoods:
                user += "\n\nNOGOODS (previously RETRACTED from these records — never re-derive):\n" + "\n".join(
                    f"- {n['conclusion']} (why retracted: {n['why']})" for n in nogoods
                )
            ops = await self._complete(DREAM_RUBRIC, user, DreamOps)
            if ops is None:
                continue
            for cand in ops.candidates[:3]:
                if budget <= 0:
                    return
                premises = [by_id[p] for p in dict.fromkeys(cand.premise_ids) if p in by_id]
                if not premises or cand.mode not in _DERIVE_MODES:
                    continue
                if cand.mode == "induction" and len(premises) < 2:
                    continue
                if max(p.depth for p in premises) + 1 > DERIVATION_DEPTH_CAP:
                    continue
                if await self._verify_and_commit(cand, premises, report):
                    budget -= 1

    async def _verify_and_commit(self, cand, premises: list[Record], report: ConsolidateReport) -> bool:
        """ADM verify-before-commit, then enter through reconcile: a conclusion an
        existing record already states lands as an extra JUSTIFICATION on it
        (corroboration), never a twin."""
        existing = await self._records.search(cand.conclusion, limit=5)
        existing = [e for e in existing if e.id not in {p.id for p in premises}]
        user = (
            "PREMISES:\n" + "\n".join(self._card(p) for p in premises)
            + "\n\nEXISTING NEARBY RECORDS:\n"
            + ("\n".join(self._card(e) for e in existing) or "(none)")
            + f"\n\nCANDIDATE CONCLUSION:\n{cand.conclusion}"
        )
        verdict = await self._complete(VERIFY_RUBRIC, user, VerifyVerdict)
        if verdict is None or not verdict.supported or not verdict.nontrivial:
            return False
        premise_ids = [p.id for p in premises]
        if verdict.duplicate_of:
            target = next((e for e in existing if e.id == verdict.duplicate_of), None)
            if target is None:
                return False  # hallucinated duplicate id — drop, don't dead-end
            try:
                await self._records.add_justification(
                    target.id, premise_ids=premise_ids, mode=cand.mode, question=cand.question
                )
            except ValueError:
                return False  # cyclic/dead support — drop
            report.corroborated += 1
            return True
        try:
            await self._records.add_derived(
                cand.conclusion, premise_ids=premise_ids, mode=cand.mode,
                question=cand.question, kind="fact",
            )
        except ValueError:
            return False
        report.derived += 1
        return True

    async def _rejudge_unresolved(self, report: ConsolidateReport) -> None:
        """Spec §4.4 — derivations whose premises died: re-affirm on live
        premises, revise into a corrected conclusion, or retire (+ nogood).
        Bounded per sweep; anything unjudged stays unresolved for the next one."""
        for record in await self._records.unresolved(limit=MAX_REJUDGE_PER_SWEEP):
            justs = await self._records.justifications_of(record.id)
            dead: list[Record] = []
            successors: list[Record] = []
            live: dict[str, Record] = {}
            for just in justs:
                for pid in just.premise_ids:
                    premise = await self._records.get(pid)
                    if premise is None:
                        continue
                    if premise.superseded_by is not None or premise.standing != "active":
                        dead.append(premise)
                        if premise.superseded_by:
                            succ = await self._records.get(premise.superseded_by)
                            if succ is not None and succ.standing == "active":
                                successors.append(succ)
                    else:
                        live[premise.id] = premise
            for hit in await self._records.search(record.text, limit=NEIGHBORHOOD_LIMIT):
                if hit.id != record.id:
                    live.setdefault(hit.id, hit)
            for succ in successors:
                live.setdefault(succ.id, succ)
            question = justs[0].question if justs else ""
            mode = justs[0].mode if justs else "deduction"
            user = (
                f"INFERRED RECORD (question it answered: {question!r}):\n- {record.id}: {record.text}"
                + "\n\nDEAD PREMISES:\n"
                + ("\n".join(f"- {d.id}: {d.text}" for d in dead) or "(deleted)")
                + "\n\nSUPERSEDING RECORDS:\n"
                + ("\n".join(self._card(s) for s in successors) or "(none)")
                + "\n\nLIVE RECORDS (usable premises):\n"
                + ("\n".join(self._card(r) for r in live.values()) or "(none)")
            )
            op = await self._complete(REJUDGE_RUBRIC, user, RejudgeOp)
            if op is None:
                continue  # stays unresolved; retried next sweep
            premise_ids = [p for p in dict.fromkeys(op.premise_ids) if p in live]
            if op.op == "REAFFIRM" and premise_ids:
                try:
                    await self._records.add_justification(
                        record.id, premise_ids=premise_ids, mode=mode, question=question
                    )
                except ValueError:
                    continue
                report.reaffirmed += 1
            elif op.op == "REVISE" and op.text and op.text.strip() and premise_ids:
                try:
                    revised = await self._records.add_derived(
                        op.text.strip(), premise_ids=premise_ids, mode=mode,
                        question=question, kind=record.kind,
                    )
                except ValueError:
                    continue
                await self._records.supersede(record.id, revised.id)
                report.revised += 1
            elif op.op == "RETIRE":
                await self._records.retire(record.id, nogood_why=op.why or "premise superseded")
                report.retired += 1

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
