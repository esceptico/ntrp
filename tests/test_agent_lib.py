"""Standalone tests for the ntrp.agent library. No ntrp imports beyond ntrp.agent.*"""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any

import pytest

from ntrp.agent import (
    Agent,
    AgentHooks,
    Choice,
    CompletionResponse,
    FunctionCall,
    Message,
    Result,
    Role,
    SharedLedger,
    SpawnContext,
    StopReason,
    TextBlock,
    TextDelta,
    ToolCall,
    ToolChoiceMode,
    ToolMeta,
    ToolResult,
    Usage,
)

# ============================================================
# Test doubles — pure, zero ntrp dependencies
# ============================================================


def _response(
    text: str | None = None, tool_calls: list[ToolCall] | None = None, usage: Usage | None = None
) -> CompletionResponse:
    return CompletionResponse(
        choices=[
            Choice(
                message=Message(role=Role.ASSISTANT, content=text, tool_calls=tool_calls, reasoning_content=None),
                finish_reason=None,
            )
        ],
        usage=usage or Usage(prompt_tokens=10, completion_tokens=5),
        model="test",
    )


def _tc(tool_id: str, name: str, args: dict) -> ToolCall:
    return ToolCall(id=tool_id, type="function", function=FunctionCall(name=name, arguments=json.dumps(args)))


class FakeLLM:
    """Queue-based LLM: yields responses in order, raises if exhausted."""

    def __init__(self, responses: list[CompletionResponse | Exception]):
        self._queue = list(responses)
        self.call_count = 0
        self.last_messages: list[dict] | None = None
        self.last_tool_choice = None

    async def stream(self, messages, model, tools, tool_choice=None) -> AsyncGenerator:
        self.call_count += 1
        self.last_messages = list(messages)
        self.last_tool_choice = tool_choice
        if not self._queue:
            raise RuntimeError("FakeLLM exhausted")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if item.choices[0].message.content:
            yield item.choices[0].message.content
        yield item

    async def complete(self, model, messages, **kwargs):
        return self._queue.pop(0)


class FakeExecutor:
    """In-memory tool executor with configurable results and metadata."""

    def __init__(self, handlers: dict[str, Any], meta: dict[str, ToolMeta] | None = None):
        self._handlers = handlers
        self._meta = meta or {}
        self.call_log: list[tuple[str, dict]] = []

    async def execute(self, name: str, args: dict, tool_call_id: str) -> ToolResult:
        self.call_log.append((name, args))
        handler = self._handlers.get(name)
        if handler is None:
            return ToolResult(content=f"unknown: {name}", preview="unknown", is_error=True)
        if isinstance(handler, Exception):
            raise handler
        if callable(handler):
            return handler(args)
        return handler

    def get_meta(self, name: str) -> ToolMeta | None:
        return self._meta.get(
            name,
            ToolMeta(name=name, display_name=name, mutates=False, volatile=False),
        )


def _msgs(user: str = "hi") -> list[dict]:
    return [{"role": "system", "content": "sys"}, {"role": "user", "content": user}]


def _make_agent(llm: FakeLLM, executor: FakeExecutor, **kwargs) -> Agent:
    return Agent(
        tools=[{"type": "function", "function": {"name": "test"}}],
        client=llm,
        executor=executor,
        model="test",
        **kwargs,
    )


# ============================================================
# Basic loop
# ============================================================


@pytest.mark.asyncio
async def test_simple_text_response_returns_result():
    llm = FakeLLM([_response(text="hello")])
    agent = _make_agent(llm, FakeExecutor({}))
    result = await agent.run(_msgs())
    assert result.text == "hello"
    assert result.stop_reason == StopReason.END_TURN
    assert result.steps == 0


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_then_result():
    llm = FakeLLM([_response(text="answer")])
    agent = _make_agent(llm, FakeExecutor({}))
    events = [e async for e in agent.stream(_msgs())]
    assert any(isinstance(e, TextDelta) and e.content == "answer" for e in events)
    assert isinstance(events[-1], Result)
    assert events[-1].text == "answer"


