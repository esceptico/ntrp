"""run_memory_init integration pass (ntrp/memory/init.py P2.5) + curator.ingest_items.

Phase 2-3 = re-derive memory from the connected INTEGRATIONS (calendar, gmail,
slack) in addition to chat transcripts. Hermetic: stubbed integration clients
returning RawItems, the StubLLM curator pattern (deterministic ADD ops), a stub
sessions store, and a real tmp RecordStore (search_index=None -> FTS-only). The
whole memory lives in a tmp sqlite so ~/.ntrp is never touched; no network.

Proves:
  (a) curator.ingest_items routes calendar RawItems to source_ref.kind=="calendar"
      + scope_kind=="integration" (scopes.py routing, end to end);
  (b) gmail's pre-LLM label filter drops CATEGORY_PROMOTIONS BEFORE the LLM;
  (c) a slack client raising a missing-scope error is recorded as {error} while
      transcripts + other sources still complete;
  (d) max_llm_calls caps the total across transcripts + integrations (capped).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ntrp.memory.curator import Curator
from ntrp.memory.records import RecordStore
from ntrp.search.types import RawItem
from tests.conftest import completion_response
from tests.test_memory_curator import StubSessions, _scope, _turn
from tests.test_memory_init import ConsolidateStubLLM, FakeConfig, FakeKnowledge

pytestmark = pytest.mark.asyncio


def _raw(source: str, source_id: str, title: str, content: str, **metadata) -> RawItem:
    now = datetime.now(tz=UTC)
    return RawItem(
        source=source,
        source_id=source_id,
        title=title,
        content=content,
        created_at=now,
        updated_at=now,
        metadata=metadata,
    )


class CountingCuratorLLM:
    """Curator LLM: emits one ADD per call (FIFO over distinct texts), then
    empty ops. Records every call so a test can assert the budget ceiling."""

    def __init__(self, *texts: str):
        self._texts = list(texts)
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, reasoning_effort=None, **kwargs):
        self.calls.append({"messages": messages, "model": model})
        if self._texts:
            text = self._texts.pop(0)
            body = json.dumps({"records": [{"op": "ADD", "text": text, "kind": "fact"}]})
        else:
            body = json.dumps({"records": []})
        return completion_response(body)


class StubCalendar:
    def __init__(self, items: list[RawItem]):
        self._items = items
        self.past_calls: list[int] = []

    def get_past(self, days: int = 7, limit: int = 20) -> list[RawItem]:
        self.past_calls.append(days)
        return list(self._items)


class StubGmail:
    def __init__(self, items: list[RawItem]):
        self._items = items
        self.queries: list[str] = []

    def search(self, query: str, limit: int = 50) -> list[RawItem]:
        self.queries.append(query)
        return list(self._items)


class StubSlackMissingScope:
    async def list_dms(self, limit: int = 50):
        raise RuntimeError("Slack conversations.list failed: missing_scope — needs scope: im:read [user token]")


def _make_curator(records: RecordStore, sessions, llm, db_path: Path) -> Curator:
    return Curator(llm, sessions, model="memory-model", db_path=db_path, record_store=records)


# -- (a) calendar ingest routes to the integration scope ---------------------


async def test_ingest_items_routes_calendar_to_integration_scope(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    records = RecordStore(db_path, search_index=None)
    await records.open()

    items = [
        _raw("calendar", "ev1", "1:1 with Regina", "Time: 2026-06-10 10:00\nDiscuss MATS roadmap"),
        _raw("calendar", "ev2", "Dentist", "Time: 2026-06-12 09:00"),
        _raw("calendar", "ev3", "Team offsite", "Time: 2026-06-15 all day\nQuarterly planning"),
    ]
    llm = CountingCuratorLLM("the user has a recurring 1:1 with Regina about MATS")
    curator = _make_curator(records, StubSessions(), llm, db_path)

    result = await curator.ingest_items(items, source_kind="calendar", source_label="NEW DOCUMENTS")

    assert result["admitted"] == 1
    assert result["calls"] == 1
    assert result["capped"] is False

    # The written record carries the calendar source AND the integration scope.
    active = await records.list(limit=None)
    minted = [r for r in active if "Regina" in r.text]
    assert len(minted) == 1
    rec = minted[0]
    assert rec.scope_kind == "integration"
    assert rec.source_ref is not None
    assert rec.source_ref.kind == "calendar"
    assert rec.source_ref.scope_kind == "integration"

    # All 3 events rendered into the single batch -> one LLM call, header used.
    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert "NEW DOCUMENTS" in user_prompt
    assert "1:1 with Regina" in user_prompt

    await curator.stop()
    await records.close()


# -- (b) gmail noise filter drops promotions BEFORE the LLM ------------------


async def test_run_memory_init_gmail_filters_promotions_before_llm(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    records = RecordStore(db_path, search_index=None)
    await records.open()

    promo = _raw(
        "gmail", "m_promo", "50% OFF EVERYTHING", "Shop now!!!", labels=["CATEGORY_PROMOTIONS", "INBOX"]
    )
    real = _raw(
        "gmail", "m_real", "Re: O-1A petition", "Your attorney needs the recommendation letters by Friday.",
        labels=["INBOX", "IMPORTANT"],
    )
    gmail = StubGmail([promo, real])

    sessions = StubSessions(rows={}, scopes=[])  # no transcripts; integration-only
    llm = CountingCuratorLLM("the user's O-1A attorney needs recommendation letters by Friday")
    curator = _make_curator(records, sessions, llm, db_path)
    consolidate = ConsolidateStubLLM()
    from ntrp.memory.consolidate import Consolidate

    cons = Consolidate(records, consolidate, model="memory-model", db_path=db_path)
    config = FakeConfig(db_path, tmp_path / "artifacts")
    knowledge = FakeKnowledge(records, curator, cons, config)

    report = await import_run_memory_init()(
        knowledge,
        max_llm_calls=50,
        integration_clients={"gmail": gmail},
    )

    # Only the real message survived the pre-LLM filter -> exactly one batch /
    # one curator call. The promo never reached the LLM.
    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert "O-1A petition" in user_prompt
    assert "50% OFF" not in user_prompt
    assert "Shop now" not in user_prompt

    assert report["integrations"]["gmail"]["admitted"] == 1
    assert gmail.queries == ["newer_than:30d"]  # default gmail window

    await cons.close()
    await curator.stop()
    await records.close()


# -- (c) a slack missing-scope error degrades that source, run still completes


async def test_run_memory_init_slack_missing_scope_is_isolated(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    records = RecordStore(db_path, search_index=None)
    await records.open()

    # A real chat session + a healthy calendar + a broken slack.
    sessions = StubSessions(
        rows={"chat1": [_turn(0, "user", "I always prefer green tea")]},
        scopes=[_scope("chat1")],
    )
    calendar = StubCalendar([_raw("calendar", "ev1", "Standup", "Time: 2026-06-10 09:00")])
    slack = StubSlackMissingScope()

    llm = CountingCuratorLLM(
        "the user prefers green tea",  # transcript
        "the user has a daily standup at 9am",  # calendar
    )
    curator = _make_curator(records, sessions, llm, db_path)
    from ntrp.memory.consolidate import Consolidate

    cons = Consolidate(records, ConsolidateStubLLM(), model="memory-model", db_path=db_path)
    config = FakeConfig(db_path, tmp_path / "artifacts")
    knowledge = FakeKnowledge(records, curator, cons, config)

    report = await import_run_memory_init()(
        knowledge,
        max_llm_calls=50,
        integration_clients={"calendar": calendar, "slack": slack},
    )

    # Slack failed but is recorded with an error; calendar + transcript succeeded.
    assert "error" in report["integrations"]["slack"]
    assert "missing_scope" in report["integrations"]["slack"]["error"]
    assert report["integrations"]["calendar"]["admitted"] == 1
    assert report["sessions_processed"] == 1
    assert report["admitted"] >= 2  # transcript + calendar

    texts = {r.text for r in await records.list(limit=None)}
    assert "the user prefers green tea" in texts
    assert "the user has a daily standup at 9am" in texts

    await cons.close()
    await curator.stop()
    await records.close()


# -- (d) the shared budget caps transcripts + integrations -------------------


async def test_run_memory_init_budget_caps_across_transcripts_and_integrations(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    records = RecordStore(db_path, search_index=None)
    await records.open()

    # One transcript turn (1 call) + a calendar with many events. Budget of 1
    # should spend it on the transcript, leaving 0 for calendar -> capped.
    sessions = StubSessions(
        rows={"chat1": [_turn(0, "user", "fact one")]},
        scopes=[_scope("chat1")],
    )
    calendar = StubCalendar([_raw("calendar", f"ev{i}", f"Event {i}", "x" * 100) for i in range(20)])

    llm = CountingCuratorLLM(*[f"derived fact {i}" for i in range(10)])
    curator = _make_curator(records, sessions, llm, db_path)
    from ntrp.memory.consolidate import Consolidate

    cons = Consolidate(records, ConsolidateStubLLM(), model="memory-model", db_path=db_path)
    config = FakeConfig(db_path, tmp_path / "artifacts")
    knowledge = FakeKnowledge(records, curator, cons, config)

    report = await import_run_memory_init()(
        knowledge,
        max_llm_calls=1,
        integration_clients={"calendar": calendar},
    )

    assert report["capped"] is True
    # Exactly one curator call total — the budget was exhausted on the transcript.
    assert len(llm.calls) == 1
    # Calendar got the remaining budget of 0 -> capped, zero calls, zero admitted.
    assert report["integrations"]["calendar"] == {"admitted": 0, "calls": 0, "capped": True}

    await cons.close()
    await curator.stop()
    await records.close()


def import_run_memory_init():
    from ntrp.memory.init import run_memory_init

    return run_memory_init
