from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from ntrp.agent import Result, StopReason, Usage
from ntrp.agent.model_request import ModelRequest
from ntrp.agent.types.tool_choice import ToolChoiceMode
from ntrp.context.models import SessionState
from ntrp.core.compaction_model_request_middleware import CompactionModelRequestMiddleware
from ntrp.core.deferred_tools_middleware import DeferredToolsModelRequestMiddleware
from ntrp.core.spawner import create_spawn_fn
from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.deferred import build_deferred_tools_prompt, build_deferred_tools_prompt_for_schemas, load_tools_tool


class SearchInput(BaseModel):
    query: str = ""


async def fake_search(execution: ToolExecution, args: SearchInput) -> ToolResult:
    return ToolResult(content=f"searched: {args.query}", preview="searched")


async def fake_echo(execution: ToolExecution, args: SearchInput) -> ToolResult:
    return ToolResult(content=args.query, preview="echo")


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("load_tools", load_tools_tool, source="_system")
    registry.register("echo", tool(description="Always visible echo", input_model=SearchInput, execute=fake_echo), source="_system")
    registry.register(
        "background",
        tool(description="Spawn a background agent", input_model=SearchInput, execute=fake_search),
        source="_background",
    )
    registry.register(
        "notify",
        tool(description="Send a notification", input_model=SearchInput, mutates=True, execute=fake_search),
        source="_notifications",
    )
    registry.register(
        "set_directives",
        tool(description="Update persistent behavior directives", input_model=SearchInput, mutates=True, execute=fake_search),
        source="_directives",
    )
    registry.register(
        "slack_search",
        tool(description="Search Slack messages across the workspace", input_model=SearchInput, execute=fake_search),
        source="slack",
    )
    return registry


def _request(registry: ToolRegistry) -> ModelRequest:
    return ModelRequest(
        step=0,
        messages=[],
        model="test",
        tools=registry.get_schemas(),
        tool_choice=ToolChoiceMode.AUTO,
        reasoning_effort=None,
        previous_response=None,
    )


async def _identity(req: ModelRequest) -> ModelRequest:
    return req


class AlwaysCompacts:
    async def maybe_compact(self, messages: list[dict], model: str, last_input_tokens: int | None) -> list[dict] | None:
        return [{"role": "system", "content": "compacted"}]


@pytest.mark.asyncio
async def test_deferred_middleware_hides_then_reveals_loaded_tools():
    registry = _registry()
    run = RunContext(run_id="run", deferred_tools_enabled=True)
    middleware = DeferredToolsModelRequestMiddleware(registry=registry, run=run, get_services=dict)

    prepared = await middleware(_request(registry), _identity)
    names = {t["function"]["name"] for t in prepared.tools}
    assert "load_tools" in names
    assert "echo" in names
    assert "background" not in names
    assert "notify" not in names
    assert "set_directives" not in names
    assert "slack_search" not in names

    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=registry,
        run=run,
        io=IOBridge(),
    )
    result = await registry.execute(
        "load_tools",
        ToolExecution(tool_id="call_load", tool_name="load_tools", ctx=ctx),
        {"group": "slack"},
    )
    assert not result.is_error
    assert "slack_search" in run.loaded_tools

    prepared = await middleware(_request(registry), _identity)
    names = {t["function"]["name"] for t in prepared.tools}
    assert "slack_search" in names


@pytest.mark.asyncio
async def test_compaction_unloads_deferred_tools_after_current_request():
    registry = _registry()
    run = RunContext(run_id="run", deferred_tools_enabled=True, loaded_tools={"slack_search"})
    deferred = DeferredToolsModelRequestMiddleware(registry=registry, run=run, get_services=dict)
    compaction = CompactionModelRequestMiddleware(
        compactor=AlwaysCompacts(),
        on_compact=run.loaded_tools.clear,
    )

    async def compacting_next(req: ModelRequest) -> ModelRequest:
        return await compaction(req, _identity)

    prepared = await deferred(_request(registry), compacting_next)
    names = {t["function"]["name"] for t in prepared.tools}
    assert "slack_search" in names
    assert prepared.messages == [{"role": "system", "content": "compacted"}]
    assert run.loaded_tools == set()

    next_prepared = await deferred(_request(registry), _identity)
    next_names = {t["function"]["name"] for t in next_prepared.tools}
    assert "slack_search" not in next_names


