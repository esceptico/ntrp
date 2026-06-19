"""run_integration_ingest (ntrp/memory/init.py) — the periodic, NON-destructive,
incremental integration ingest. Per-source watermark advances on each run; a run
with no items newer than the watermark makes ZERO LLM calls. Hermetic: stubbed
clients, the CountingCuratorLLM pattern, a real tmp RecordStore (FTS-only)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ntrp.memory.init import run_integration_ingest
from ntrp.memory.records import RecordStore
from ntrp.search.types import RawItem
from tests.test_memory_curator import StubSessions
from tests.test_memory_init import FakeConfig, FakeKnowledge
from tests.test_memory_init_integrations import CountingCuratorLLM, StubCalendar, _make_curator

pytestmark = pytest.mark.asyncio


def _raw_at(source: str, sid: str, title: str, content: str, ts: datetime, **meta) -> RawItem:
    return RawItem(
        source=source, source_id=sid, title=title, content=content,
        created_at=ts, updated_at=ts, metadata=meta,
    )


async def _knowledge(tmp_path: Path, llm):
    db_path = tmp_path / "memory.db"
    records = RecordStore(db_path, search_index=None)
    await records.open()
    curator = _make_curator(records, StubSessions(), llm, db_path)
    knowledge = FakeKnowledge(records, curator, None, FakeConfig(db_path, tmp_path / "artifacts"))
    return knowledge, curator, records


async def test_incremental_ingest_advances_watermark_and_skips_seen(tmp_path: Path):
    t0 = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
    cal = StubCalendar([
        _raw_at("calendar", "ev1", "1:1 with Regina", "MATS roadmap", t0),
        _raw_at("calendar", "ev2", "Standup", "daily", t0 + timedelta(hours=1)),
    ])
    llm = CountingCuratorLLM("the user has a 1:1 with Regina about MATS")
    knowledge, curator, records = await _knowledge(tmp_path, llm)

    # Run 1: both events are new -> one batch -> one LLM call; watermark set to newest.
    r1 = await run_integration_ingest(knowledge, integration_clients={"calendar": cal})
    assert r1["integrations"]["calendar"]["admitted"] == 1
    assert len(llm.calls) == 1
    assert await curator.read_ingest_watermark("calendar") == (t0 + timedelta(hours=1)).isoformat()

    # Run 2: nothing newer than the watermark -> ZERO new LLM calls.
    r2 = await run_integration_ingest(knowledge, integration_clients={"calendar": cal})
    assert r2["integrations"]["calendar"]["admitted"] == 0
    assert len(llm.calls) == 1  # unchanged

    # Run 3: a newer event arrives -> only it reaches the LLM.
    cal._items.append(_raw_at("calendar", "ev3", "New plan", "Q3 planning", t0 + timedelta(days=1)))
    llm._texts.append("the user is planning Q3")
    await run_integration_ingest(knowledge, integration_clients={"calendar": cal})
    assert len(llm.calls) == 2
    last_prompt = llm.calls[-1]["messages"][-1]["content"]
    assert "New plan" in last_prompt
    assert "1:1 with Regina" not in last_prompt  # already-seen items are not re-sent

    await curator.stop()
    await records.close()


async def test_ingest_is_non_destructive_and_isolates_a_failing_source(tmp_path: Path):
    t0 = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
    cal = StubCalendar([_raw_at("calendar", "ev1", "Standup", "daily", t0)])

    class StubSlackBoom:
        async def list_dms(self, limit: int = 50):
            raise RuntimeError("missing_scope — needs im:read")

    llm = CountingCuratorLLM("the user has a daily standup")
    knowledge, curator, records = await _knowledge(tmp_path, llm)
    # A pre-existing record must survive — ingest only ADDs, never wipes.
    await records.add("the user is named Tim", kind="fact")

    report = await run_integration_ingest(
        knowledge, integration_clients={"calendar": cal, "slack": StubSlackBoom()}
    )

    assert report["integrations"]["calendar"]["admitted"] == 1
    assert "error" in report["integrations"]["slack"]  # isolated, run still completes
    assert "missing_scope" in report["integrations"]["slack"]["error"]
    texts = {r.text for r in await records.list(limit=None)}
    assert "the user is named Tim" in texts  # not wiped

    await curator.stop()
    await records.close()


async def test_reset_watermarks_clears_ingest_watermarks(tmp_path: Path):
    llm = CountingCuratorLLM()
    _knowledge_obj, curator, records = await _knowledge(tmp_path, llm)

    await curator.write_ingest_watermark("gmail", "2026-06-10T00:00:00+00:00")
    assert await curator.read_ingest_watermark("gmail") is not None

    await curator.reset_watermarks()
    assert await curator.read_ingest_watermark("gmail") is None  # /init starts fresh

    await curator.stop()
    await records.close()