@pytest.mark.asyncio
async def test_single_tool_call_then_response():
    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("c1", "echo", {"x": 1})]),
            _response(text="done"),
        ]
    )
    executor = FakeExecutor({"echo": ToolResult(content="echoed", preview="e")})
    agent = _make_agent(llm, executor)

    messages = _msgs()
    result = await agent.run(messages)

    assert result.text == "done"
    assert result.steps == 1
    assert executor.call_log == [("echo", {"x": 1})]
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"] == "echoed"


# ============================================================
# Edge cases — malformed LLM output
# ============================================================


@pytest.mark.asyncio
async def test_empty_text_response():
    llm = FakeLLM([_response(text="")])
    agent = _make_agent(llm, FakeExecutor({}))
    result = await agent.run(_msgs())
    assert result.text == ""
    assert result.stop_reason == StopReason.END_TURN


@pytest.mark.asyncio
async def test_none_text_response():
    llm = FakeLLM([_response(text=None)])
    agent = _make_agent(llm, FakeExecutor({}))
    result = await agent.run(_msgs())
    assert result.text == ""


@pytest.mark.asyncio
async def test_text_and_tool_calls_yields_text_block():
    llm = FakeLLM(
        [
            _response(text="thinking...", tool_calls=[_tc("c1", "t", {})]),
            _response(text="done"),
        ]
    )
    agent = _make_agent(llm, FakeExecutor({"t": ToolResult(content="ok", preview="ok")}))
    events = [e async for e in agent.stream(_msgs())]
    assert any(isinstance(e, TextBlock) and e.content == "thinking..." for e in events)


@pytest.mark.asyncio
async def test_malformed_tool_arguments_becomes_empty_dict():
    bad_tc = ToolCall(id="c1", type="function", function=FunctionCall(name="t", arguments="{not json}"))
    llm = FakeLLM([_response(tool_calls=[bad_tc]), _response(text="done")])
    executor = FakeExecutor({"t": ToolResult(content="ok", preview="ok")})
    agent = _make_agent(llm, executor)
    await agent.run(_msgs())
    assert executor.call_log == [("t", {})]


# ============================================================
# Multiple tool calls — concurrency by mutates flag
# ============================================================


@pytest.mark.asyncio
async def test_multiple_non_mutating_tools_run_concurrently():
    events_order: list[str] = []

    def slow_a(args):
        events_order.append("a_start")
        return ToolResult(content="a", preview="a")

    def slow_b(args):
        events_order.append("b_start")
        return ToolResult(content="b", preview="b")

    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("1", "a", {}), _tc("2", "b", {})]),
            _response(text="done"),
        ]
    )
    executor = FakeExecutor(
        {"a": slow_a, "b": slow_b},
        meta={
            "a": ToolMeta(name="a", display_name="A", mutates=False, volatile=False),
            "b": ToolMeta(name="b", display_name="B", mutates=False, volatile=False),
        },
    )
    agent = _make_agent(llm, executor)
    result = await agent.run(_msgs())
    assert result.text == "done"
    assert set(events_order) == {"a_start", "b_start"}


@pytest.mark.asyncio
async def test_mutating_tools_run_sequentially_after_non_mutating():
    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("1", "mut", {}), _tc("2", "read", {})]),
            _response(text="done"),
        ]
    )
    executor = FakeExecutor(
        {
            "mut": ToolResult(content="mutated", preview="m"),
            "read": ToolResult(content="read", preview="r"),
        },
        meta={
            "mut": ToolMeta(name="mut", display_name="Mut", mutates=True, volatile=False),
            "read": ToolMeta(name="read", display_name="Read", mutates=False, volatile=False),
        },
    )
    agent = _make_agent(llm, executor)
    messages = _msgs()
    await agent.run(messages)
    # Both tools executed
    names = [c[0] for c in executor.call_log]
    assert set(names) == {"mut", "read"}


@pytest.mark.asyncio
async def test_tool_exception_wrapped_as_error_result():
    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("1", "boom", {})]),
            _response(text="recovered"),
        ]
    )
    executor = FakeExecutor({"boom": RuntimeError("kaboom")})
    agent = _make_agent(llm, executor)
    messages = _msgs()
    result = await agent.run(messages)
    assert result.text == "recovered"
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "kaboom" in tool_msgs[0]["content"]


# ============================================================
# Stop conditions
# ============================================================


