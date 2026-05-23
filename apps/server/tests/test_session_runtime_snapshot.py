from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore
from ntrp.core.model_context_budget import HISTORY_TOOL_RESULT_PREVIEW_CHARS
from ntrp.events.sse import ThinkingEvent
from ntrp.server.bus import BusRegistry
from ntrp.server.routers.session import get_session_history, list_sessions
from ntrp.server.state import RunRegistry, RunStatus
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
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-runtime", limit=100, around_seq=None
    )

    assert result["active_run_id"] == "run-1"
    assert result["runtime"]["checkpoint_seq"] == 12
    assert result["runtime"]["active_run"]["status"] == "running"
    assert result["runtime"]["pending_approvals"][0]["tool_id"] == "tool-1"
    assert result["runtime"]["queued_messages"][0]["client_id"] == "queued-1"


@pytest.mark.asyncio
async def test_history_runtime_snapshot_reports_live_backgrounded_run(session_service: SessionService):
    state = _state("sess-live-backgrounded")
    await session_service.save(state, [{"role": "user", "content": "hi", "client_id": "msg-1"}])
    registry = RunRegistry()
    run = registry.create_run("sess-live-backgrounded")
    run.status = RunStatus.RUNNING
    run.backgrounded = True

    runtime = SimpleNamespace(run_registry=registry, executor=None)
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-live-backgrounded", limit=100, around_seq=None
    )

    assert result["runtime"]["active_run"]["run_id"] == run.run_id
    assert result["runtime"]["active_run"]["status"] == "backgrounded"


@pytest.mark.asyncio
async def test_history_runtime_snapshot_hides_stale_queue_rows(session_service: SessionService):
    state = _state("sess-stale-queue")
    await session_service.save(state, [{"role": "user", "content": "hi", "client_id": "msg-1"}])
    await session_service.store.record_chat_run_started("run-old", "sess-stale-queue")
    await session_service.store.record_chat_queued_message(
        client_id="queued-old",
        session_id="sess-stale-queue",
        run_id="run-old",
        message={"role": "user", "content": "old queued", "client_id": "queued-old"},
        enqueued_seq=5,
    )
    await session_service.store.record_chat_run_status("run-old", "interrupted", last_seq=6)

    await session_service.store.record_chat_run_started("run-new", "sess-stale-queue")
    await session_service.store.record_chat_run_status("run-new", "running", last_seq=7)
    await session_service.store.record_chat_queued_message(
        client_id="queued-new",
        session_id="sess-stale-queue",
        run_id="run-new",
        message={"role": "user", "content": "new queued", "client_id": "queued-new"},
        enqueued_seq=8,
    )

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-stale-queue", limit=100, around_seq=None
    )

    assert result["runtime"]["active_run"]["run_id"] == "run-new"
    assert [message["client_id"] for message in result["runtime"]["queued_messages"]] == ["queued-new"]


@pytest.mark.asyncio
async def test_history_runtime_snapshot_omits_retryable_queue_after_terminal_run(session_service: SessionService):
    state = _state("sess-terminal-queue")
    await session_service.save(state, [{"role": "user", "content": "hi", "client_id": "msg-1"}])
    await session_service.store.record_chat_run_started("run-1", "sess-terminal-queue")
    await session_service.store.record_chat_queued_message(
        client_id="queued-1",
        session_id="sess-terminal-queue",
        run_id="run-1",
        message={"role": "user", "content": "retryable", "client_id": "queued-1"},
        enqueued_seq=9,
    )
    await session_service.store.record_chat_run_status("run-1", "interrupted", last_seq=10)
    await session_service.store.mark_interrupted_chat_queued_messages_retryable()

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-terminal-queue", limit=100, around_seq=None
    )

    assert result["runtime"]["active_run"]["status"] == "interrupted"
    assert result["runtime"]["queued_messages"] == []


@pytest.mark.asyncio
async def test_history_clamps_huge_persisted_tool_content(session_service: SessionService):
    state = _state("sess-huge-tool")
    huge_result = "x" * (HISTORY_TOOL_RESULT_PREVIEW_CHARS + 10_000)
    await session_service.save(
        state,
        [
            {"role": "user", "content": "search"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_text", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": huge_result},
        ],
    )

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-huge-tool", limit=100, around_seq=None
    )

    tool_message = result["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-1"
    assert len(tool_message["content"]) < len(huge_result)
    assert "Tool result compacted for history display" in tool_message["content"]
    assert huge_result not in tool_message["content"]


@pytest.mark.asyncio
async def test_history_ignores_legacy_null_tool_calls(session_service: SessionService):
    state = _state("sess-null-tool-calls")
    await session_service.save(
        state,
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello", "tool_calls": None},
        ],
    )

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-null-tool-calls", limit=100, around_seq=None
    )

    assistant = result["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "hello"
    assert "tool_calls" not in assistant


@pytest.mark.asyncio
async def test_history_skips_malformed_tool_calls_but_keeps_valid_calls(session_service: SessionService):
    state = _state("sess-malformed-tool-calls")
    await session_service.save(
        state,
        [
            {"role": "user", "content": "run tools"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    None,
                    {"id": "missing-function"},
                    {"id": 123, "function": {"name": "bash", "arguments": "{}"}},
                    {"id": "missing-name", "function": {"arguments": "{}"}},
                    {"id": "call-1", "function": {"name": "bash", "arguments": {"cmd": "date"}}},
                    {"id": "call-2", "function": {"name": "read_file", "arguments": '{"path":"a"}'}},
                ],
            },
        ],
    )

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(
        session_service, runtime, BusRegistry(), "sess-malformed-tool-calls", limit=100, around_seq=None
    )

    assistant = result["messages"][-1]
    assert assistant["tool_calls"] == [
        {"id": "call-1", "name": "bash", "arguments": "{}", "kind": "tool"},
        {"id": "call-2", "name": "read_file", "arguments": '{"path":"a"}', "kind": "tool"},
    ]


@pytest.mark.asyncio
async def test_history_runtime_snapshot_keeps_live_tail_after_checkpoint(session_service: SessionService):
    state = _state("sess-live-tail")
    await session_service.save(state, [{"role": "user", "content": "hi", "client_id": "msg-1"}])
    await session_service.store.record_chat_run_started("run-1", "sess-live-tail")
    await session_service.store.record_chat_run_status("run-1", "running", last_seq=1)

    buses = BusRegistry()
    bus = buses.get_or_create("sess-live-tail")
    await bus.emit(ThinkingEvent(status="checkpointed"))
    bus.mark_checkpoint()
    await bus.emit(ThinkingEvent(status="live-tail"))

    runtime = SimpleNamespace(run_registry=RunRegistry(), executor=None)
    result = await get_session_history(session_service, runtime, buses, "sess-live-tail", limit=100, around_seq=None)

    assert result["runtime"]["checkpoint_seq"] == 1
    assert result["runtime"]["latest_event_seq"] == 2
    assert result["runtime"]["active_run"]["checkpoint_seq"] == 1
    assert result["runtime"]["active_run"]["latest_event_seq"] == 2


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
