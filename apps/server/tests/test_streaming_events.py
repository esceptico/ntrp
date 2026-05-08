import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntrp.agent import ReasoningContentDelta, ReasoningDelta, TextDelta, TextEnded, TextStarted
from ntrp.context.models import SessionData, SessionState
from ntrp.core import spawner as spawner_module
from ntrp.core.spawner import create_spawn_fn
from ntrp.core.usage_tracker import UsageTracker
from ntrp.events.sse import (
    ReasoningMessageContentEvent,
    TaskFinishedEvent,
    TaskStartedEvent,
    TextDeltaEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ThinkingEvent,
    agent_events_to_sse,
)
from ntrp.server.bus import BusRegistry, SessionBus
from ntrp.server.routers.chat import _event_stream
from ntrp.server.state import RunRegistry, RunState, RunStatus
from ntrp.server.stream import run_agent_loop
from ntrp.services.chat import ChatContext, _drain_backgrounded, run_chat
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext
from tests.helpers import make_executor, make_text_response


def test_text_boundary_events_convert_to_sse():
    (start,) = agent_events_to_sse(TextStarted(message_id="text-1"))
    (content,) = agent_events_to_sse(TextDelta(message_id="text-1", content="hello"))
    (end,) = agent_events_to_sse(TextEnded(message_id="text-1", content="hello"))

    assert isinstance(start, TextMessageStartEvent)
    assert start.message_id == "text-1"
    assert content.message_id == "text-1"
    assert isinstance(end, TextMessageEndEvent)
    assert end.message_id == "text-1"
    assert end.content == "hello"


def test_reasoning_sse_preserves_nested_scope():
    (event,) = agent_events_to_sse(
        ReasoningDelta(depth=1, parent_id="call-research", message_id="reasoning-1", content="internal thought")
    )

    assert isinstance(event, ReasoningMessageContentEvent)
    assert event.depth == 1
    assert event.parent_id == "call-research"

    data = json.loads(event.to_sse()["data"])
    assert data["depth"] == 1
    assert data["parent_id"] == "call-research"


def test_text_boundary_sse_preserves_nested_scope():
    (start,) = agent_events_to_sse(TextStarted(depth=1, parent_id="call-research", message_id="text-1"))
    (content,) = agent_events_to_sse(
        TextDelta(depth=1, parent_id="call-research", message_id="text-1", content="hello")
    )
    (end,) = agent_events_to_sse(TextEnded(depth=1, parent_id="call-research", message_id="text-1", content="hello"))

    for event in (start, content, end):
        data = json.loads(event.to_sse()["data"])
        assert data["depth"] == 1
        assert data["parent_id"] == "call-research"


def test_task_lifecycle_events_include_parent_tool_call():
    start = TaskStartedEvent(
        run_id="run-1",
        task_id="call-research",
        parent_tool_call_id="call-research",
        name="Research",
        summary="look up event systems",
        depth=1,
    )
    done = TaskFinishedEvent(
        run_id="run-1",
        task_id="call-research",
        parent_tool_call_id="call-research",
        status="completed",
        summary="done",
        depth=1,
    )

    start_payload = json.loads(start.to_sse()["data"])
    done_payload = json.loads(done.to_sse()["data"])

    assert start_payload["type"] == "task_started"
    assert start_payload["task_id"] == "call-research"
    assert start_payload["parent_tool_call_id"] == "call-research"
    assert done_payload["type"] == "task_finished"
    assert done_payload["status"] == "completed"


@pytest.mark.asyncio
async def test_research_child_reasoning_is_not_emitted_to_parent(monkeypatch):
    prompt_cache_keys = []

    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            prompt_cache_keys.append(prompt_cache_key)
            yield ReasoningContentDelta("internal research thought")
            yield make_text_response("child answer", model=model)

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    emitted = []

    async def emit(event):
        emitted.append(event)

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(emit=emit),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    spawn = create_spawn_fn(executor=executor, model="test-model", max_depth=3, current_depth=0)
    result = await spawn(
        ctx,
        "research task",
        system_prompt="research system",
        tools=[],
        parent_id="call-research",
        timeout=1,
    )

    assert result == "child answer"
    assert [event.type.value for event in emitted] == ["task_started", "task_finished"]
    assert len(prompt_cache_keys) == 1
    assert prompt_cache_keys[0].startswith("test::")