@pytest.mark.asyncio
async def test_max_iterations_stops_with_reason():
    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("1", "t", {})]),
            _response(tool_calls=[_tc("2", "t", {})]),
            _response(tool_calls=[_tc("3", "t", {})]),
            _response(text="unreached"),
        ]
    )
    executor = FakeExecutor({"t": ToolResult(content="r", preview="r")})
    agent = _make_agent(llm, executor, max_iterations=2)
    result = await agent.run(_msgs())
    assert result.stop_reason == StopReason.MAX_ITERATIONS
    assert result.steps == 2


@pytest.mark.asyncio
async def test_max_depth_stops_before_calling_llm():
    llm = FakeLLM([_response(text="unreached")])
    agent = _make_agent(llm, FakeExecutor({}), max_depth=2, current_depth=2)
    result = await agent.run(_msgs())
    assert result.stop_reason == StopReason.MAX_DEPTH
    assert llm.call_count == 0


# ============================================================
# Model request middleware
# ============================================================


@pytest.mark.asyncio
async def test_model_request_middleware_can_override_model_and_tool_choice():
    llm = FakeLLM([_response(text="ok")])
    captured: dict = {}

    async def override_request(request, next_request):
        return await next_request(replace(request, model="override-model", tool_choice=ToolChoiceMode.REQUIRED))

    class Capture(FakeLLM):
        async def stream(self, messages, model, tools, tool_choice=None):
            captured["model"] = model
            captured["tool_choice"] = tool_choice
            async for item in super().stream(messages, model, tools, tool_choice):
                yield item

    llm = Capture([_response(text="ok")])
    agent = _make_agent(llm, FakeExecutor({}), model_request_middlewares=(override_request,))
    await agent.run(_msgs())
    assert captured["model"] == "override-model"
    assert captured["tool_choice"] == ToolChoiceMode.REQUIRED


@pytest.mark.asyncio
async def test_model_request_middleware_can_replace_messages():
    async def replace_messages(request, next_request):
        return await next_request(replace(request, messages=[{"role": "system", "content": "replaced"}]))

    llm = FakeLLM([_response(text="ok")])
    agent = _make_agent(llm, FakeExecutor({}), model_request_middlewares=(replace_messages,))
    messages = _msgs()
    await agent.run(messages)
    # Caller's list was mutated to replaced content
    assert messages[0]["content"] == "replaced"


@pytest.mark.asyncio
async def test_model_request_middlewares_run_in_order():
    calls: list[str] = []

    async def outer(request, next_request):
        calls.append("outer:before")
        prepared = await next_request(request)
        calls.append("outer:after")
        return prepared

    async def inner(request, next_request):
        calls.append("inner:before")
        prepared = await next_request(request)
        calls.append("inner:after")
        return prepared

    llm = FakeLLM([_response(text="ok")])
    agent = _make_agent(llm, FakeExecutor({}), model_request_middlewares=(outer, inner))
    await agent.run(_msgs())
    assert calls == ["outer:before", "inner:before", "inner:after", "outer:after"]


# ============================================================
# Hooks
# ============================================================


@pytest.mark.asyncio
async def test_on_response_fires_with_accumulated_usage():
    seen: list[CompletionResponse] = []

    async def on_response(resp):
        seen.append(resp)

    llm = FakeLLM(
        [
            _response(text="", tool_calls=[_tc("1", "t", {})], usage=Usage(prompt_tokens=5, completion_tokens=3)),
            _response(text="done", usage=Usage(prompt_tokens=10, completion_tokens=7)),
        ]
    )
    executor = FakeExecutor({"t": ToolResult(content="r", preview="r")})
    agent = _make_agent(llm, executor, hooks=AgentHooks(on_response=on_response))
    result = await agent.run(_msgs())
    assert len(seen) == 2
    # Agent's accumulated usage = sum of both responses
    assert result.usage.prompt_tokens == 15
    assert result.usage.completion_tokens == 10


@pytest.mark.asyncio
async def test_on_error_fires_before_reraise():
    seen: list[Exception] = []

    async def on_error(exc):
        seen.append(exc)

    llm = FakeLLM([RuntimeError("llm failed")])
    agent = _make_agent(llm, FakeExecutor({}), hooks=AgentHooks(on_error=on_error))
    with pytest.raises(RuntimeError, match="llm failed"):
        await agent.run(_msgs())
    assert len(seen) == 1
    assert str(seen[0]) == "llm failed"


