"""Consolidate/Lint — the records consolidation pass (ntrp/memory/consolidate.py).

THIS is the memory step: the background O(delta) pass that merges duplicates,
supersedes stale/contradicted records, and drops orphans over the flat record
pool. Hermetic: a STUB LLM (scripted LintOps JSON per neighborhood) + a real tmp
RecordStore (search_index=None -> FTS-only neighborhoods). The watermark lives in
the same tmp memory.db.

Covers:
  (a) merge folds duplicate records onto one survivor (the others superseded);
  (b) a pinned record is never merged/invalidated/dropped;
  (c) invalidate-with-successor supersedes the stale record into the newer one;
  (d) invalidate-without-successor deletes the stale record;
  (e) drop_orphan deletes a source-less record, but keeps a record with provenance;
  (f) watermark durability: a clean second sweep does no LLM work;
  (g) no LLM / no model -> no-op;
  (h) the RecordStore primitives: merge atomicity + pin-guard, updated_since order.
"""

from pathlib import Path

import pytest

from ntrp.memory.consolidate import Consolidate
from ntrp.memory.models import SourceRef
from ntrp.memory.prompts_consolidate import LabelOps, LintOps
from ntrp.memory.prompts_derive import DreamOps
from ntrp.memory.records import RecordStore
from tests.conftest import completion_response

pytestmark = pytest.mark.asyncio


class StubLLM:
    """Scripted completion client: returns queued LintOps payloads (FIFO) and
    records every call so a test can assert the per-neighborhood cost / no-op."""

    def __init__(self, *responses: str):
        self._queue = list(responses)
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, reasoning_effort=None, response_format=None, **kwargs):
        self.calls.append({"messages": messages, "model": model, "response_format": response_format})
        body = self._queue.pop(0) if self._queue else LintOps().model_dump_json()
        return completion_response(body)


def _consolidate(tmp_path: Path, records: RecordStore, llm) -> Consolidate:
    return Consolidate(records, llm, model="memory-model", db_path=tmp_path / "memory.db")


def _merge_ops(member_ids: list[str], merged_text: str | None = None) -> str:
    return LintOps.model_validate(
        {"merges": [{"member_ids": member_ids, "merged_text": merged_text}]}
    ).model_dump_json()


def _invalidate_ops(record_id: str, contradicted_by: str | None = None) -> str:
    return LintOps.model_validate(
        {"invalidations": [{"record_id": record_id, "contradicted_by": contradicted_by}]}
    ).model_dump_json()


def _orphan_ops(record_id: str) -> str:
    return LintOps.model_validate({"orphans": [{"record_id": record_id}]}).model_dump_json()


# --- merge --------------------------------------------------------------------


