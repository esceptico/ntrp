"""Session store tests — real SQLite, round-trip persistence."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore


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
