"""LensStore — named criterion VIEWS over the flat record pool, membership
LLM-scored + cached (ntrp/memory/lenses.py).

A lens is just {name, criterion}. ENTITY == LENS. Hermetic: a real tmp `memory.db`
backs both records and the lens tables; a real RecordStore (`search_index=None` ->
FTS-only) supplies the candidates. A scripted StubLLM returns banded judgements
and records every call so the cost is locked by call-count:

  - create -> ONE backfill judge call; membership cached.
  - members() -> reads the cache, NO LLM call.
  - score_records (the dreamer hook) -> one judge call PER active lens.
  - llm=None -> no judging; membership degrades to raw hybrid search of the
    criterion (NEVER a wordlist heuristic).
"""

import json
from pathlib import Path

import pytest

from ntrp.memory.lenses import LensStore
from ntrp.memory.records import RecordStore
from tests.conftest import completion_response

pytestmark = pytest.mark.asyncio


class StubLLM:
    """Scripted completion client: returns queued payloads (FIFO) and records
    every call so a test can assert the judge cost."""

    def __init__(self, *responses: str):
        self._queue = list(responses)
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, reasoning_effort=None, **kwargs):
        self.calls.append(
            {"messages": messages, "model": model, "reasoning_effort": reasoning_effort}
        )
        body = self._queue.pop(0) if self._queue else ""
        return completion_response(body)


def _members(*pairs: tuple[str, str]) -> str:
    """Build a judge response: {"members": [{"id":..., "band":...}, ...]}."""
    return json.dumps({"members": [{"id": rid, "band": band} for rid, band in pairs]})


def _records(tmp_path: Path) -> RecordStore:
    return RecordStore(tmp_path / "memory.db", search_index=None)


def _lenses(tmp_path: Path, records: RecordStore, *, llm=None) -> LensStore:
    return LensStore(tmp_path / "memory.db", records, llm=llm, model="lens-model")


# --- create / list / get / delete --------------------------------------------


async def test_create_and_get(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records, llm=StubLLM(_members()))

    lens = await lenses.create("open-tasks", "tasks that are not finished")
    assert lens.id
    assert lens.name == "open-tasks"

    got = await lenses.get("open-tasks")
    assert got is not None
    assert got.criterion == "tasks that are not finished"
    await lenses.close()
    await records.close()


async def test_list_returns_all(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records, llm=StubLLM(_members(), _members()))

    await lenses.create("a", "first criterion")
    await lenses.create("b", "second criterion")

    names = [l.name for l in await lenses.list()]
    assert set(names) == {"a", "b"}
    await lenses.close()
    await records.close()


async def test_get_missing_returns_none(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records)
    assert await lenses.get("nope") is None
    await lenses.close()
    await records.close()


