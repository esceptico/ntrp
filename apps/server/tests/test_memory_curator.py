"""Curator (the Dreamer) — the sleep-time memory writer (ntrp/memory/curator.py).

ONE LLM call per session emits a SINGLE JSON object `{"records": [ADD|UPDATE|
SUPERSEDE|NOOP ...]}`: it reconciles the flat record pool, then scores the new
records into the active lenses. No docs, no scope. Hermetic: a STUB LLM (scripted
single-call JSON responses) + a STUB sessions store (in-memory `messages_since`) +
a real tmp RecordStore + a real tmp LensStore (`search_index=None` -> FTS-only).
The watermark + records live in a tmp sqlite (injected via the Curator's `db_path`
arg so the real ~/.ntrp/memory.db is never touched).

Covers:
  (a) empty ops (novelty gate) -> no record writes, watermark advances;
  (b) the watermark filters already-seen seqs;
  (c) a content-less completion -> no writes, watermark NOT advanced;
  (d) record ops: ADD inserts, UPDATE edits+confirms, SUPERSEDE closes+inserts,
      NOOP confirms — exactly one LLM call per curation;
  (e) new records get scored into active lenses (the dreamer's membership half);
  (f) the sweep schedules curation for recent sessions.
"""

import asyncio
import json
from pathlib import Path

import pytest

from ntrp.memory.curator import Curator
from ntrp.memory.lenses import LensStore
from ntrp.memory.records import RecordStore
from tests.conftest import completion_response

pytestmark = pytest.mark.asyncio


class StubLLM:
    """Scripted completion client: returns queued payloads (FIFO) and records
    every call so a test can assert the cost ceiling (one call per curation)."""

    def __init__(self, *responses: str):
        self._queue = list(responses)
        self.calls: list[dict] = []

    async def completion(self, *, messages, model, reasoning_effort=None, **kwargs):
        self.calls.append(
            {"messages": messages, "model": model, "reasoning_effort": reasoning_effort}
        )
        body = self._queue.pop(0) if self._queue else ""
        return completion_response(body)


class StubSessions:
    """Minimal SessionService stand-in. Holds ordered transcript rows in the
    `_message_row_payload` shape (seq/role/message) and serves messages_since.
    `scopes` is the preset {session_id, project_id} worklist for the sweep."""

    def __init__(self, rows: dict[str, list[dict]] | None = None, scopes: list[dict] | None = None):
        self._rows = rows or {}
        self._scopes = scopes or []

    def set_rows(self, session_id: str, rows: list[dict]) -> None:
        self._rows[session_id] = rows

    async def messages_since(self, session_id: str, seq: int) -> list[dict]:
        return [r for r in self._rows.get(session_id, []) if r["seq"] > seq]

    async def recent_session_scopes(self, limit: int) -> list[dict]:
        return self._scopes[:limit]


def _turn(seq: int, role: str, text: str) -> dict:
    return {"seq": seq, "role": role, "message": {"role": role, "content": text}}


def _ops_json(records: list[dict] | None = None) -> str:
    """The single JSON object the Curator now expects from the LLM."""
    return json.dumps({"records": records or []})


def _make_curator(tmp_path: Path, llm, sessions) -> tuple[Curator, RecordStore, LensStore]:
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    lenses = LensStore(tmp_path / "memory.db", records, llm=None)  # no lens scoring by default
    curator = Curator(
        llm,
        sessions,
        model="memory-model",
        db_path=tmp_path / "memory.db",
        record_store=records,
        lens_store=lenses,
    )
    return curator, records, lenses


# --- novelty gate / watermark -------------------------------------------------


async def test_empty_ops_skip_writes_but_advance_watermark(tmp_path: Path):
    llm = StubLLM(_ops_json([]))
    sessions = StubSessions({"s1": [_turn(0, "user", "what time is it")]})
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    await curator.curate_session("s1")

    assert len(llm.calls) == 1  # the gate ran once, then declined
    assert await records.list() == []  # no record writes
    assert await curator._read_watermark("s1") == 0  # advanced to max seq seen
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_watermark_filters_already_seen_seqs(tmp_path: Path):
    llm = StubLLM(
        _ops_json([{"op": "ADD", "text": "captured fact"}]),
        _ops_json([{"op": "ADD", "text": "should not be reached"}]),
    )
    sessions = StubSessions(
        {
            "s1": [
                _turn(0, "user", "old turn already curated"),
                _turn(1, "user", "brand new durable fact"),
            ]
        }
    )
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    await curator._write_watermark("s1", 0)  # pretend seq 0 already curated

    changed = await curator.curate_session("s1")
    assert changed is True

    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["messages"][1]["content"]
    assert "brand new durable fact" in user_prompt
    assert "old turn already curated" not in user_prompt
    assert await curator._read_watermark("s1") == 1
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_curator_ignores_system_rows(tmp_path: Path):
    llm = StubLLM(_ops_json([]))
    sessions = StubSessions(
        {
            "s1": [
                _turn(0, "system", "large repeated system prompt should not enter memory"),
                _turn(1, "user", "I prefer tea"),
            ]
        }
    )
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    await curator.curate_session("s1")

    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["messages"][1]["content"]
    assert "I prefer tea" in user_prompt
    assert "large repeated system prompt" not in user_prompt
    assert await curator._read_watermark("s1") == 1
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_curator_chunks_large_backlog_before_llm(tmp_path: Path):
    llm = StubLLM(_ops_json([]))
    rows = [_turn(i, "user", f"fact {i} " + ("x" * 1000)) for i in range(20)]
    sessions = StubSessions({"s1": rows})
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    await curator.curate_session("s1")

    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["messages"][1]["content"]
    assert len(user_prompt) < 8_000
    assert await curator._read_watermark("s1") < rows[-1]["seq"]
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_no_new_turns_advances_without_llm(tmp_path: Path):
    llm = StubLLM(_ops_json([{"op": "ADD", "text": "never called"}]))
    sessions = StubSessions({"s1": [_turn(5, "user", "hello")]})
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)
    await curator._write_watermark("s1", 5)  # everything already seen

    changed = await curator.curate_session("s1")

    assert changed is False
    assert llm.calls == []  # the novelty gate never even spent an LLM call
    assert await curator._read_watermark("s1") == 5
    await curator.stop()
    await lenses.close()
    await records.close()


