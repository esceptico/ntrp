"""LensStore v2 — saved natural-language queries over the flat record pool,
evaluated in the BACKGROUND, read from cache (ntrp/memory/lenses.py).

create() is an instant INSERT that KICKS a background evaluate+render; a
criterion edit does the same. members()/page() are CACHE-ONLY — no read path
ever pays an LLM call; status() reports an in-flight kick. promote_to_label()
graduates the CACHED membership into a record label. Hermetic: a real tmp
`memory.db` backs both records and the lens tables; a real RecordStore
(`search_index=None` -> FTS-only) supplies candidates; a scripted StubLLM locks
the judge/synth cost by call-count. Tests make the background work deterministic
with `await lenses.wait()`.
"""

import asyncio
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
        self.gate: asyncio.Event | None = None  # set by tests that probe status()

    async def completion(self, *, messages, model, reasoning_effort=None, **kwargs):
        if self.gate is not None:
            await self.gate.wait()
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


# --- create: instant INSERT + background kick ---------------------------------


async def test_create_is_instant_and_kicks_background_eval(tmp_path: Path):
    records = _records(tmp_path)
    keep = await records.add("ship the memory v2 feature")
    llm = StubLLM(_members((keep.id, "high")), "## V2\n- ship memory v2")
    lenses = _lenses(tmp_path, records, llm=llm)

    lens = await lenses.create("v2-work", "ship work that is about v2")
    assert lens.id
    assert lens.promoted_to is None  # the request itself never awaited the LLM

    await lenses.wait()  # background kick: ONE judge + ONE page synth
    assert len(llm.calls) == 2
    assert {r.id for r in await lenses.members("v2-work")} == {keep.id}
    assert await lenses.page("v2-work") == "## V2\n- ship memory v2"

    # Reads after the kick are pure cache — no further LLM calls.
    await lenses.members("v2-work")
    await lenses.page("v2-work")
    assert len(llm.calls) == 2
    await lenses.close()
    await records.close()