@pytest.mark.asyncio
async def test_event_stream_does_not_synthesize_text_boundaries():
    buses = BusRegistry()
    bus = buses.get_or_create("sess-1")
    await bus.emit(TextMessageStartEvent(message_id="text-1"))
    await bus.emit(TextDeltaEvent(message_id="text-1", delta="hello"))
    await bus.emit(TextMessageEndEvent(message_id="text-1", content="hello"))

    stream = _event_stream("sess-1", buses, RunRegistry(), stream=True)
    try:
        chunks = [await anext(stream), await anext(stream), await anext(stream)]
    finally:
        await stream.aclose()

    payloads = [json.loads(chunk.split("data: ", 1)[1].strip()) for chunk in chunks]
    assert [payload["type"] for payload in payloads] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
    ]
    assert [payload["message_id"] for payload in payloads] == ["text-1", "text-1", "text-1"]


@pytest.mark.asyncio
async def test_event_stream_filters_snapshot_text_deltas_when_stream_false():
    buses = BusRegistry()
    bus = buses.get_or_create("sess-1")
    await bus.emit(TextMessageStartEvent(message_id="text-1"))
    await bus.emit(TextDeltaEvent(message_id="text-1", delta="hello"))
    await bus.emit(TextMessageEndEvent(message_id="text-1", content="hello"))

    stream = _event_stream("sess-1", buses, RunRegistry(), stream=False)
    try:
        chunks = [await anext(stream), await anext(stream)]
    finally:
        await stream.aclose()

    payloads = [json.loads(chunk.split("data: ", 1)[1].strip()) for chunk in chunks]
    assert [payload["type"] for payload in payloads] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_END",
    ]
    assert all(payload["type"] != "TEXT_MESSAGE_CONTENT" for payload in payloads)


@pytest.mark.asyncio
async def test_event_stream_emits_stream_reset_on_replay_gap():
    buses = BusRegistry()
    bus = buses.get_or_create("sess-1")
    await bus.emit(ThinkingEvent(status="saved-a"))
    await bus.emit(ThinkingEvent(status="saved-b"))
    bus.clear_buffer()
    await bus.emit(ThinkingEvent(status="live-tail"))

    stream = _event_stream("sess-1", buses, RunRegistry(), stream=True, after_seq=1)
    try:
        reset_chunk = await anext(stream)
        replay_chunk = await anext(stream)
    finally:
        await stream.aclose()

    reset_payload = json.loads(reset_chunk.split("data: ", 1)[1].strip())
    replay_payload = json.loads(replay_chunk.split("data: ", 1)[1].strip())

    assert "event: stream_reset" in reset_chunk
    assert reset_payload["type"] == "stream_reset"
    assert reset_payload["reason"] == "replay_gap"
    assert reset_payload["session_id"] == "sess-1"
    assert reset_payload["seq"] == 2
    assert replay_payload["type"] == "thinking"
    assert replay_payload["status"] == "live-tail"
    assert replay_payload["seq"] == 3


@pytest.mark.asyncio
async def test_run_agent_loop_emits_text_end_before_run_cancelled():
    run = RunState(run_id="run-1", session_id="sess-1")
    bus = SessionBus(session_id="sess-1")

    class CancellingAgent:
        async def stream(self, messages):
            yield TextStarted(message_id="text-1")
            yield TextDelta(message_id="text-1", content="hello")
            run.cancelled = True
            yield TextEnded(message_id="text-1", content="hello")

    await run_agent_loop(SimpleNamespace(run=run), CancellingAgent(), bus)

    assert [record.event.type.value for record in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]