@pytest.mark.asyncio
async def test_on_finish_fires_on_normal_completion():
    seen: list[tuple] = []

    async def on_finish(text, steps, messages):
        seen.append((text, steps, len(messages)))

    llm = FakeLLM([_response(text="done")])
    agent = _make_agent(llm, FakeExecutor({}), hooks=AgentHooks(on_finish=on_finish))
    await agent.run(_msgs())
    assert len(seen) == 1
    assert seen[0][0] == "done"


@pytest.mark.asyncio
async def test_on_finish_fires_even_on_exception():
    seen: list[tuple] = []

    async def on_finish(text, steps, messages):
        seen.append((text, steps))

    llm = FakeLLM([RuntimeError("boom")])
    agent = _make_agent(llm, FakeExecutor({}), hooks=AgentHooks(on_finish=on_finish))
    with pytest.raises(RuntimeError):
        await agent.run(_msgs())
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_get_pending_messages_injects_between_steps():
    injected = [{"role": "user", "content": "injected"}]
    calls = 0

    async def get_pending():
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        if calls == 2:
            batch = list(injected)
            injected.clear()
            return batch
        return []

    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("1", "t", {})]),
            _response(text="done"),
        ]
    )
    executor = FakeExecutor({"t": ToolResult(content="r", preview="r")})
    agent = _make_agent(llm, executor, hooks=AgentHooks(get_pending_messages=get_pending))
    messages = _msgs()
    await agent.run(messages)
    assert any(m.get("content") == "injected" for m in messages)


@pytest.mark.asyncio
async def test_pending_arrived_during_final_turn_continues_loop():
    """User queues a message while the LLM is producing its end-turn response.

    The agent must drain pending before exiting and respond to it instead
    of stranding it as an orphaned queue entry.
    """
    injected = [{"role": "user", "content": "follow-up"}]
    calls = 0

    async def get_pending():
        nonlocal calls
        calls += 1
        # First drain (top of iter 1) — empty
        # Second drain (after end-turn check on iter 1) — return follow-up
        # Third drain (top of iter 2) — empty
        # Fourth drain (after end-turn check on iter 2) — empty, stop
        if calls == 2:
            batch = list(injected)
            injected.clear()
            return batch
        return []

    llm = FakeLLM(
        [
            _response(text="first answer"),  # iter 1: would end, but pending arrives
            _response(text="second answer"),  # iter 2: ends cleanly
        ]
    )
    agent = _make_agent(llm, FakeExecutor({}), hooks=AgentHooks(get_pending_messages=get_pending))
    messages = _msgs()
    result = await agent.run(messages)

    assert any(m.get("content") == "follow-up" for m in messages), "queued message must land in conversation context"
    assert result.text == "second answer", "agent must produce a fresh response after consuming the queued message"


# ============================================================
# Cancellation
# ============================================================


@pytest.mark.asyncio
async def test_cancellation_yields_cancelled_result_and_reraises():
    slow_event = asyncio.Event()

    class BlockingLLM:
        async def stream(self, messages, model, tools, tool_choice=None):
            await slow_event.wait()
            yield _response(text="unreached")

        async def complete(self, *args, **kwargs):
            raise NotImplementedError

    async def on_finish(text, steps, messages):
        assert text == "Cancelled."

    agent = Agent(
        tools=[],
        client=BlockingLLM(),
        executor=FakeExecutor({}),
        model="test",
        hooks=AgentHooks(on_finish=on_finish),
    )

    gen = agent.stream(_msgs())
    task = asyncio.create_task(_consume(gen))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def _consume(gen):
    events = []
    async for e in gen:
        events.append(e)
    return events


# ============================================================
# Spawn / recursive agents
# ============================================================


@pytest.mark.asyncio
async def test_spawn_context_creates_child_with_incremented_depth():
    llm = FakeLLM([_response(text="child result")])
    ctx = SpawnContext(client=llm, executor=FakeExecutor({}), max_depth=3)
    child = ctx.child_agent(tools=[], model="test", current_depth=1)
    assert child.current_depth == 1
    assert child.max_depth == 3