async def test_merge_folds_duplicates_onto_one_survivor(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user lives in Yerevan")
    b = await records.add("the user lives in Yerevan, Armenia")
    # One neighborhood is judged; queue a merge of both onto a unified survivor.
    llm = StubLLM(_merge_ops([a.id, b.id], merged_text="the user lives in Yerevan, Armenia"))
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.merged == 1
    active = await records.list()
    assert len(active) == 1
    survivor = active[0]
    assert survivor.text == "the user lives in Yerevan, Armenia"
    # The loser is closed into the survivor (history preserved).
    loser = a if survivor.id == b.id else b
    closed = await records.get(loser.id)
    assert closed.superseded_by == survivor.id
    await consolidate.close()
    await records.close()


async def test_merge_keeps_survivor_text_without_merged_text(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("uses Linux daily")
    b = await records.add("uses Linux daily")
    llm = StubLLM(_merge_ops([a.id, b.id]))  # no unified wording
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.merged == 1
    active = await records.list()
    assert len(active) == 1
    assert active[0].text == "uses Linux daily"
    await consolidate.close()
    await records.close()


# --- pin inviolability --------------------------------------------------------


async def test_pinned_record_is_never_merged(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user lives in Yerevan", pinned=True)
    b = await records.add("the user lives in Yerevan")
    llm = StubLLM(_merge_ops([a.id, b.id]))
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.merged == 0
    assert len(await records.list()) == 2  # both survive untouched
    await consolidate.close()
    await records.close()


async def test_pinned_record_is_never_invalidated(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user works at Acme", pinned=True)
    llm = StubLLM(_invalidate_ops(a.id))
    consolidate = _consolidate(tmp_path, records, llm)

    await consolidate.run_once()

    assert await records.get(a.id) is not None  # not deleted
    await consolidate.close()
    await records.close()


# --- invalidate ---------------------------------------------------------------


async def test_invalidate_with_successor_supersedes_into_it(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    old = await records.add("the user works at Acme")
    new = await records.add("the user works at Globex")
    # Both share the "the user works at" neighborhood; mark old as superseded by new.
    llm = StubLLM(_invalidate_ops(old.id, contradicted_by=new.id))
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.superseded == 1
    closed = await records.get(old.id)
    assert closed.superseded_by == new.id
    assert (await records.get(new.id)).superseded_by is None  # the newer record lives
    await consolidate.close()
    await records.close()


async def test_invalidate_without_successor_deletes_stale(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    stale = await records.add("the meeting is tomorrow at noon")
    llm = StubLLM(_invalidate_ops(stale.id))
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.superseded == 1
    assert await records.get(stale.id) is None  # no successor -> deleted
    await consolidate.close()
    await records.close()


# --- drop orphan --------------------------------------------------------------


async def test_drop_orphan_removes_sourceless_record(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    orphan = await records.add("a stray fragment")  # no source_ref
    llm = StubLLM(_orphan_ops(orphan.id))
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.dropped == 1
    assert await records.get(orphan.id) is None
    await consolidate.close()
    await records.close()


async def test_drop_orphan_keeps_record_with_provenance(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    sourced = await records.add("a sourced fact", source_ref=SourceRef("curator", "s1"))
    llm = StubLLM(_orphan_ops(sourced.id))
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.dropped == 0
    assert await records.get(sourced.id) is not None  # provenance -> not an orphan
    await consolidate.close()
    await records.close()


# --- label hygiene (one bounded call per sweep) --------------------------------


def _label_ops(renames: list[tuple[str, str]]) -> str:
    return LabelOps.model_validate(
        {"renames": [{"old": old, "new": new} for old, new in renames]}
    ).model_dump_json()


async def test_label_hygiene_folds_near_duplicate_labels(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("dex sleeps through the night now")
    b = await records.add("dex sleeps in his crib")
    await records.set_labels(a.id, ["dex"])
    await records.set_labels(b.id, ["Dex memory"])
    # One neighborhood judgment (no ops), then the label-hygiene call: both
    # spellings fold into "Dex"; the hallucinated "ghost" rename is dropped.
    llm = StubLLM(
        LintOps().model_dump_json(),
        _label_ops([("dex", "Dex"), ("Dex memory", "Dex"), ("ghost", "Dex")]),
    )
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.relabeled == 2
    assert await records.list_labels() == [{"label": "Dex", "count": 2}]
    assert await records.labels_of(a.id) == ["Dex"]
    # ONE hygiene call after the neighborhood judgments, then the dream phase
    # (one DreamOps call per >=2-member neighborhood; stub yields no candidates).
    assert [c["response_format"] for c in llm.calls] == [LintOps, LabelOps, DreamOps]

    # No new records -> the next sweep spends nothing, label hygiene included.
    await consolidate.run_once()
    assert len(llm.calls) == 3
    await consolidate.close()
    await records.close()


async def test_label_hygiene_skipped_below_two_labels(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("a lone labeled fact")
    await records.set_labels(a.id, ["solo"])
    llm = StubLLM()  # default no-op LintOps for the one neighborhood
    consolidate = _consolidate(tmp_path, records, llm)

    report = await consolidate.run_once()

    assert report.relabeled == 0
    assert [c["response_format"] for c in llm.calls] == [LintOps]
    await consolidate.close()
    await records.close()


async def test_merge_unions_labels_onto_survivor(tmp_path: Path):
    """Verify the store-level union semantics through a consolidation merge."""
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("the user lives in Yerevan")
    b = await records.add("the user lives in Yerevan, Armenia")
    await records.set_labels(a.id, ["Timur"])
    await records.set_labels(b.id, ["places"])
    llm = StubLLM(
        _merge_ops([a.id, b.id], merged_text="the user lives in Yerevan, Armenia"),
        _label_ops([]),
    )
    consolidate = _consolidate(tmp_path, records, llm)

    await consolidate.run_once()

    survivor = (await records.list())[0]
    assert await records.labels_of(survivor.id) == ["Timur", "places"]
    await consolidate.close()
    await records.close()


# --- watermark durability / anti-heartbeat -----------------------------------


async def test_second_sweep_is_a_noop_without_changes(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    await records.add("a settled fact")
    llm = StubLLM()  # default LintOps() (no ops) for the first sweep's one neighborhood
    consolidate = _consolidate(tmp_path, records, llm)

    await consolidate.run_once()
    first_calls = len(llm.calls)
    assert first_calls >= 1

    # No record was confirmed after the first sweep's watermark -> the delta is
    # empty, so the second sweep spends no LLM call.
    await consolidate.run_once()
    assert len(llm.calls) == first_calls
    await consolidate.close()
    await records.close()


async def test_noop_without_llm(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    await records.add("x")
    await records.add("x")
    consolidate = Consolidate(records, None, model="memory-model", db_path=tmp_path / "memory.db")

    report = await consolidate.run_once()

    assert report.merged == 0
    assert len(await records.list()) == 2
    await consolidate.close()
    await records.close()


# --- RecordStore primitives ---------------------------------------------------


async def test_record_merge_is_atomic_and_pin_guarded(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    s = await records.add("survivor")
    l1 = await records.add("loser one")
    l2 = await records.add("loser two")

    merged = await records.merge(s.id, [l1.id, l2.id], text="unified survivor")
    assert merged is not None
    assert merged.text == "unified survivor"
    assert (await records.get(l1.id)).superseded_by == s.id
    assert (await records.get(l2.id)).superseded_by == s.id
    assert {r.id for r in await records.list()} == {s.id}

    # A pinned member aborts the whole merge.
    p = await records.add("pinned", pinned=True)
    q = await records.add("other")
    assert await records.merge(q.id, [p.id]) is None
    assert (await records.get(p.id)).superseded_by is None
    await records.close()


async def test_updated_since_is_oldest_first_and_inclusive(tmp_path: Path):
    import asyncio

    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("first")
    await asyncio.sleep(0.01)
    b = await records.add("second")

    rows = await records.updated_since(None, limit=10)
    assert [r.id for r in rows] == [a.id, b.id]  # oldest-confirmed first

    # `>=`-inclusive at the boundary.
    rows2 = await records.updated_since(a.last_confirmed_at, limit=10)
    assert a.id in {r.id for r in rows2}
    await records.close()


async def test_neighborhood_excludes_self(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    a = await records.add("kubernetes deployment guide")
    b = await records.add("kubernetes cluster setup")

    hood = await records.neighborhood(a, limit=8)
    ids = {r.id for r in hood}
    assert a.id not in ids
    assert b.id in ids
    await records.close()