@pytest.mark.asyncio
async def test_run_agent_loop_closes_open_text_on_cooperative_cancel():
    run = RunState(run_id="run-1", session_id="sess-1")

    class CancelAfterSecondContentBus(SessionBus):
        def __init__(self):
            super().__init__(session_id="sess-1")
            self.content_count = 0

        async def emit(self, event):
            await super().emit(event)
            if isinstance(event, TextMessageContentEvent):
                self.content_count += 1
                if self.content_count == 2:
                    run.cancelled = True

    class CooperativeCancellingAgent:
        async def stream(self, messages):
            yield TextStarted(depth=1, parent_id="call-research", message_id="text-1")
            yield TextDelta(depth=1, parent_id="call-research", message_id="text-1", content="hello")
            yield TextDelta(depth=1, parent_id="call-research", message_id="text-1", content=" world")
            yield TextDelta(depth=1, parent_id="call-research", message_id="text-1", content=" dropped")

    bus = CancelAfterSecondContentBus()

    await run_agent_loop(SimpleNamespace(run=run), CooperativeCancellingAgent(), bus)

    assert [record.event.type.value for record in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]
    end = bus._recent[3].event
    assert isinstance(end, TextMessageEndEvent)
    assert end.message_id == "text-1"
    assert end.content == "hello world"
    assert end.depth == 1
    assert end.parent_id == "call-research"


@pytest.mark.asyncio
async def test_run_agent_loop_closes_text_before_backgrounding():
    run = RunState(run_id="run-1", session_id="sess-1")
    bus = SessionBus(session_id="sess-1")

    class BackgroundingAgent:
        async def stream(self, messages):
            yield TextStarted(message_id="text-1")
            yield TextDelta(message_id="text-1", content="hello")
            run.backgrounded = True
            yield TextEnded(message_id="text-1", content="hello")

    result, bg_gen = await run_agent_loop(SimpleNamespace(run=run), BackgroundingAgent(), bus)

    assert result is None
    assert bg_gen is not None
    assert [record.event.type.value for record in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
    ]


@pytest.mark.asyncio
async def test_run_agent_loop_closes_text_when_task_cancelled_during_content_flush():
    run_registry = RunRegistry()
    run = run_registry.create_run("sess-1")

    class CancellingContentFlushBus(SessionBus):
        async def emit(self, event):
            await super().emit(event)
            if isinstance(event, TextMessageContentEvent):
                run_registry.cancel_run(run.run_id)
                await asyncio.sleep(0)

    class AgentWithOpenText:
        async def stream(self, messages):
            yield TextStarted(depth=1, parent_id="call-research", message_id="text-1")
            yield TextDelta(depth=1, parent_id="call-research", message_id="text-1", content="hello")
            yield TextEnded(depth=1, parent_id="call-research", message_id="text-1", content="hello")

    bus = CancellingContentFlushBus(session_id="sess-1")
    task = asyncio.create_task(run_agent_loop(SimpleNamespace(run=run), AgentWithOpenText(), bus))
    run.task = task

    await task

    assert [record.event.type.value for record in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]
    end = bus._recent[2].event
    assert isinstance(end, TextMessageEndEvent)
    assert end.message_id == "text-1"
    assert end.content == "hello"
    assert end.depth == 1
    assert end.parent_id == "call-research"


@pytest.mark.asyncio
async def test_run_agent_loop_hard_task_cancel_emits_terminal_cancelled():
    run = RunState(run_id="run-1", session_id="sess-1")
    bus = SessionBus(session_id="sess-1")
    released = asyncio.Event()

    class AgentWithBlockingStream:
        async def stream(self, messages):
            yield TextStarted(depth=1, parent_id="call-research", message_id="text-1")
            yield TextDelta(depth=1, parent_id="call-research", message_id="text-1", content="partial")
            await released.wait()

    task = asyncio.create_task(run_agent_loop(SimpleNamespace(run=run), AgentWithBlockingStream(), bus))

    async def wait_for_streamed_content():
        while len(bus._recent) < 2:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_streamed_content(), timeout=1)

    task.cancel()
    await task

    event_types = [record.event.type.value for record in bus._recent]
    assert event_types == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]
    assert event_types.count("run_cancelled") == 1
    end = bus._recent[2].event
    assert isinstance(end, TextMessageEndEvent)
    assert end.message_id == "text-1"
    assert end.content == "partial"
    assert end.depth == 1
    assert end.parent_id == "call-research"
    assert run.cancelled is True