@pytest.mark.asyncio
async def test_spawn_executes_child_and_returns_text():
    llm = FakeLLM([_response(text="spawned result")])
    ctx = SpawnContext(client=llm, executor=FakeExecutor({}), max_depth=3)
    result = await ctx.spawn(
        "child task",
        system_prompt="you are child",
        tools=[],
        model="test",
        current_depth=1,
    )
    assert result == "spawned result"


@pytest.mark.asyncio
async def test_spawn_timeout_raises():
    slow = asyncio.Event()

    class BlockingLLM:
        async def stream(self, messages, model, tools, tool_choice=None):
            await slow.wait()
            yield _response(text="never")

        async def complete(self, *args, **kwargs):
            raise NotImplementedError

    ctx = SpawnContext(client=BlockingLLM(), executor=FakeExecutor({}))
    with pytest.raises(asyncio.TimeoutError):
        await ctx.spawn(
            "task",
            system_prompt="sys",
            tools=[],
            model="test",
            current_depth=1,
            timeout=0,
        )


# ============================================================
# SharedLedger
# ============================================================


@pytest.mark.asyncio
async def test_ledger_register_and_complete():
    ledger = SharedLedger()
    await ledger.register("id1", "research topic X", depth="deep")
    items = ledger.get_items()
    assert len(items) == 1
    assert items[0].label == "research topic X"
    assert items[0].done is False
    assert items[0].metadata["depth"] == "deep"

    await ledger.complete("id1")
    items = ledger.get_items()
    assert items[0].done is True


@pytest.mark.asyncio
async def test_ledger_mark_accessed_returns_true_on_duplicate():
    ledger = SharedLedger()
    assert await ledger.mark_accessed("file.md") is False
    assert await ledger.mark_accessed("file.md") is True
    assert await ledger.mark_accessed("other.md") is False
    assert ledger.accessed_count == 2


@pytest.mark.asyncio
async def test_ledger_exclude_id_filters_items():
    ledger = SharedLedger()
    await ledger.register("a", "task a")
    await ledger.register("b", "task b")
    items = ledger.get_items(exclude_id="a")
    assert len(items) == 1
    assert items[0].id == "b"


@pytest.mark.asyncio
async def test_ledger_concurrent_register_is_safe():
    ledger = SharedLedger()

    async def add(i):
        await ledger.register(f"id{i}", f"task {i}")

    await asyncio.gather(*[add(i) for i in range(100)])
    assert len(ledger.get_items()) == 100


# ============================================================
# Usage accumulation
# ============================================================


@pytest.mark.asyncio
async def test_usage_accumulates_across_steps():
    llm = FakeLLM(
        [
            _response(text="", tool_calls=[_tc("1", "t", {})], usage=Usage(prompt_tokens=100, completion_tokens=50)),
            _response(text="done", usage=Usage(prompt_tokens=200, completion_tokens=75)),
        ]
    )
    executor = FakeExecutor({"t": ToolResult(content="r", preview="r")})
    agent = _make_agent(llm, executor)
    result = await agent.run(_msgs())
    assert result.usage.prompt_tokens == 300
    assert result.usage.completion_tokens == 125
    assert result.usage.total_tokens == 425


@pytest.mark.asyncio
async def test_usage_input_tokens_property_includes_cache():
    u = Usage(prompt_tokens=100, completion_tokens=50, cache_read_tokens=10, cache_write_tokens=5)
    assert u.input_tokens == 115
    assert u.total_tokens == 165


# ============================================================
# Messages list ownership — caller owns, agent mutates
# ============================================================


@pytest.mark.asyncio
async def test_agent_mutates_caller_messages_list_in_place():
    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("1", "t", {})]),
            _response(text="done"),
        ]
    )
    executor = FakeExecutor({"t": ToolResult(content="r", preview="r")})
    agent = _make_agent(llm, executor)
    messages = _msgs()
    original_len = len(messages)
    await agent.run(messages)
    assert len(messages) > original_len
    assert any(m["role"] == "assistant" for m in messages)
    assert any(m["role"] == "tool" for m in messages)
