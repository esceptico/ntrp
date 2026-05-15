"""Session store tests — real SQLite, round-trip persistence."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.events.sse import ThinkingEvent
from ntrp.server.bus import StreamRecord


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    read_conn = await database.connect(tmp_path / "sessions.db", readonly=True)
    s = SessionStore(conn, read_conn)
    await s.init_schema()
    yield s
    await read_conn.close()
    await conn.close()


def _make_state(session_id: str = "test-session", name: str | None = None) -> SessionState:
    return SessionState(
        session_id=session_id,
        started_at=datetime.now(UTC),
        name=name,
    )


@pytest.mark.asyncio
async def test_save_and_load_round_trip(store: SessionStore):
    state = _make_state(name="my chat")
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    await store.save_session(state, messages)
    loaded = await store.load_session("test-session")

    assert loaded is not None
    assert loaded.state.session_id == "test-session"
    assert loaded.state.name == "my chat"
    assert len(loaded.messages) == 3
    assert loaded.messages[1]["content"] == "Hello"
    assert loaded.messages[2]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_chat_run_and_queued_message_ledger(store: SessionStore):
    await store.record_chat_run_started("run-1", "sess-1")
    await store.record_chat_queued_message(
        client_id="cid-1",
        session_id="sess-1",
        run_id="run-1",
        message={"role": "user", "content": "follow-up", "client_id": "cid-1"},
    )

    queued = await store.list_chat_queued_messages("sess-1")
    assert [row["client_id"] for row in queued] == ["cid-1"]
    assert queued[0]["status"] == "queued"
    assert queued[0]["message"]["content"] == "follow-up"

    await store.mark_chat_queued_message_ingested("cid-1", ingested_seq=42)
    await store.record_chat_run_status("run-1", "completed", last_seq=99)

    completed = await store.get_chat_run("run-1")
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["last_seq"] == 99
    assert completed["ended_at"] is not None

    queued = await store.list_chat_queued_messages("sess-1")
    assert queued[0]["status"] == "ingested"
    assert queued[0]["ingested_seq"] == 42
    assert queued[0]["ingested_at"] is not None


@pytest.mark.asyncio
async def test_latest_session_checkpoint_uses_chat_run_last_seq(store: SessionStore):
    await store.record_chat_run_started("run-1", "sess-1")
    await store.record_chat_run_status("run-1", "running", last_seq=12)
    await store.record_chat_run_started("run-2", "sess-1")
    await store.record_chat_run_status("run-2", "running")
    await store.record_chat_run_started("run-other", "sess-2")
    await store.record_chat_run_status("run-other", "running", last_seq=99)

    assert await store.get_latest_session_checkpoint_seq("sess-1") == 12
    assert await store.get_latest_session_checkpoint_seq("missing") == 0


@pytest.mark.asyncio
async def test_marks_interrupted_chat_runs_on_startup(store: SessionStore):
    await store.record_chat_run_started("run-1", "sess-1")
    await store.record_chat_run_status("run-1", "running")

    changed = await store.mark_interrupted_chat_runs()
    run = await store.get_chat_run("run-1")

    assert changed == 1
    assert run is not None
    assert run["status"] == "interrupted"
    assert run["stop_reason"] == "server_restart"
    assert run["ended_at"] is not None


@pytest.mark.asyncio
async def test_background_agent_run_lifecycle(store: SessionStore):
    await store.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-1",
        parent_run_id="run-1",
        command="research task",
    )
    await store.record_background_agent_event(
        task_id="bg-1",
        session_id="sess-1",
        status="activity",
        detail="read files",
    )
    await store.record_background_agent_finished(
        task_id="bg-1",
        session_id="sess-1",
        status="completed",
        result_ref="bg_results/bg-1.txt",
        detail="done",
        result_text="full result",
    )

    runs = await store.list_background_agent_runs("sess-1")
    assert runs[0]["task_id"] == "bg-1"
    assert runs[0]["status"] == "completed"
    assert runs[0]["result_ref"] == "bg_results/bg-1.txt"
    assert await store.get_background_agent_result("sess-1", "bg-1") == "full result"

    events = await store.list_background_agent_events("sess-1", after_seq=0)
    assert [e["status"] for e in events] == ["started", "activity", "completed"]
    assert events[-1]["terminal"] is True


@pytest.mark.asyncio
async def test_background_agent_task_ids_are_session_scoped(store: SessionStore):
    await store.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-1",
        parent_run_id="run-1",
        command="first",
    )
    await store.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-2",
        parent_run_id="run-2",
        command="second",
    )

    assert (await store.list_background_agent_runs("sess-1"))[0]["command"] == "first"
    assert (await store.list_background_agent_runs("sess-2"))[0]["command"] == "second"


@pytest.mark.asyncio
async def test_background_agent_cancel_request_is_session_scoped_and_evented(store: SessionStore):
    await store.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-1",
        parent_run_id="run-1",
        command="first",
    )
    await store.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-2",
        parent_run_id="run-2",
        command="second",
    )

    assert await store.request_background_agent_cancel("sess-1", "bg-1") is True

    assert (await store.list_background_agent_runs("sess-1"))[0]["status"] == "cancel_requested"
    assert (await store.list_background_agent_runs("sess-2"))[0]["status"] == "running"
    events = await store.list_background_agent_events("sess-1")
    assert [e["status"] for e in events] == ["started", "cancel_requested"]
    assert events[-1]["terminal"] is False


@pytest.mark.asyncio
async def test_background_agent_schema_migrates_old_task_id_primary_key(tmp_path: Path):
    conn = await database.connect(tmp_path / "old-sessions.db")
    read_conn = await database.connect(tmp_path / "old-sessions.db", readonly=True)
    await conn.execute(
        """
        CREATE TABLE background_agent_runs (
            task_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            parent_run_id TEXT,
            status TEXT NOT NULL,
            command TEXT NOT NULL,
            detail TEXT,
            result_ref TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            ended_at TEXT,
            cancel_requested_at TEXT,
            notified_at TEXT
        )
        """
    )
    await conn.execute(
        """
        INSERT INTO background_agent_runs (
            task_id, session_id, parent_run_id, status, command,
            created_at, started_at, updated_at
        )
        VALUES ('bg-1', 'sess-1', 'run-1', 'running', 'old', 'now', 'now', 'now')
        """
    )
    await conn.commit()

    s = SessionStore(conn, read_conn)
    await s.init_schema()
    await s.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-2",
        parent_run_id="run-2",
        command="new",
    )
    await s.record_background_agent_finished(
        task_id="bg-1",
        session_id="sess-2",
        status="completed",
        result_text="result",
    )

    assert (await s.list_background_agent_runs("sess-1"))[0]["command"] == "old"
    assert (await s.list_background_agent_runs("sess-2"))[0]["command"] == "new"
    assert await s.get_background_agent_result("sess-2", "bg-1") == "result"

    await read_conn.close()
    await conn.close()


@pytest.mark.asyncio
async def test_marks_running_background_agents_interrupted_on_startup(store: SessionStore):
    await store.record_background_agent_started(
        task_id="bg-1",
        session_id="sess-1",
        parent_run_id="run-1",
        command="research task",
    )

    changed = await store.mark_interrupted_background_agent_runs()
    runs = await store.list_background_agent_runs("sess-1")

    assert changed == 1
    assert runs[0]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_session_events_round_trip_with_sequence(store: SessionStore):
    await store.record_session_event(
        StreamRecord(seq=7, session_id="sess-1", event=ThinkingEvent(status="processing")),
    )

    events = await store.list_session_events("sess-1", after_seq=6)

    assert [record.seq for record in events] == [7]
    assert events[0].session_id == "sess-1"
    assert isinstance(events[0].event, ThinkingEvent)
    assert events[0].event.status == "processing"
    assert await store.get_latest_session_event_seq("sess-1") == 7


@pytest.mark.asyncio
async def test_compaction_boundary_round_trip(store: SessionStore):
    await store.record_chat_compaction(
        compaction_id="compact-1",
        session_id="sess-1",
        boundary_seq=12,
        messages_before=20,
        messages_after=5,
    )

    compactions = await store.list_chat_compactions("sess-1")

    assert len(compactions) == 1
    assert compactions[0]["compaction_id"] == "compact-1"
    assert compactions[0]["boundary_seq"] == 12
    assert compactions[0]["messages_before"] == 20
    assert compactions[0]["messages_after"] == 5


@pytest.mark.asyncio
async def test_save_updates_existing_session(store: SessionStore):
    state = _make_state()
    await store.save_session(state, [{"role": "user", "content": "First"}])
    await store.save_session(
        state,
        [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply"},
        ],
    )

    loaded = await store.load_session("test-session")
    assert len(loaded.messages) == 2


@pytest.mark.asyncio
async def test_list_sessions(store: SessionStore):
    for i in range(3):
        state = _make_state(f"session-{i}", name=f"Chat {i}")
        await store.save_session(state, [{"role": "user", "content": f"msg {i}"}])

    sessions = await store.list_sessions(limit=10)
    assert len(sessions) == 3
    assert all("session_id" in s for s in sessions)


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none(store: SessionStore):
    loaded = await store.load_session("does-not-exist")
    assert loaded is None


@pytest.mark.asyncio
async def test_get_latest_id(store: SessionStore):
    await store.save_session(_make_state("old"), [])
    await store.save_session(_make_state("new"), [])

    latest = await store.get_latest_id()
    assert latest == "new"


@pytest.mark.asyncio
async def test_archive_and_restore(store: SessionStore):
    state = _make_state()
    await store.save_session(state, [{"role": "user", "content": "test"}])

    assert await store.archive_session("test-session")

    # Archived sessions don't appear in active list
    active = await store.list_sessions()
    assert not any(s["session_id"] == "test-session" for s in active)

    # But appear in archived list
    archived = await store.list_archived_sessions()
    assert any(s["session_id"] == "test-session" for s in archived)

    # Restore
    assert await store.restore_session("test-session")
    active = await store.list_sessions()
    assert any(s["session_id"] == "test-session" for s in active)


@pytest.mark.asyncio
async def test_save_stamps_created_at(store: SessionStore):
    state = _make_state()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    await store.save_session(state, messages)

    loaded = await store.load_session("test-session")
    assert loaded is not None
    assert all(m.get("created_at") for m in loaded.messages)


@pytest.mark.asyncio
async def test_update_progress_upserts_for_brand_new_session(store: SessionStore):
    """Regression: a fresh session's first save_progress (called by
    submit_chat_message before the agent starts) used to silently no-op
    because the SQL was UPDATE-only and the row didn't exist yet. The
    user-typed message would then be invisible if the user switched
    sessions and came back before the run's first step finished."""
    state = _make_state("brand-new")
    messages = [
        {"role": "user", "content": "hi", "client_id": "cid-1"},
    ]
    await store.update_progress(state, messages)

    loaded = await store.load_session("brand-new")
    assert loaded is not None
    assert loaded.messages[0]["content"] == "hi"
    assert loaded.messages[0]["client_id"] == "cid-1"