@pytest.mark.asyncio
async def test_run_chat_emits_cancelled_when_task_cancelled_before_agent_loop():
    registry = RunRegistry()
    run = registry.create_run("sess-1")
    session_state = SessionState(session_id="sess-1", started_at=datetime.now(UTC))

    class NoopSessionService:
        async def save(self, session_state, messages, metadata=None):
            return None

    class CancellingInitialEmitBus(SessionBus):
        async def emit(self, event):
            await super().emit(event)
            if event.type.value == "RUN_STARTED":
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
                await asyncio.sleep(0)

    bus = CancellingInitialEmitBus(session_id="sess-1")
    queue = bus.subscribe()
    ctx = ChatContext(
        run=run,
        session_state=session_state,
        is_init=False,
        executor=SimpleNamespace(),
        tools=[],
        config=SimpleNamespace(),
        available_integrations=[],
        integration_errors={},
        session_service=NoopSessionService(),
        run_registry=registry,
    )

    await run_chat(ctx, bus)

    events = []
    while not queue.empty():
        record = queue.get_nowait()
        assert record is not None
        events.append(record.event.type.value)

    assert events.count("run_cancelled") == 1
    assert events == ["RUN_STARTED", "run_cancelled"]
    assert run.cancelled is True
    assert run.cancel_terminal_emitted is True
    assert run.status == RunStatus.CANCELLED
    assert registry.get_active_run("sess-1") is None


@pytest.mark.asyncio
async def test_cancelled_run_finally_drops_pending_without_persisting():
    registry = RunRegistry()
    run = registry.create_run("sess-1")
    run.messages = [{"role": "user", "content": "old request"}]
    run.queue_injection({"role": "user", "content": "dead follow-up", "client_id": "cid-dead"})
    session_state = SessionState(session_id="sess-1", started_at=datetime.now(UTC))

    class RecordingSessionService:
        def __init__(self):
            self.saved: list[list[dict]] = []

        async def save(self, session_state, messages, metadata=None):
            self.saved.append(list(messages))

    class CancellingInitialEmitBus(SessionBus):
        async def emit(self, event):
            await super().emit(event)
            if event.type.value == "RUN_STARTED":
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
                await asyncio.sleep(0)

    session_service = RecordingSessionService()
    bus = CancellingInitialEmitBus(session_id="sess-1")
    ctx = ChatContext(
        run=run,
        session_state=session_state,
        is_init=False,
        executor=SimpleNamespace(),
        tools=[],
        config=SimpleNamespace(),
        available_integrations=[],
        integration_errors={},
        session_service=session_service,
        run_registry=registry,
    )

    await run_chat(ctx, bus)

    assert session_service.saved == []
    assert run.pending_injection_count == 0
    assert run.messages == [{"role": "user", "content": "old request"}]


@pytest.mark.asyncio
async def test_cancelled_run_finally_does_not_clear_newer_replay_events():
    registry = RunRegistry()
    run = registry.create_run("sess-1")
    session_state = SessionState(session_id="sess-1", started_at=datetime.now(UTC))

    class NoopSessionService:
        async def save(self, session_state, messages, metadata=None):
            return None

    class CancellingInitialEmitBus(SessionBus):
        async def emit(self, event):
            await super().emit(event)
            if event.type.value == "RUN_STARTED":
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
                await asyncio.sleep(0)

    bus = CancellingInitialEmitBus(session_id="sess-1")
    await bus.emit(ThinkingEvent(status="newer run replay"))
    ctx = ChatContext(
        run=run,
        session_state=session_state,
        is_init=False,
        executor=SimpleNamespace(),
        tools=[],
        config=SimpleNamespace(),
        available_integrations=[],
        integration_errors={},
        session_service=NoopSessionService(),
        run_registry=registry,
    )

    await run_chat(ctx, bus)

    assert [record.event.type.value for record in bus._recent] == [
        "thinking",
        "RUN_STARTED",
        "run_cancelled",
    ]


