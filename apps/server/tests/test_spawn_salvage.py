"""Tests for the spawn-failure salvage path: when a sub-agent's LLM call
errors mid-run, we summarize the tool results gathered so far instead of
returning a bare error string."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ntrp.agent import Choice, CompletionResponse, FunctionCall, Message, Result, StopReason, ToolCall, Usage
from ntrp.agent.types.tools import ToolMeta
from ntrp.agent.types.tools import ToolResult as AgentToolResult
from ntrp.context.models import ProjectContext, SessionState
from ntrp.core import spawner as spawner_module
from ntrp.core.spawner import (
    _clamp_for_salvage,
    _deterministic_salvage,
    _salvage_summary,
    create_spawn_fn,
)
from ntrp.events.sse import TaskFinishedEvent, TaskProgressEvent, TaskStartedEvent, TokenUsageEvent
from ntrp.server.state import RunRegistry
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext
from tests.helpers import make_executor


class ParentTracker:
    def __init__(self, cost: float = 0.0):
        self.cost = cost


@pytest.mark.asyncio
async def test_spawned_agent_prompt_includes_project_context(monkeypatch):
    captured = {}

    class FakeAgent:
        async def stream(self, messages):
            captured["messages"] = messages
            yield Result(text="done", stop_reason=StopReason.END_TURN, steps=1, usage=Usage())

    monkeypatch.setattr(spawner_module, "Agent", lambda **kwargs: FakeAgent())

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
        project=ProjectContext(
            project_id="proj-1",
            name="Ntrp",
            default_cwd="/Users/me/src/ntrp",
            instructions="Use the repo conventions.",
            knowledge_scope="project:proj-1",
        ),
    )

    spawn = create_spawn_fn(executor=executor, model="test-model", max_depth=3, current_depth=0)
    result = await spawn(ctx, "research task", system_prompt="child prompt", tools=[])

    assert result.text == "done"
    prompt = captured["messages"][0]["content"]
    assert "## PROJECT" in prompt
    assert "Name: Ntrp" in prompt
    assert "Default cwd: /Users/me/src/ntrp" in prompt
    assert "Instructions:\nUse the repo conventions." in prompt


def test_clamp_for_salvage_leaves_short_messages_alone():
    msg = {"role": "tool", "content": "small"}
    assert _clamp_for_salvage(msg) is msg


def test_clamp_for_salvage_truncates_long_tool_content():
    long_content = "x" * 10_000
    out = _clamp_for_salvage({"role": "tool", "content": long_content, "tool_call_id": "abc"})
    assert len(out["content"]) < 5000
    assert "[clamped for salvage summary]" in out["content"]
    assert out["tool_call_id"] == "abc"


def test_clamp_for_salvage_skips_user_and_system():
    long = "x" * 10_000
    assert _clamp_for_salvage({"role": "user", "content": long})["content"] == long
    assert _clamp_for_salvage({"role": "system", "content": long})["content"] == long


def test_deterministic_salvage_includes_tail_tool_results():
    msgs = [
        {"role": "user", "content": "find stuff"},
        {"role": "assistant", "content": None},
        {"role": "tool", "content": "first finding"},
        {"role": "tool", "content": "second finding"},
    ]
    out = _deterministic_salvage(msgs, "boom")
    assert "[partial — sub-agent errored: boom]" in out
    assert "first finding" in out
    assert "second finding" in out


def test_deterministic_salvage_with_no_tool_results():
    out = _deterministic_salvage([{"role": "user", "content": "x"}], "boom")
    assert "(none)" in out


@pytest.mark.asyncio
async def test_salvage_summary_calls_llm_with_clamped_messages(monkeypatch):
    captured: dict = {}

    class FakeClient:
        async def complete(self, model, messages, **kwargs):
            captured["model"] = model
            captured["messages"] = messages
            return CompletionResponse(
                choices=[
                    Choice(
                        message=Message(role="assistant", content="here is what i found", tool_calls=None, reasoning_content=None),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(),
                model=model,
            )

    monkeypatch.setattr(spawner_module, "llm_client", FakeClient())

    summary = await _salvage_summary(
        model="m",
        child_messages=[{"role": "tool", "content": "x" * 10_000}],
        error="boom",
        task="research X",
    )
    assert summary == "here is what i found"
    # The salvage adds a final user message asking for the summary.
    assert captured["messages"][-1]["role"] == "user"
    assert "boom" in captured["messages"][-1]["content"]
    assert "research X" in captured["messages"][-1]["content"]
    # The original tool message was clamped.
    assert "[clamped for salvage summary]" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_salvage_summary_returns_empty_when_llm_also_fails(monkeypatch):
    class FakeClient:
        async def complete(self, *_, **__):
            raise RuntimeError("llm dead")

    monkeypatch.setattr(spawner_module, "llm_client", FakeClient())

    summary = await _salvage_summary("m", [{"role": "tool", "content": "x"}], "boom", "task")
    assert summary == ""


@pytest.mark.asyncio
async def test_spawn_emits_foreground_task_lifecycle_on_success(monkeypatch):
    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            yield CompletionResponse(
                choices=[
                    Choice(
                        message=Message(role="assistant", content="done", tool_calls=None, reasoning_content=None),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(),
                model=model,
            )

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
        system_prompt="sys",
        tools=[],
        parent_id="call-research",
        timeout=1,
    )

    assert result.text == "done"
    task_events = [event for event in emitted if isinstance(event, (TaskStartedEvent, TaskFinishedEvent))]
    assert [event.type.value for event in task_events] == ["task_started", "task_finished"]
    assert task_events[0].run_id == "run-1"
    assert task_events[0].task_id == "call-research"
    assert task_events[0].parent_tool_call_id == "call-research"
    assert task_events[0].depth == 1
    assert task_events[1].status == "completed"


@pytest.mark.asyncio
async def test_foreground_subagent_emits_generated_name_while_running(monkeypatch):
    emitted = []

    async def emit(event):
        emitted.append(event)

    async def fake_generate_agent_name(model: str, task: str) -> str:
        await asyncio.sleep(0)
        return "Web Release Scout"

    class FakeAgent:
        async def stream(self, messages):
            await asyncio.sleep(0.01)
            yield Result(text="done", stop_reason=StopReason.END_TURN, steps=1, usage=Usage())

    monkeypatch.setattr(spawner_module, "generate_agent_name", fake_generate_agent_name)
    monkeypatch.setattr(spawner_module, "Agent", lambda **kwargs: FakeAgent())

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
        "do web research",
        system_prompt="sys",
        tools=[],
        parent_id="call-research",
        timeout=1,
    )

    assert result.text == "done"
    task_events = [
        event
        for event in emitted
        if isinstance(event, (TaskStartedEvent, TaskProgressEvent, TaskFinishedEvent))
    ]
    assert [event.type.value for event in task_events] == ["task_started", "task_progress", "task_finished"]
    assert task_events[0].name == ""
    assert task_events[1].name == "Web Release Scout"
    assert task_events[1].parent_tool_call_id == "call-research"
    assert task_events[2].name == "Web Release Scout"


@pytest.mark.asyncio
async def test_foreground_subagent_cancel_returns_partial_summary(monkeypatch):
    emitted = []

    async def emit(event):
        emitted.append(event)

    class SlowAgent:
        hooks = SimpleNamespace(on_response=None)

        async def stream(self, messages):
            messages.append({"role": "assistant", "content": "Found useful evidence."})
            await asyncio.sleep(60)

    monkeypatch.setattr(spawner_module, "Agent", lambda **kwargs: SlowAgent())
    monkeypatch.setattr(spawner_module, "_salvage_summary", AsyncMock(return_value="Partial summary."))

    executor = make_executor()
    registry = RunRegistry()
    parent_run = registry.create_run("test")
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id=parent_run.run_id, current_depth=0, max_depth=3),
        io=IOBridge(emit=emit),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
        run_registry=registry,
    )

    spawn = create_spawn_fn(executor=executor, model="test-model", max_depth=3, current_depth=0)
    task = asyncio.create_task(
        spawn(
            ctx,
            "research trace replay",
            system_prompt="sys",
            tools=[],
            parent_id="call-research",
        )
    )
    await asyncio.sleep(0)

    result = registry.cancel_subagent(parent_run.run_id, "call-research")
    assert result == {"found": True, "cancel_requested": True}

    spawn_result = await task
    assert "partial" in spawn_result.text.lower()
    assert "Partial summary." in spawn_result.text
    assert any(getattr(event, "status", None) == "cancelled" for event in emitted)


@pytest.mark.asyncio
async def test_spawn_cost_budget_uses_parent_spend(monkeypatch):
    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            raise AssertionError("child should stop before model call")
            yield  # pragma: no cover

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
        parent_tracker=ParentTracker(cost=1.0),
    )

    spawn = create_spawn_fn(
        executor=executor,
        model="test-model",
        max_depth=3,
        current_depth=0,
        max_cost=1.0,
    )
    result = await spawn(ctx, "research task", system_prompt="sys", tools=[], timeout=1)

    assert result.text == ""


@pytest.mark.asyncio
async def test_spawn_tool_call_budget_is_shared_with_parent(monkeypatch):
    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            raise AssertionError("child should stop before model call")
            yield  # pragma: no cover

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3, max_tool_calls=1),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    assert ctx.run.budget is not None
    ctx.run.budget.tool_calls = 1

    spawn = create_spawn_fn(
        executor=executor,
        model="test-model",
        max_depth=3,
        current_depth=0,
        max_tool_calls=1,
    )
    result = await spawn(ctx, "research task", system_prompt="sys", tools=[], timeout=1)

    assert result.text == ""


@pytest.mark.asyncio
async def test_spawn_wall_time_budget_uses_parent_start(monkeypatch):
    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            raise AssertionError("child should stop before model call")
            yield  # pragma: no cover

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3, started_at=0.0),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    spawn = create_spawn_fn(
        executor=executor,
        model="test-model",
        max_depth=3,
        current_depth=0,
        max_wall_time_seconds=0.0,
    )
    result = await spawn(ctx, "research task", system_prompt="sys", tools=[], timeout=1)

    assert result.text == ""


@pytest.mark.asyncio
async def test_background_spawn_rolls_cost_into_parent_tracker(monkeypatch):
    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            yield CompletionResponse(
                choices=[
                    Choice(
                        message=Message(role="assistant", content="done", tool_calls=None, reasoning_content=None),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(prompt_tokens=10),
                model=model,
            )

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    parent_tracker = ParentTracker(cost=0.0)
    executor = make_executor()
    bg_registry = BackgroundTaskRegistry(session_id="test")
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=bg_registry,
        parent_tracker=parent_tracker,
    )

    spawn = create_spawn_fn(executor=executor, model="claude-sonnet-4-6", max_depth=3, current_depth=0)
    result = await spawn(ctx, "task", system_prompt="sys", tools=[], background=True, timeout=1)
    task_id = result.text.removeprefix("Background task ").split(" started:", 1)[0]
    task = bg_registry._tasks[task_id]

    await task

    assert parent_tracker.cost > 0
    assert task.done()
    assert task_id not in bg_registry._tasks


@pytest.mark.asyncio
async def test_spawn_emits_live_token_usage_for_child_response(monkeypatch):
    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            yield CompletionResponse(
                choices=[
                    Choice(
                        message=Message(role="assistant", content="done", tool_calls=None, reasoning_content=None),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=2, cache_read_tokens=3),
                model=model,
            )

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    async def slow_agent_name(model, task):
        await asyncio.sleep(2)
        return "Slow label"

    monkeypatch.setattr(spawner_module, "generate_agent_name", slow_agent_name)

    emitted = []

    async def emit(event):
        emitted.append(event)

    parent_tracker = ParentTracker(cost=0.0)
    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(emit=emit),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
        parent_tracker=parent_tracker,
    )

    spawn = create_spawn_fn(executor=executor, model="claude-sonnet-4-6", max_depth=3, current_depth=0)

    await spawn(ctx, "task", system_prompt="sys", tools=[], timeout=1)

    usage_events = [event for event in emitted if isinstance(event, TokenUsageEvent)]
    assert len(usage_events) == 1
    assert usage_events[0].run_id == "run-1"
    assert usage_events[0].usage == {"prompt": 10, "completion": 2, "total": 15, "cache_read": 3, "cache_write": 0}
    assert usage_events[0].cost == parent_tracker.cost


@pytest.mark.asyncio
async def test_spawn_returns_salvage_when_inner_agent_fails(monkeypatch):
    """End-to-end: the inner agent's LLM call raises, and spawn returns
    a partial-summary string instead of letting the exception escape."""
    salvage_text = "Found 3 things before the error."

    class FakeLLM:
        def __init__(self):
            self.complete_calls = 0

        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            # The inner agent's first model call simulates a fatal LLM error.
            raise RuntimeError("oops")
            yield  # pragma: no cover  # keep generator-typed

        async def complete(self, model, messages, **kwargs):
            self.complete_calls += 1
            return CompletionResponse(
                choices=[
                    Choice(
                        message=Message(role="assistant", content=salvage_text, tool_calls=None, reasoning_content=None),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(),
                model=model,
            )

    fake = FakeLLM()
    monkeypatch.setattr(spawner_module, "llm_client", fake)

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
        system_prompt="sys",
        tools=[],
        parent_id="call",
        timeout=1,
    )

    assert "[partial — sub-agent errored:" in result.text
    assert salvage_text in result.text
    assert fake.complete_calls == 1
    task_events = [event for event in emitted if isinstance(event, (TaskStartedEvent, TaskFinishedEvent))]
    assert [event.type.value for event in task_events] == ["task_started", "task_finished"]
    assert task_events[1].status == "failed"


@pytest.mark.asyncio
async def test_spawn_uses_reasoning_effort_for_model_override(monkeypatch):
    captured: dict = {}

    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            captured["model"] = model
            captured["reasoning_effort"] = reasoning_effort
            yield CompletionResponse(
                choices=[
                    Choice(
                        message=Message(role="assistant", content="done", tool_calls=None, reasoning_content=None),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(),
                model=model,
            )

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    spawn = create_spawn_fn(
        executor=executor,
        model="chat-model",
        max_depth=3,
        current_depth=0,
        reasoning_effort="low",
        model_reasoning_efforts={"research-model": "max"},
    )
    result = await spawn(
        ctx,
        "research task",
        system_prompt="sys",
        tools=[],
        model_override="research-model",
        parent_id="call",
        timeout=1,
    )

    assert result.text == "done"
    assert captured == {"model": "research-model", "reasoning_effort": "max"}


@pytest.mark.asyncio
async def test_spawn_salvage_preserves_tool_results_after_loop_progress(monkeypatch):
    """The real scenario: sub-agent runs several tool calls successfully,
    then the LLM dies on the next iteration. Salvage must see the tool
    results that were already accumulated — that's the entire point of
    the feature (don't throw away ~200 tool calls of paid work)."""
    captured_salvage_messages: list = []

    class FakeLLM:
        def __init__(self):
            self.stream_calls = 0

        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            self.stream_calls += 1
            if self.stream_calls == 1:
                # First call: agent decides to invoke a tool. The agent
                # loop will then dispatch it and append the tool result
                # to the messages list, before looping back for call 2.
                yield CompletionResponse(
                    choices=[
                        Choice(
                            message=Message(
                                role="assistant",
                                content=None,
                                tool_calls=[
                                    ToolCall(
                                        id="call_1",
                                        type="function",
                                        function=FunctionCall(name="finder", arguments="{}"),
                                    )
                                ],
                                reasoning_content=None,
                            ),
                            finish_reason="tool_calls",
                        )
                    ],
                    usage=Usage(),
                    model=model,
                )
                return
            # Second call: simulate a fatal LLM error mid-loop.
            raise RuntimeError("api blew up")

        async def complete(self, model, messages, **kwargs):
            captured_salvage_messages.append(messages)
            return CompletionResponse(
                choices=[
                    Choice(
                        message=Message(
                            role="assistant",
                            content="Recovered: found one thing about apricots.",
                            tool_calls=None,
                            reasoning_content=None,
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(),
                model=model,
            )

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    class FinderExecutor:
        async def execute(self, name, args, tool_call_id):
            return AgentToolResult(content="apricots are good", preview="apricots", is_error=False)

        def get_meta(self, name):
            return ToolMeta(name="finder", display_name="Finder", kind="tool")

    monkeypatch.setattr(
        "ntrp.core.spawner.NtrpToolExecutor", lambda *_args, **_kwargs: FinderExecutor()
    )

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    spawn = create_spawn_fn(executor=executor, model="test-model", max_depth=3, current_depth=0)
    result = await spawn(
        ctx,
        "find things about apricots",
        system_prompt="sys",
        tools=[],
        parent_id="call",
        timeout=5,
    )

    assert "[partial — sub-agent errored:" in result.text
    assert "Recovered: found one thing about apricots." in result.text
    # Verify the salvage call actually saw the tool result — that's the
    # whole point. Find the tool message in what we sent to `complete`.
    salvage_msgs = captured_salvage_messages[0]
    tool_msgs = [m for m in salvage_msgs if m.get("role") == "tool"]
    assert tool_msgs, f"no tool messages in salvage payload: {salvage_msgs}"
    assert any("apricots are good" in (m.get("content") or "") for m in tool_msgs)


@pytest.mark.asyncio
async def test_spawn_salvages_on_foreground_timeout(monkeypatch):
    """If the foreground sub-agent hits the wait_for timeout, we still
    return a salvage summary instead of a bare timeout error."""
    import asyncio as _aio

    class FakeLLM:
        async def stream(self, messages, model, tools, tool_choice=None, reasoning_effort=None, prompt_cache_key=None):
            # Sleep longer than the spawn timeout to force a TimeoutError.
            await _aio.sleep(10)
            yield  # pragma: no cover

        async def complete(self, model, messages, **kwargs):
            return CompletionResponse(
                choices=[
                    Choice(
                        message=Message(
                            role="assistant",
                            content="best-effort summary",
                            tool_calls=None,
                            reasoning_content=None,
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(),
                model=model,
            )

    monkeypatch.setattr(spawner_module, "llm_client", FakeLLM())

    executor = make_executor()
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )

    spawn = create_spawn_fn(executor=executor, model="test-model", max_depth=3, current_depth=0)
    result = await spawn(
        ctx,
        "task",
        system_prompt="sys",
        tools=[],
        parent_id="call",
        timeout=0.1,
    )

    assert "[partial — sub-agent timed out" in result.text
    assert "best-effort summary" in result.text


def test_clamp_for_salvage_handles_list_typed_content():
    """List-typed content (multi-part blocks from vision/tool results)
    must also be clamped — otherwise an oversized blob bypasses the
    safety net and can re-trigger the same context-length failure."""
    blocks = [{"type": "text", "text": "a" * 8000}, {"type": "text", "text": "b" * 8000}]
    out = _clamp_for_salvage({"role": "tool", "content": blocks, "tool_call_id": "x"})
    assert isinstance(out["content"], str)
    assert len(out["content"]) < 5000
    assert "[clamped for salvage summary]" in out["content"]