@pytest.mark.asyncio
async def test_update_progress_keeps_metadata_on_existing_session(store: SessionStore):
    """Mid-run checkpoints must not clobber metadata that the final save
    sets (e.g. last_input_tokens used for compaction)."""
    state = _make_state("with-meta")
    await store.save_session(
        state,
        [{"role": "user", "content": "hi"}],
        metadata={"last_input_tokens": 1234},
    )
    await store.update_progress(
        state,
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ],
    )
    loaded = await store.load_session("with-meta")
    assert loaded is not None
    assert loaded.last_input_tokens == 1234
    assert len(loaded.messages) == 2


@pytest.mark.asyncio
async def test_save_preserves_existing_created_at(store: SessionStore):
    state = _make_state()
    fixed = "2024-01-01T00:00:00+00:00"
    messages = [
        {"role": "user", "content": "hello", "created_at": fixed},
        {"role": "assistant", "content": "hi"},
    ]
    await store.save_session(state, messages)
    loaded = await store.load_session("test-session")
    assert loaded is not None
    assert loaded.messages[0]["created_at"] == fixed
    assert loaded.messages[1]["created_at"] != fixed


@pytest.mark.asyncio
async def test_metadata_round_trip(store: SessionStore):
    state = _make_state()
    metadata = {"last_input_tokens": 1234}
    await store.save_session(state, [], metadata=metadata)

    loaded = await store.load_session("test-session")
    assert loaded.last_input_tokens == 1234


