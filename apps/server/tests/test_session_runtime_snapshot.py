from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.server.bus import BusRegistry
from ntrp.server.routers.session import get_session_history, list_sessions
from ntrp.server.state import RunRegistry
from ntrp.services.session import SessionService


@pytest_asyncio.fixture
async def session_service(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    read_conn = await database.connect(tmp_path / "sessions.db", readonly=True)
    store = SessionStore(conn, read_conn)
    await store.init_schema()
    yield SessionService(store)
    await read_conn.close()
    await conn.close()


def _state(session_id: str) -> SessionState:
    return SessionState(session_id=session_id, started_at=datetime.now(UTC), name="runtime test")


@pytest.mark.asyncio
async def test_history_includes_runtime_snapshot_for_active_session(session_service: SessionService):
    state = _state("sess-runtime")
    await session_service.save(state, [{"role": "user", "content": "hi", "client_id": "msg-1"}])
    await session_service.store.record_chat_run_started("run-1", "sess-runtime")
    await session_service.store.record_chat_run_status("run-1", "running", last_seq=12)
    await session_service.store.record_tool_approval_requested(
        run_id="run-1",
        session_id="sess-runtime",
        tool_call_id="tool-1",
        tool_name="write_file",
        action="write",
        scope="internal",
        diff="diff",
    )
    await session_service.store.record_chat_queued_message(
        client_id="queued-1",
        session_id="sess-runtime",
        run_id="run-1",
        message={"role": "user", "content": "follow up", "client_id": "queued-1"},
        enqueued_seq=13,
    )

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(session_service, runtime, BusRegistry(), "sess-runtime", limit=100, around_seq=None)

    assert result["active_run_id"] == "run-1"
    assert result["runtime"]["checkpoint_seq"] == 12
    assert result["runtime"]["active_run"]["status"] == "running"
    assert result["runtime"]["pending_approvals"][0]["tool_id"] == "tool-1"
    assert result["runtime"]["queued_messages"][0]["client_id"] == "queued-1"


@pytest.mark.asyncio
async def test_sessions_list_surfaces_interrupted_runtime_state(session_service: SessionService):
    state = _state("sess-interrupted")
    await session_service.save(state, [])
    await session_service.store.record_chat_run_started("run-interrupted", "sess-interrupted")
    await session_service.store.record_chat_run_status(
        "run-interrupted",
        "interrupted",
        stop_reason="server_restart",
        last_seq=22,
        error_code="run_interrupted",
    )

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await list_sessions(session_service, runtime, BusRegistry())

    session = result["sessions"][0]
    assert session["session_id"] == "sess-interrupted"
    assert session["active_run_id"] == "run-interrupted"
    assert session["run_status"] == "interrupted"
    assert session["checkpoint_seq"] == 22
    assert session["is_active"] is False
    assert session["run_error_code"] == "run_interrupted"