@pytest.mark.asyncio
async def test_load_group_respects_run_allowed_names():
    registry = _registry()
    registry.register(
        "slack_post",
        tool(description="Post to Slack", input_model=SearchInput, mutates=True, execute=fake_search),
        source="slack",
    )
    run = RunContext(
        run_id="run",
        deferred_tools_enabled=True,
        allowed_tool_names={"load_tools", "echo", "slack_search"},
    )
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=registry,
        run=run,
        io=IOBridge(),
    )

    result = await registry.execute(
        "load_tools",
        ToolExecution(tool_id="call_load", tool_name="load_tools", ctx=ctx),
        {"group": "slack"},
    )

    assert not result.is_error
    assert "slack_search" in run.loaded_tools
    assert "slack_post" not in run.loaded_tools
    assert "Not allowed" not in result.content


def test_deferred_prompt_lists_groups_and_tools():
    registry = _registry()
    prompt = build_deferred_tools_prompt(registry, frozenset())
    assert prompt is not None
    assert 'name="slack"' in prompt
    assert "slack_search" in prompt
    assert 'name="background"' in prompt
    assert "background" in prompt
    assert 'name="notifications"' in prompt
    assert "notify" in prompt
    assert 'name="directives"' in prompt
    assert "set_directives" in prompt
    assert "load_tools" in prompt


def test_deferred_prompt_respects_allowed_tool_schemas():
    registry = _registry()

    prompt = build_deferred_tools_prompt_for_schemas(registry, frozenset(), registry.get_schemas(names={"echo"}))
    assert prompt is None

    prompt = build_deferred_tools_prompt_for_schemas(
        registry,
        frozenset(),
        registry.get_schemas(names={"load_tools", "echo", "slack_search"}),
    )
    assert prompt is not None
    assert 'name="slack"' in prompt
    assert "slack_search" in prompt
    assert "background" not in prompt
    assert "notify" not in prompt
    assert "set_directives" not in prompt


@pytest.mark.asyncio
async def test_background_notifications_and_directives_load_by_group_aliases():
    registry = _registry()
    run = RunContext(run_id="run", deferred_tools_enabled=True)
    ctx = ToolContext(
        session_state=SessionState(session_id="test", started_at=datetime.now(UTC)),
        registry=registry,
        run=run,
        io=IOBridge(),
    )

    background_result = await registry.execute(
        "load_tools",
        ToolExecution(tool_id="call_bg", tool_name="load_tools", ctx=ctx),
        {"group": "background"},
    )
    notify_result = await registry.execute(
        "load_tools",
        ToolExecution(tool_id="call_notify", tool_name="load_tools", ctx=ctx),
        {"group": "notify"},
    )
    directives_result = await registry.execute(
        "load_tools",
        ToolExecution(tool_id="call_directives", tool_name="load_tools", ctx=ctx),
        {"group": "directives"},
    )

    assert not background_result.is_error
    assert not notify_result.is_error
    assert not directives_result.is_error
    assert "background" in run.loaded_tools
    assert "notify" in run.loaded_tools
    assert "set_directives" in run.loaded_tools


@pytest.mark.asyncio
async def test_spawned_agents_inherit_deferred_loading(monkeypatch):
    registry = _registry()
    captured = {}

    class FakeExecutor:
        def __init__(self, registry: ToolRegistry):
            self.registry = registry

        @property
        def tool_services(self):
            return {}

        def get_tools(self, **kwargs):
            return self.registry.get_schemas(**kwargs)

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def stream(self, messages):
            captured["messages"] = messages
            yield Result(text="done", stop_reason=StopReason.END_TURN, steps=1, usage=Usage())

    monkeypatch.setattr("ntrp.core.spawner.Agent", FakeAgent)

    parent_ctx = ToolContext(
        session_state=SessionState(session_id="parent", started_at=datetime.now(UTC)),
        registry=registry,
        run=RunContext(run_id="run", max_depth=3, deferred_tools_enabled=True),
        io=IOBridge(),
    )
    parent_ctx.spawn_fn = create_spawn_fn(
        executor=FakeExecutor(registry),
        model="test-model",
        max_depth=3,
        current_depth=0,
    )

    result = await parent_ctx.spawn_fn(
        parent_ctx,
        task="search slack",
        system_prompt="child prompt",
        tools=registry.get_schemas(),
    )

    assert result == "done"
    assert "## DEFERRED TOOLS" in captured["messages"][0]["content"]
    assert "slack_search" in captured["messages"][0]["content"]

    middleware = captured["model_request_middlewares"][0]
    prepared = await middleware(_request(registry), _identity)
    names = {t["function"]["name"] for t in prepared.tools}
    assert "load_tools" in names
    assert "echo" in names
    assert "slack_search" not in names
