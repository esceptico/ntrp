"""Agent loop tests — mock LLM, real tool execution."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from ntrp.channel import Channel
from ntrp.core.agent import Agent
from ntrp.events.sse import SSEEvent, ToolCallEvent, ToolResultEvent
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.executor import ToolExecutor
from tests.helpers import MockCompletionClient, make_text_response, make_tool_response


class EchoTool(Tool):
    name = "echo"
    display_name = "Echo"
    description = "Echoes input back"

    async def execute(self, execution: ToolExecution, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(content=f"echo: {text}", preview="echo")


class FailTool(Tool):
    name = "fail"
    display_name = "Fail"
    description = "Always fails"

    async def execute(self, execution: ToolExecution, **kwargs) -> ToolResult:
        raise RuntimeError("tool crashed")


def _make_executor(*tools: Tool) -> ToolExecutor:
    executor = ToolExecutor.__new__(ToolExecutor)
    executor._get_services = dict
    executor.registry = ToolRegistry()
    for tool in tools:
        executor.registry.register(tool)
    return executor


def _make_ctx(executor: ToolExecutor) -> ToolContext:
    from ntrp.context.models import SessionState

    return ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=executor.registry,
        run=RunContext(run_id="run-1"),
        io=IOBridge(),
        channel=Channel(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )


def _make_agent(client: MockCompletionClient, executor: ToolExecutor, ctx: ToolContext) -> Agent:
    tools = executor.get_tools()
    agent = Agent(
        tools=tools,
        tool_executor=executor,
        model="test-model",
        system_prompt="You are a test assistant.",
        ctx=ctx,
    )
    agent._track_usage = lambda response: None
    return agent


@pytest.mark.asyncio
async def test_simple_text_response():
    client = MockCompletionClient([make_text_response("Hello!")])
    executor = _make_executor()
    ctx = _make_ctx(executor)
    agent = _make_agent(client, executor, ctx)

    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        result = await agent.run("Hi")

    assert result == "Hello!"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_tool_call_then_response():
    client = MockCompletionClient(
        [
            make_tool_response("echo", {"text": "world"}),
            make_text_response("Got: echo: world"),
        ]
    )
    executor = _make_executor(EchoTool())
    ctx = _make_ctx(executor)
    agent = _make_agent(client, executor, ctx)

    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        result = await agent.run("Echo world")

    assert result == "Got: echo: world"
    assert len(client.calls) == 2
    # Verify tool result was appended to messages
    tool_msg = [m for m in agent.messages if m["role"] == "tool"]
    assert len(tool_msg) == 1
    assert "echo: world" in tool_msg[0]["content"]


@pytest.mark.asyncio
async def test_tool_error_handled():
    client = MockCompletionClient(
        [
            make_tool_response("fail", {}),
            make_text_response("Tool failed, sorry."),
        ]
    )
    executor = _make_executor(FailTool())
    ctx = _make_ctx(executor)
    agent = _make_agent(client, executor, ctx)

    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        result = await agent.run("Do something")

    assert result == "Tool failed, sorry."
    tool_msg = [m for m in agent.messages if m["role"] == "tool"]
    assert len(tool_msg) == 1
    assert "Error" in tool_msg[0]["content"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    client = MockCompletionClient(
        [
            make_tool_response("nonexistent", {"x": 1}),
            make_text_response("I couldn't find that tool."),
        ]
    )
    executor = _make_executor()
    ctx = _make_ctx(executor)
    agent = _make_agent(client, executor, ctx)

    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        result = await agent.run("Call missing tool")

    assert result == "I couldn't find that tool."


@pytest.mark.asyncio
async def test_stream_yields_events_in_order():
    client = MockCompletionClient(
        [
            make_tool_response("echo", {"text": "hi"}),
            make_text_response("Done."),
        ]
    )
    executor = _make_executor(EchoTool())
    ctx = _make_ctx(executor)
    agent = _make_agent(client, executor, ctx)

    events = []
    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        async for item in agent.stream("test"):
            events.append(item)

    sse_events = [e for e in events if isinstance(e, SSEEvent)]
    assert any(isinstance(e, ToolCallEvent) for e in sse_events)
    assert any(isinstance(e, ToolResultEvent) for e in sse_events)
    # Final item is the text result
    assert events[-1] == "Done."


@pytest.mark.asyncio
async def test_max_depth_stops_agent():
    client = MockCompletionClient([make_text_response("Should not run")])
    executor = _make_executor()
    ctx = _make_ctx(executor)
    ctx.run.max_depth = 2

    agent = Agent(
        tools=[],
        tool_executor=executor,
        model="test-model",
        system_prompt="test",
        ctx=ctx,
        max_depth=2,
        current_depth=2,
    )
    agent._track_usage = lambda response: None

    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        result = await agent.run("Hi")

    assert "Max depth" in result
    assert len(client.calls) == 0


@pytest.mark.asyncio
async def test_inject_queue_processed():
    """Messages injected mid-run are picked up on the next iteration."""
    client = MockCompletionClient(
        [
            make_tool_response("echo", {"text": "first"}),
            make_text_response("Final answer"),
        ]
    )
    executor = _make_executor(EchoTool())
    ctx = _make_ctx(executor)
    agent = _make_agent(client, executor, ctx)

    # Inject a message that should appear in context
    agent.inject_queue.append({"role": "user", "content": "injected message"})

    with patch("ntrp.core.agent.get_completion_client", return_value=client):
        result = await agent.run("Start")

    assert result == "Final answer"
    # The injected message should be in the agent's message history
    contents = [m.get("content") for m in agent.messages]
    assert "injected message" in contents