@pytest.mark.asyncio
async def test_session_messages_are_stable_across_compaction(store: SessionStore):
    state = _make_state()
    original = [
        {"role": "user", "content": "first", "client_id": "u-1"},
        {"role": "assistant", "content": "reply", "client_id": "a-1"},
        {"role": "user", "content": "second", "client_id": "u-2"},
    ]
    await store.save_session(state, original)

    compacted = [
        {"role": "assistant", "content": "Summary of earlier chat.", "client_id": "summary-1"},
        original[-1],
    ]
    await store.save_session(state, compacted)

    page = await store.list_session_messages("test-session", limit=10)

    assert [row["message"]["content"] for row in page["messages"]] == [
        "first",
        "reply",
        "second",
        "Summary of earlier chat.",
    ]
    assert page["has_more_before"] is False
    assert page["has_more_after"] is False


@pytest.mark.asyncio
async def test_session_message_pagination_before_and_around(store: SessionStore):
    state = _make_state()
    messages = [
        {"role": "user", "content": f"msg {i}", "client_id": f"m-{i}"}
        for i in range(5)
    ]
    await store.save_session(state, messages)

    latest = await store.list_session_messages("test-session", limit=2)
    assert [row["message_id"] for row in latest["messages"]] == ["m-3", "m-4"]
    assert latest["has_more_before"] is True
    assert latest["has_more_after"] is False

    older = await store.list_session_messages("test-session", limit=2, before="m-3")
    assert [row["message_id"] for row in older["messages"]] == ["m-1", "m-2"]
    assert older["has_more_before"] is True
    assert older["has_more_after"] is True

    around = await store.list_session_messages("test-session", limit=3, around="m-2")
    assert [row["message_id"] for row in around["messages"]] == ["m-1", "m-2", "m-3"]
    assert around["has_more_before"] is True
    assert around["has_more_after"] is True


