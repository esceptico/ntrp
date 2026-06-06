import asyncio
import contextlib
from datetime import UTC, datetime

import pytest

import ntrp.tools.background as background_module
from ntrp.context.models import SessionState
from ntrp.core.spawner import SpawnResult
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry


def _ctx(registry: BackgroundTaskRegistry) -> ToolContext:
    return ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=registry,
    )


async def _register_live(registry: BackgroundTaskRegistry, task_id: str, command: str) -> asyncio.Task:
    task = asyncio.create_task(asyncio.sleep(3600))
    registry.register(task_id, task, command=command)
    return task


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_background_tool_spawns_detached_background_research_agent():
    captured = {}

    async def spawn_fn(ctx, task, **kwargs):
        captured["task"] = task
        captured.update(kwargs)
        return SpawnResult(
            text="Started a background agent to: scan docs",
            child_run_id="agent-1",
            parent_tool_call_id="background-1",
            agent_type="background_research",
            wait=False,
            status="running",
        )

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=ToolRegistry(),
        run=RunContext(run_id="run-1", current_depth=0, max_depth=3),
        io=IOBridge(),
        background_tasks=BackgroundTaskRegistry(session_id="test"),
    )
    ctx.spawn_fn = spawn_fn
    execution = ToolExecution(tool_id="background-1", tool_name="background", ctx=ctx)

    result = await background_module.background(
        execution,
        background_module.BackgroundInput(task="scan docs"),
    )

    assert captured["task"] == "scan docs"
    assert captured["parent_id"] == "background-1"
    assert captured["agent_type"] == "background_research"
    assert captured["wait"] is False
    assert "background" not in captured
    assert result.content == "Started a background agent to: scan docs"
    assert result.data == {
        "child_agent": {
            "child_run_id": "agent-1",
            "parent_tool_call_id": "background-1",
            "agent_type": "background_research",
            "wait": False,
            "status": "running",
        }
    }


def test_background_tool_is_agent_kind():
    assert background_module.background_tool.kind == "agent"


@pytest.mark.asyncio
async def test_send_to_agent_delivers_to_running_agent():
    registry = BackgroundTaskRegistry(session_id="test")
    task = await _register_live(registry, "agent-1", "scan docs")
    try:
        execution = ToolExecution(tool_id="t", tool_name="send_to_agent", ctx=_ctx(registry))
        result = await background_module.send_to_agent(
            execution,
            background_module.SendToAgentInput(agent_id="agent-1", message="also check pricing"),
        )
        assert not result.is_error
        assert "agent-1" in result.content

        drained = registry.drain_injections("agent-1")
        assert len(drained) == 1
        assert drained[0]["role"] == "user"
        assert "also check pricing" in drained[0]["content"]
        # drained exactly once
        assert registry.drain_injections("agent-1") == []
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_send_to_agent_unknown_id_lists_running_agents():
    registry = BackgroundTaskRegistry(session_id="test")
    task = await _register_live(registry, "agent-live", "scan docs")
    try:
        execution = ToolExecution(tool_id="t", tool_name="send_to_agent", ctx=_ctx(registry))
        result = await background_module.send_to_agent(
            execution,
            background_module.SendToAgentInput(agent_id="agent-missing", message="hi"),
        )
        assert result.is_error
        assert "agent-live" in result.content
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_queue_injection_skips_finished_agent():
    registry = BackgroundTaskRegistry(session_id="test")
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    registry.register("agent-done", done, command="x")
    assert registry.queue_injection("agent-done", {"role": "user", "content": "x"}) is False
    assert registry.queue_injection("agent-never-existed", {"role": "user", "content": "x"}) is False