@pytest.mark.parametrize("blank", ["", "   ", "\n\n"])
async def test_empty_completion_does_not_write_or_advance(tmp_path: Path, blank: str):
    """A content-less but non-erroring completion must NOT write records or advance
    the watermark — the turns retry next session."""
    llm = StubLLM(blank)
    sessions = StubSessions({"s1": [_turn(0, "user", "some durable new fact")]})
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    changed = await curator.curate_session("s1")

    assert changed is False
    assert len(llm.calls) == 1  # the call happened…
    assert await records.list() == []  # …no record writes
    assert await curator._read_watermark("s1") == -1  # NOT advanced -> retried
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_unparseable_completion_does_not_advance(tmp_path: Path):
    llm = StubLLM("not json at all")
    sessions = StubSessions({"s1": [_turn(0, "user", "a durable fact")]})
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    changed = await curator.curate_session("s1")

    assert changed is False
    assert await records.list() == []
    assert await curator._read_watermark("s1") == -1
    await curator.stop()
    await lenses.close()
    await records.close()


# --- record ops: ADD / UPDATE / SUPERSEDE / NOOP ------------------------------


async def test_add_op_inserts_a_record(tmp_path: Path):
    llm = StubLLM(_ops_json([{"op": "ADD", "text": "the user uses Linux", "kind": "fact"}]))
    sessions = StubSessions({"s1": [_turn(0, "user", "I run Linux")]})
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    changed = await curator.curate_session("s1")

    assert changed is True
    assert len(llm.calls) == 1
    rows = await records.list()
    assert [r.text for r in rows] == ["the user uses Linux"]
    assert rows[0].kind == "fact"
    # Dreamer-written records carry curator provenance.
    assert rows[0].source_ref is not None
    assert rows[0].source_ref.kind == "curator"
    assert rows[0].source_ref.ref == "s1"
    assert await curator._read_watermark("s1") == 0
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_update_op_edits_and_confirms(tmp_path: Path):
    curator, records, lenses = _make_curator(tmp_path, StubLLM(), StubSessions())
    existing = await records.add("the user lives in Berlin")
    before = (await records.get(existing.id)).last_confirmed_at

    llm = StubLLM(_ops_json([{"op": "UPDATE", "id": existing.id, "text": "the user lives in Munich"}]))
    sessions = StubSessions({"s1": [_turn(0, "user", "I moved to Munich")]})
    curator2 = Curator(
        llm, sessions, model="memory-model",
        db_path=tmp_path / "memory.db", record_store=records, lens_store=lenses,
    )
    await asyncio.sleep(0.01)

    changed = await curator2.curate_session("s1")

    assert changed is True
    got = await records.get(existing.id)
    assert got.text == "the user lives in Munich"
    assert got.last_confirmed_at > before
    assert len(llm.calls) == 1
    await curator2.stop()
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_supersede_op_closes_old_and_inserts_new(tmp_path: Path):
    curator, records, lenses = _make_curator(tmp_path, StubLLM(), StubSessions())
    old = await records.add("the user works at Acme")

    llm = StubLLM(
        _ops_json([{"op": "SUPERSEDE", "id": old.id, "text": "the user works at Globex", "kind": "fact"}])
    )
    sessions = StubSessions({"s1": [_turn(0, "user", "I switched jobs to Globex")]})
    curator2 = Curator(
        llm, sessions, model="memory-model",
        db_path=tmp_path / "memory.db", record_store=records, lens_store=lenses,
    )

    changed = await curator2.curate_session("s1")

    assert changed is True
    closed = await records.get(old.id)
    assert closed.superseded_by is not None
    active = await records.list()  # list excludes superseded
    assert [r.text for r in active] == ["the user works at Globex"]
    assert closed.superseded_by == active[0].id
    assert active[0].kind == "fact"
    assert len(llm.calls) == 1
    await curator2.stop()
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_noop_op_confirms_existing(tmp_path: Path):
    curator, records, lenses = _make_curator(tmp_path, StubLLM(), StubSessions())
    existing = await records.add("the user prefers dark mode")
    before = (await records.get(existing.id)).last_confirmed_at

    llm = StubLLM(_ops_json([{"op": "NOOP", "id": existing.id}]))
    sessions = StubSessions({"s1": [_turn(0, "user", "still on dark mode")]})
    curator2 = Curator(
        llm, sessions, model="memory-model",
        db_path=tmp_path / "memory.db", record_store=records, lens_store=lenses,
    )
    await asyncio.sleep(0.01)

    changed = await curator2.curate_session("s1")

    assert changed is True
    got = await records.get(existing.id)
    assert got.text == "the user prefers dark mode"
    assert got.last_confirmed_at > before  # reconfirmed
    assert got.superseded_by is None
    assert len(llm.calls) == 1
    await curator2.stop()
    await curator.stop()
    await lenses.close()
    await records.close()