@pytest.mark.asyncio
async def test_background_result_after_cancel_is_ignored_for_cancelled_run(monkeypatch):
    from ntrp.services import chat as chat_service

    registry = RunRegistry()
    run = registry.create_run("sess-1")
    session_state = SessionState(session_id="sess-1", started_at=datetime.now(UTC))
    stream_started = asyncio.Event()
    release = asyncio.Event()

    class NoopSessionService:
        async def save(self, session_state, messages, metadata=None):
            return None

    class FakeAgent:
        def __init__(self):
            self.hooks = SimpleNamespace(on_response=None, on_step_finish=None, get_pending_messages=None)
            self.tools = []

        async def stream(self, messages):
            stream_started.set()
            await release.wait()
            if False:
                yield None

    monkeypatch.setattr(chat_service, "create_agent", lambda **_kwargs: FakeAgent())
    ctx = ChatContext(
        run=run,
        session_state=session_state,
        is_init=False,
        executor=SimpleNamespace(),
        tools=[],
        config=SimpleNamespace(),
        available_integrations=[],
        integration_errors={},
        session_service=NoopSessionService(),
        run_registry=registry,
    )

    task = asyncio.create_task(run_chat(ctx, SessionBus(session_id="sess-1")))
    await asyncio.wait_for(stream_started.wait(), timeout=1)
    run.cancelled = True

    await registry.get_background_registry("sess-1").inject([{"role": "user", "content": "late background"}])

    assert run.pending_injection_count == 0
    task.cancel()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_backgrounded_drain_cancel_does_not_save_merged_output():
    run = RunState(run_id="run-1", session_id="sess-1", backgrounded=True)
    session_state = SessionState(session_id="sess-1", started_at=datetime.now(UTC))
    started = asyncio.Event()
    release = asyncio.Event()

    class RecordingSessionService:
        def __init__(self):
            self.saved: list[list[dict]] = []

        async def load(self, session_id=None):
            return SessionData(state=session_state, messages=[{"role": "user", "content": "newer"}])

        async def save(self, session_state, messages, metadata=None):
            self.saved.append(list(messages))

    async def gen():
        started.set()
        await release.wait()
        if False:
            yield None

    ctx = ChatContext(
        run=run,
        session_state=session_state,
        is_init=False,
        executor=SimpleNamespace(registry=SimpleNamespace(get=lambda _name: None)),
        tools=[],
        config=SimpleNamespace(),
        available_integrations=[],
        integration_errors={},
        session_service=RecordingSessionService(),
        run_registry=RunRegistry(),
    )
    task = asyncio.create_task(
        _drain_backgrounded(
            gen(),
            SimpleNamespace(tools=[]),
            ctx,
            BackgroundTaskRegistry(session_id="sess-1"),
            UsageTracker(),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    task.cancel()
    await asyncio.wait_for(task, timeout=1)

    assert ctx.session_service.saved == []


@pytest.mark.asyncio
async def test_run_agent_loop_retries_text_end_when_emit_is_cancelled():
    run = RunState(run_id="run-1", session_id="sess-1")

    class CancellingFirstEndBus(SessionBus):
        def __init__(self):
            super().__init__(session_id="sess-1")
            self.cancelled_end_once = False

        async def emit(self, event):
            if isinstance(event, TextMessageEndEvent) and not self.cancelled_end_once:
                self.cancelled_end_once = True
                run.cancelled = True
                raise asyncio.CancelledError
            await super().emit(event)

    class AgentWithTextEnd:
        async def stream(self, messages):
            yield TextStarted(depth=1, parent_id="call-research", message_id="text-1")
            yield TextDelta(depth=1, parent_id="call-research", message_id="text-1", content="partial")
            yield TextEnded(depth=2, parent_id="call-final", message_id="text-final", content="explicit final")

    bus = CancellingFirstEndBus()

    await run_agent_loop(SimpleNamespace(run=run), AgentWithTextEnd(), bus)

    assert [record.event.type.value for record in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]
    end = bus._recent[2].event
    assert isinstance(end, TextMessageEndEvent)
    assert end.message_id == "text-final"
    assert end.content == "explicit final"
    assert end.depth == 2
    assert end.parent_id == "call-final"
    assert bus.cancelled_end_once is True
