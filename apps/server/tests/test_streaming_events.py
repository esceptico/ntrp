import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ntrp.agent import ReasoningContentDelta, ReasoningDelta, TextDelta, TextEnded, TextStarted
from ntrp.context.models import SessionState
from ntrp.core import spawner as spawner_module
from ntrp.core.spawner import create_spawn_fn
from ntrp.events.sse import (
    ReasoningMessageContentEvent,
    TextDeltaEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    agent_events_to_sse,
)
from ntrp.server.bus import BusRegistry, SessionBus
from ntrp.server.routers.chat import _event_stream
from ntrp.server.state import RunRegistry, RunState
from ntrp.server.stream import run_agent_loop
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
    assert emitted == []
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

    assert [event.type.value for event in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]


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
    assert [event.type.value for event in bus._recent] == [
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
            yield TextStarted(message_id="text-1")
            yield TextDelta(message_id="text-1", content="hello")
            yield TextEnded(message_id="text-1", content="hello")

    bus = CancellingContentFlushBus(session_id="sess-1")
    task = asyncio.create_task(run_agent_loop(SimpleNamespace(run=run), AgentWithOpenText(), bus))
    run.task = task

    await task

    assert [event.type.value for event in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]


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
            yield TextStarted(message_id="text-1")
            yield TextDelta(message_id="text-1", content="hello")
            yield TextEnded(message_id="text-1", content="hello")

    bus = CancellingFirstEndBus()

    await run_agent_loop(SimpleNamespace(run=run), AgentWithTextEnd(), bus)

    assert [event.type.value for event in bus._recent] == [
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "run_cancelled",
    ]
    assert bus.cancelled_end_once is True