# --- the dreamer also maintains lens membership -------------------------------


async def test_new_records_are_scored_into_active_lenses(tmp_path: Path):
    """ADD'd records get routed into an active lens by the dreamer. The lens store
    has its OWN LLM (the judge); the curator's LLM emits the ops."""
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    lens_llm = StubLLM()  # filled after we know the new record id (see below)
    lenses = LensStore(tmp_path / "memory.db", records, llm=lens_llm, model="lens-model")

    # Backfill the lens (empty pool) -> 1 judge call returning no members.
    lens_llm._queue.append(json.dumps({"members": []}))
    await lenses.create("linux", "about Linux usage")

    curator_llm = StubLLM(_ops_json([{"op": "ADD", "text": "the user uses Linux", "kind": "fact"}]))
    sessions = StubSessions({"s1": [_turn(0, "user", "I run Linux")]})
    curator = Curator(
        curator_llm, sessions, model="memory-model",
        db_path=tmp_path / "memory.db", record_store=records, lens_store=lenses,
    )

    # Queue the judge's banding for the new record: it'll be high (a member).
    # The new record's id isn't known yet, so script the judge to echo whatever
    # candidate it's handed as high.
    class EchoHighLLM:
        def __init__(self):
            self.calls = 0

        async def completion(self, *, messages, model, reasoning_effort=None, **kwargs):
            self.calls += 1
            payload = messages[1]["content"]
            # Extract candidate ids from the JSON the judge was handed.
            import re
            ids = re.findall(r'"([0-9a-f]{32})"', payload)
            members = [{"id": i, "band": "high"} for i in ids]
            return completion_response(json.dumps({"members": members}))

    lenses._llm = EchoHighLLM()

    changed = await curator.curate_session("s1")
    assert changed is True

    members = await lenses.members("linux")
    assert [r.text for r in members] == ["the user uses Linux"]
    await curator.stop()
    await lenses.close()
    await records.close()


# --- sweep --------------------------------------------------------------------


async def test_sweep_schedules_curation_for_recent_sessions(tmp_path: Path):
    """The sweep schedules curation for every recent session by id (no scope)."""
    llm = StubLLM()
    sessions = StubSessions(
        scopes=[
            {"session_id": "chat1", "project_id": None},
            {"session_id": "auto2", "project_id": "proj_abc"},
            {"session_id": "chat3", "project_id": None},
        ]
    )
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)

    recorded: list[str] = []
    curator.schedule_curation = lambda sid: recorded.append(sid)  # type: ignore[method-assign]

    scheduled = await curator.sweep_once()

    assert scheduled == 3
    assert recorded == ["chat1", "auto2", "chat3"]
    await curator.stop()
    await lenses.close()
    await records.close()


async def test_sweep_curates_only_sessions_with_new_turns(tmp_path: Path):
    """End-to-end: the new-turns session gets curated (one LLM call); the session
    already at its watermark no-ops (no LLM call)."""
    llm = StubLLM(_ops_json([{"op": "ADD", "text": "the user prefers tea"}]))
    sessions = StubSessions(
        rows={
            "fresh": [_turn(0, "user", "I prefer tea")],
            "stale": [_turn(0, "user", "already curated long ago")],
        },
        scopes=[
            {"session_id": "fresh", "project_id": None},
            {"session_id": "stale", "project_id": None},
        ],
    )
    curator, records, lenses = _make_curator(tmp_path, llm, sessions)
    await curator._write_watermark("stale", 0)  # stale is fully up to date

    await curator.sweep_once()
    await asyncio.gather(*curator._tasks.values(), return_exceptions=True)

    assert len(llm.calls) == 1  # only the fresh session spent an LLM call
    assert [r.text for r in await records.list()] == ["the user prefers tea"]
    assert await curator._read_watermark("fresh") == 0
    await curator.stop()
    await lenses.close()
    await records.close()