async def test_status_reports_generating_then_idle(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("a record about cats")
    llm = StubLLM(_members((rec.id, "high")), "page")
    llm.gate = asyncio.Event()  # hold the judge call open
    lenses = _lenses(tmp_path, records, llm=llm)

    lens = await lenses.create("cats", "about cats")
    await asyncio.sleep(0)  # let the kicked task reach the gated LLM call
    assert lenses.status(lens.id) == "generating"

    llm.gate.set()
    await lenses.wait()
    assert lenses.status(lens.id) == "idle"
    assert await lenses.page("cats") == "page"
    await lenses.close()
    await records.close()


async def test_list_returns_all(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records)

    await lenses.create("a", "first criterion")
    await lenses.create("b", "second criterion")

    names = [lens.name for lens in await lenses.list()]
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
    llm = StubLLM(_members((rec.id, "high")), "page")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("temp", "shipping work")
    await lenses.wait()  # membership cached

    assert await lenses.delete("temp") is True
    assert await lenses.get("temp") is None
    assert await lenses.delete("temp") is False  # already gone
    # The record survives a lens deletion.
    assert await records.get(rec.id) is not None
    await lenses.close()
    await records.close()


# --- members(): CACHE-ONLY ------------------------------------------------------


async def test_members_is_cache_only_while_kick_is_in_flight(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("ship the memory v2 feature")
    llm = StubLLM(_members((rec.id, "high")), "page")
    llm.gate = asyncio.Event()  # hold the kicked judge call open
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("v2-work", "ship work that is about v2")
    await asyncio.sleep(0)

    # A read mid-kick serves the (empty) cache and triggers NO LLM work itself.
    assert await lenses.members("v2-work") == []
    assert llm.calls == []

    llm.gate.set()
    await lenses.wait()
    assert {r.id for r in await lenses.members("v2-work")} == {rec.id}
    await lenses.close()
    await records.close()


async def test_low_band_is_omitted_mid_is_shown(tmp_path: Path):
    records = _records(tmp_path)
    keep = await records.add("the deploy pipeline might be related")
    drop = await records.add("the deploy pipeline of another org")
    llm = StubLLM(_members((keep.id, "mid"), (drop.id, "low")), "page")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("deploy", "deploy pipeline")
    await lenses.wait()

    members = await lenses.members("deploy")
    assert {r.id for r in members} == {keep.id}  # mid -> shown, low -> omitted
    await lenses.close()
    await records.close()


async def test_evaluate_never_invents_ids(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("real record about cats")
    llm = StubLLM(_members((rec.id, "high"), ("hallucinated-id", "high")), "page")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("cats", "about cats")
    await lenses.wait()

    assert {r.id for r in await lenses.members("cats")} == {rec.id}
    conn = await lenses._ensure_conn()
    rows = await conn.execute_fetchall("SELECT record_id FROM lens_members")
    assert {r["record_id"] for r in rows} == {rec.id}  # never cached either
    await lenses.close()
    await records.close()


async def test_evaluate_replaces_cache(tmp_path: Path):
    records = _records(tmp_path)
    a = await records.add("note about dogs")
    b = await records.add("note about cats")
    llm = StubLLM(
        _members((a.id, "high"), (b.id, "low")), "page one",
        _members((a.id, "low"), (b.id, "high")),
    )
    lenses = _lenses(tmp_path, records, llm=llm)
    lens = await lenses.create("pets", "about dogs")
    await lenses.wait()
    assert {r.id for r in await lenses.members("pets")} == {a.id}

    rescored = await lenses.evaluate(lens)  # the background worker, called direct
    assert {r.id for r in rescored} == {b.id}  # cache REPLACED, not unioned
    assert {r.id for r in await lenses.members("pets")} == {b.id}
    await lenses.close()
    await records.close()


async def test_judge_failure_keeps_old_cache(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("the build is broken")
    llm = StubLLM(_members((rec.id, "high")), "page", "this is not json")
    lenses = _lenses(tmp_path, records, llm=llm)
    lens = await lenses.create("broken", "broken builds")
    await lenses.wait()
    assert {r.id for r in await lenses.members("broken")} == {rec.id}

    members = await lenses.evaluate(lens)  # judge returns garbage
    assert {r.id for r in members} == {rec.id}  # old cache kept + returned
    await lenses.close()
    await records.close()


async def test_members_excludes_superseded_records(tmp_path: Path):
    records = _records(tmp_path)
    note = await records.add("a note about acme culture")
    old = await records.add("the user works at acme")
    llm = StubLLM(_members((note.id, "high"), (old.id, "high")), "page")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("acme", "about acme")
    await lenses.wait()  # cache both

    new = await records.add("the user works at globex")
    await records.supersede(old.id, new.id)

    members = await lenses.members("acme")
    assert {r.id for r in members} == {note.id}  # superseded dropped from the view
    assert len(llm.calls) == 2  # cache-only read -> no re-evaluate
    await lenses.close()
    await records.close()


async def test_members_missing_lens_returns_empty(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records)
    assert await lenses.members("ghost") == []
    await lenses.close()
    await records.close()


# --- update: criterion edit clears the cache + kicks; rename does neither ------


async def test_update_criterion_kicks_background_reevaluate(tmp_path: Path):
    records = _records(tmp_path)
    a = await records.add("note about dogs")
    b = await records.add("note about cats")
    llm = StubLLM(
        _members((a.id, "high"), (b.id, "low")), "dogs page",
        _members((a.id, "low"), (b.id, "high")), "cats page",
    )
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("pets", "about dogs")
    await lenses.wait()
    assert {r.id for r in await lenses.members("pets")} == {a.id}
    assert len(llm.calls) == 2

    updated = await lenses.update("pets", criterion="about cats")
    assert updated.criterion == "about cats"
    await lenses.wait()  # the edit kicked a background re-derive
    assert {r.id for r in await lenses.members("pets")} == {b.id}
    assert await lenses.page("pets") == "cats page"
    assert len(llm.calls) == 4
    await lenses.close()
    await records.close()


async def test_update_rename_keeps_cache_and_does_not_kick(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("about bugs")
    llm = StubLLM(_members((rec.id, "high")), "page")
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("bugs", "about bugs")
    await lenses.wait()

    updated = await lenses.update("bugs", new_name="defects")
    await lenses.wait()
    assert updated.name == "defects"
    assert {r.id for r in await lenses.members("defects")} == {rec.id}
    assert len(llm.calls) == 2  # rename only -> cache untouched, no re-evaluate
    await lenses.close()
    await records.close()


# --- no-LLM degradation: evaluation falls back to raw hybrid search -----------


async def test_no_llm_kick_degrades_to_hybrid_search_and_raw_page(tmp_path: Path):
    records = _records(tmp_path)
    await records.add("the build is currently broken")
    lenses = _lenses(tmp_path, records, llm=None)
    await lenses.create("broken", "broken")
    await lenses.wait()

    members = await lenses.members("broken")
    assert any("broken" in r.text for r in members)  # raw hybrid search, no banding
    page = await lenses.page("broken")
    assert page is not None
    assert "the build is currently broken" in page  # raw bulleted fallback
    await lenses.close()
    await records.close()


# --- page: cache-only ----------------------------------------------------------


async def test_page_none_when_nothing_matches(tmp_path: Path):
    records = _records(tmp_path)
    llm = StubLLM()
    lenses = _lenses(tmp_path, records, llm=llm)
    await lenses.create("empty", "nothing matches this")
    await lenses.wait()
    assert await lenses.page("empty") is None
    assert llm.calls == []  # no candidates -> no judge, no synth
    await lenses.close()
    await records.close()


async def test_page_read_never_synthesizes(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("a member record")
    llm = StubLLM(_members((rec.id, "high")), "render")
    lenses = _lenses(tmp_path, records, llm=llm)
    lens = await lenses.create("v", "matches the member record")
    await lenses.wait()
    assert await lenses.page("v") == "render"
    calls = len(llm.calls)

    # Dirty the page (a write-back does this); the READ must NOT re-synthesize.
    conn = await lenses._ensure_conn()
    await conn.execute("UPDATE lenses SET page = NULL WHERE id = ?", (lens.id,))
    await conn.commit()
    assert await lenses.page("v") is None
    assert len(llm.calls) == calls
    await lenses.close()
    await records.close()


# --- promote_to_label: tags the CACHED membership ------------------------------


async def test_promote_to_label_tags_cached_members_and_marks_lens(tmp_path: Path):
    records = _records(tmp_path)
    r1 = await records.add("the user runs 5k every morning")
    r2 = await records.add("the user lifts on weekends")
    llm = StubLLM(_members((r1.id, "high"), (r2.id, "mid")), "page")
    lenses = _lenses(tmp_path, records, llm=llm)
    lens = await lenses.create("fitness", "the user's fitness habits")
    await lenses.wait()
    calls = len(llm.calls)

    count = await lenses.promote_to_label(lens.id, "fitness")
    assert count == 2
    assert len(llm.calls) == calls  # promotes the cache — NO LLM in the request

    assert await records.labels_of(r1.id) == ["fitness"]
    assert await records.labels_of(r2.id) == ["fitness"]
    promoted = await lenses.get_by_id(lens.id)
    assert promoted.promoted_to == "fitness"  # marked, still viewable
    await lenses.close()
    await records.close()


async def test_promote_without_evaluated_members_raises(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records, llm=StubLLM())
    lens = await lenses.create("empty", "matches nothing in the pool")
    await lenses.wait()
    with pytest.raises(ValueError):
        await lenses.promote_to_label(lens.id, "label")
    await lenses.close()
    await records.close()


async def test_promote_missing_lens_raises(tmp_path: Path):
    records = _records(tmp_path)
    lenses = _lenses(tmp_path, records)
    with pytest.raises(ValueError):
        await lenses.promote_to_label("no-such-id", "label")
    await lenses.close()
    await records.close()


# --- open-time hygiene: stale cache rows + corrupted criteria ------------------


async def test_open_cleans_stale_member_rows(tmp_path: Path):
    records = _records(tmp_path)
    rec = await records.add("the user works at acme")
    llm = StubLLM(_members((rec.id, "high")), "page")
    store1 = _lenses(tmp_path, records, llm=llm)
    await store1.create("employer", "the user's employer")
    await store1.wait()  # cache {rec}
    new = await records.add("the user works at globex")
    await records.supersede(rec.id, new.id)
    await store1.close()

    store2 = _lenses(tmp_path, records)
    conn = await store2._ensure_conn()  # open runs the cleanup
    rows = await conn.execute_fetchall("SELECT record_id FROM lens_members")
    assert rows == []  # the superseded record's row is gone
    await store2.close()
    await records.close()


async def test_open_repairs_markdown_criterion(tmp_path: Path):
    records = _records(tmp_path)
    store1 = _lenses(tmp_path, records)
    lens = await store1.create("dex", "placeholder")
    conn = await store1._ensure_conn()
    # The old draft path stored the template body verbatim as the criterion.
    await conn.execute(
        "UPDATE lenses SET criterion = ? WHERE id = ?",
        ("## Belongs\nRecords about Dex.", lens.id),
    )
    await conn.commit()
    await store1.close()

    store2 = _lenses(tmp_path, records)
    repaired = await store2.get("dex")
    assert repaired.criterion == "Records about Dex."  # headings stripped
    await store2.close()
    await records.close()


async def test_open_repairs_heading_only_criterion_to_name_fallback(tmp_path: Path):
    records = _records(tmp_path)
    store1 = _lenses(tmp_path, records)
    lens = await store1.create("dex", "placeholder")
    conn = await store1._ensure_conn()
    await conn.execute(
        "UPDATE lenses SET criterion = ? WHERE id = ?", ("## Belongs", lens.id)
    )
    await conn.commit()
    await store1.close()

    store2 = _lenses(tmp_path, records)
    repaired = await store2.get("dex")
    assert repaired.criterion == "Records about dex."  # no prose left -> name fallback
    await store2.close()
    await records.close()