async def test_delete_removes_lens_and_members_but_not_records(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("ship the thing")
    lenses = _lenses(tmp_path, records, llm=StubLLM(_members((rec.id, "high"))))
    await lenses.create("temp", "shipping work")

    assert await lenses.delete("temp") is True
    assert await lenses.get("temp") is None
    assert await lenses.delete("temp") is False  # already gone
    # The record survives a lens deletion.
    assert await records.get(rec.id) is not None
    await lenses.close()
    await records.close()


# --- create backfills membership ONCE, then members() reads the cache ---------


async def test_create_backfills_then_members_reads_cache_with_no_llm(tmp_path: Path):
    records = _records(tmp_path)
    keep = await records.add("ship the memory v2 feature")
    drop = await records.add("ship the memory v1 feature")

    # Backfill bands keep=high, drop=low (omitted from membership).
    llm = StubLLM(_members((keep.id, "high"), (drop.id, "low")))
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("v2-work", "ship work that is about v2")

    assert len(llm.calls) == 1  # exactly one backfill judge call

    members = await lenses.members("v2-work")
    assert len(llm.calls) == 1  # members() reads the cache; NO extra LLM call
    ids = {r.id for r in members}
    assert keep.id in ids
    assert drop.id not in ids
    await lenses.close()
    await records.close()


async def test_mid_band_is_shown_as_a_member(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("the deploy pipeline might be related")
    llm = StubLLM(_members((rec.id, "mid")))
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("deploy", "deploy pipeline")

    members = await lenses.members("deploy")
    assert {r.id for r in members} == {rec.id}  # mid -> shown
    await lenses.close()
    await records.close()


async def test_judge_ignores_invented_ids(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("real record about cats")
    llm = StubLLM(_members((rec.id, "high"), ("hallucinated-id", "high")))
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("cats", "about cats")

    members = await lenses.members("cats")
    ids = {r.id for r in members}
    assert ids == {rec.id}  # the invented id never made it into the cache
    await lenses.close()
    await records.close()


async def test_members_excludes_superseded_records(tmp_path: Path):
    records = _records(tmp_path)
    old = await records.add("the user works at Acme")
    llm = StubLLM(_members((old.id, "high")))
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("employer", "about the user's employer")

    new = await records.add("the user works at Globex")
    await records.supersede(old.id, new.id)

    members = await lenses.members("employer")
    assert old.id not in {r.id for r in members}  # superseded dropped from the view
    await lenses.close()
    await records.close()


# --- the dreamer hook: score_records into every active lens -------------------


async def test_score_records_adds_new_record_to_active_lens(tmp_path: Path):
    records = _records(tmp_path)
    seed = await records.add("first item about regina")
    # create backfill (1 call) + score_records (1 call) = 2 judge calls total.
    new = await records.add("regina called about the schedule")
    llm = StubLLM(
        _members((seed.id, "high")),       # backfill for "regina"
        _members((new.id, "high")),        # score the new record in
    )
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("regina", "is about Regina")

    await lenses.score_records([new])
    assert len(llm.calls) == 2

    members = await lenses.members("regina")
    assert {r.id for r in members} == {seed.id, new.id}
    await lenses.close()
    await records.close()


async def test_score_records_noop_without_llm(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("anything")
    lenses = _lenses(tmp_path, records, llm=None)
    await lenses.create("x", "any criterion")
    # No LLM -> score_records is a no-op (no crash, no membership written).
    await lenses.score_records([rec])
    await lenses.close()
    await records.close()


# --- update: criterion change re-backfills ------------------------------------


async def test_update_criterion_rescores_membership(tmp_path: Path):
    records = _records(tmp_path)
    a = await records.add("about dogs")
    b = await records.add("about cats")
    # create backfill: only a is high. After criterion change: only b is high.
    llm = StubLLM(
        _members((a.id, "high"), (b.id, "low")),   # backfill for "about dogs"
        _members((a.id, "low"), (b.id, "high")),   # re-backfill for "about cats"
    )
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("pets", "about dogs")

    assert {r.id for r in await lenses.members("pets")} == {a.id}

    await lenses.update("pets", criterion="about cats")
    assert {r.id for r in await lenses.members("pets")} == {b.id}
    assert len(llm.calls) == 2  # one backfill per criterion
    await lenses.close()
    await records.close()


async def test_update_rename_keeps_membership(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("about bugs")
    llm = StubLLM(_members((rec.id, "high")))
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("bugs", "about bugs")

    updated = await lenses.update("bugs", new_name="defects")
    assert updated.name == "defects"
    assert len(llm.calls) == 1  # rename only -> NO re-backfill
    assert {r.id for r in await lenses.members("defects")} == {rec.id}
    await lenses.close()
    await records.close()


# --- no-LLM degradation: members() falls back to raw hybrid search ------------


async def test_members_no_llm_degrades_to_hybrid_search(tmp_path: Path):
    records = _records(tmp_path)
    await records.add("the build is currently broken")
    lenses = _lenses(tmp_path, records, llm=None)
    await lenses.create("broken", "broken")

    members = await lenses.members("broken")
    assert any("broken" in r.text for r in members)  # raw hybrid search, no banding
    await lenses.close()
    await records.close()


async def test_members_missing_lens_returns_empty(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records)
    assert await lenses.members("ghost") == []
    await lenses.close()
    await records.close()


# --- lens PAGE (synthesized overlay) -----------------------------------------


async def test_page_synthesizes_and_caches(tmp_path: Path):
    records = _records(tmp_path)
    r1 = await records.add("the user runs 5k every morning")
    r2 = await records.add("the user lifts on weekends")
    # backfill judge: both members high; then the synthesizer's render call.
    llm = StubLLM(_members((r1.id, "high"), (r2.id, "high")), "## Fitness\n- runs 5k\n- lifts")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("fitness", "the user's fitness habits")

    page = await lenses.page("fitness")
    assert page == "## Fitness\n- runs 5k\n- lifts"
    synth_calls = len(llm.calls)

    # A second read is a cache hit — no extra LLM call.
    again = await lenses.page("fitness")
    assert again == page
    assert len(llm.calls) == synth_calls
    await lenses.close()
    await records.close()


async def test_page_none_when_no_members(tmp_path: Path):
    records = _records(tmp_path)
    llm = StubLLM(_members())  # backfill finds nothing
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("empty", "nothing matches this")
    assert await lenses.page("empty") is None
    await lenses.close()
    await records.close()


async def test_page_refresh_re_synthesizes(tmp_path: Path):
    records = _records(tmp_path)
    r1 = await records.add("a member record")
    llm = StubLLM(_members((r1.id, "high")), "first render", "second render")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("v", "matches the member record")

    assert await lenses.page("v") == "first render"
    assert await lenses.page("v", refresh=True) == "second render"
    await lenses.close()
    await records.close()


async def test_page_no_llm_falls_back_to_raw_list(tmp_path: Path):
    records = _records(tmp_path)
    await records.add("the build is broken")
    lenses = _lenses(tmp_path, records, llm=None)
    await lenses.create("broken", "broken")
    page = await lenses.page("broken")
    assert page is not None
    assert "the build is broken" in page  # raw bulleted fallback
    await lenses.close()
    await records.close()