@pytest.mark.asyncio
async def test_delete_session_messages_from_trims_reverted_future(store: SessionStore):
    state = _make_state()
    messages = [
        {"role": "user", "content": f"msg {i}", "client_id": f"m-{i}"}
        for i in range(4)
    ]
    await store.save_session(state, messages)

    assert await store.delete_session_messages_from("test-session", message_id="m-2")

    page = await store.list_session_messages("test-session", limit=10)
    assert [row["message_id"] for row in page["messages"]] == ["m-0", "m-1"]

    episodes = await store.list_session_episodes("test-session")
    assert [episode["message_start_id"] for episode in episodes] == ["m-0", "m-1"]


@pytest.mark.asyncio
async def test_session_episodes_group_durable_transcript_by_user_turn(store: SessionStore):
    state = _make_state()
    messages = [
        {"role": "system", "content": "sys", "client_id": "sys"},
        {"role": "user", "content": "first", "client_id": "u-1", "created_at": "2026-01-01T00:00:00+00:00"},
        {"role": "assistant", "content": "reply", "client_id": "a-1", "created_at": "2026-01-01T00:00:01+00:00"},
        {"role": "tool", "content": "tool", "client_id": "t-1", "created_at": "2026-01-01T00:00:02+00:00"},
        {"role": "user", "content": "second", "client_id": "u-2", "created_at": "2026-01-01T00:00:03+00:00"},
        {"role": "assistant", "content": "reply 2", "client_id": "a-2", "created_at": "2026-01-01T00:00:04+00:00"},
    ]
    await store.save_session(state, messages)

    episodes = await store.list_session_episodes("test-session")

    assert [
        (episode["message_start_id"], episode["message_end_id"])
        for episode in episodes
    ] == [("u-1", "t-1"), ("u-2", "a-2")]
    assert episodes[0]["started_at"] == "2026-01-01T00:00:00+00:00"
    assert episodes[0]["ended_at"] == "2026-01-01T00:00:02+00:00"


@pytest.mark.asyncio
async def test_channel_session_type_and_origin_roundtrip(store: SessionStore):
    """v5: SessionState carries session_type and origin_automation_id."""
    state = SessionState(
        session_id="chan-1",
        started_at=datetime.now(UTC),
        name="offer-42 channel",
        session_type="channel",
        origin_automation_id="watcher-1",
    )
    await store.save_session(state, [{"role": "assistant", "content": "first post"}])

    loaded = await store.load_session("chan-1")
    assert loaded is not None
    assert loaded.state.session_type == "channel"
    assert loaded.state.origin_automation_id == "watcher-1"


@pytest.mark.asyncio
async def test_legacy_chat_session_defaults_when_unset(store: SessionStore):
    """Sessions created without the new fields default to session_type='chat'."""
    state = _make_state()
    await store.save_session(state, [{"role": "user", "content": "hi"}])

    loaded = await store.load_session("test-session")
    assert loaded is not None
    assert loaded.state.session_type == "chat"
    assert loaded.state.origin_automation_id is None


@pytest.mark.asyncio
async def test_session_episodes_survive_compaction_without_handoff_rows(store: SessionStore):
    state = _make_state()
    original = [
        {"role": "user", "content": "first", "client_id": "u-1"},
        {"role": "assistant", "content": "reply", "client_id": "a-1"},
        {"role": "user", "content": "second", "client_id": "u-2"},
        {"role": "assistant", "content": "reply 2", "client_id": "a-2"},
    ]
    await store.save_session(state, original)
    await store.save_session(
        state,
        [
            {"role": "assistant", "content": "[Session State Handoff]\nsummary", "client_id": "handoff"},
            original[-2],
            original[-1],
        ],
    )

    episodes = await store.list_session_episodes("test-session")

    assert [
        (episode["message_start_id"], episode["message_end_id"])
        for episode in episodes
    ] == [("u-1", "a-1"), ("u-2", "a-2")]
