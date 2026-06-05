from datetime import UTC, datetime

import pytest

import ntrp.tools.background as background_module
from ntrp.context.models import SessionState
from ntrp.core.spawner import SpawnResult
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry


@pytest.mark.asyncio
async def test_background_tool_spawns_detached_background_research_agent():
    captured = {}

    async def spawn_fn(ctx, task, **kwargs):
        captured["task"] = task
        captured.update(kwargs)
        return SpawnResult(
            text="Background task agent-1 started: scan docs",
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
    assert result.content == "Background task agent-1 started: scan docs"
    assert result.data == {
        "child_agent": {
            "child_run_id": "agent-1",
            "parent_tool_call_id": "background-1",
            "agent_type": "background_research",
            "wait": False,
            "status": "running",
        }
    }
