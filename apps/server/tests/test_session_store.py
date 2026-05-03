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
async def test_chat_messages_synced(store: SessionStore):
    state = _make_state()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    await store.save_session(state, messages)

    # chat_messages table should have the user and assistant messages
    rows = await store.conn.execute_fetchall(
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY message_index",
        ("test-session",),
    )
    roles = [r["role"] for r in rows]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_metadata_round_trip(store: SessionStore):
    state = _make_state()
    metadata = {"last_input_tokens": 1234}
    await store.save_session(state, [], metadata=metadata)

    loaded = await store.load_session("test-session")
    assert loaded.last_input_tokens == 1234
