from collections.abc import Callable

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.core.agent import Agent
from ntrp.core.spawner import create_spawn_fn
from ntrp.memory.facts import FactMemory
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext
from ntrp.tools.executor import ToolExecutor


def create_agent(
    *,
    executor: ToolExecutor,
    model: str,
    tools: list[dict],
    system_prompt: str | list[dict],
    session_state: SessionState,
    memory: FactMemory | None,
    channel: Channel,
    max_depth: int,
    explore_model: str | None,
    run_id: str,
    cancel_check: Callable[[], bool] | None = None,
    io: IOBridge | None = None,
    extra_auto_approve: set[str] | None = None,
) -> Agent:
    run_ctx = RunContext(
        run_id=run_id,
        max_depth=max_depth,
        extra_auto_approve=extra_auto_approve or set(),
        explore_model=explore_model,
    )

    tool_ctx = ToolContext(
        session_state=session_state,
        registry=executor.registry,
        run=run_ctx,
        io=io or IOBridge(),
        memory=memory,
        sources=executor.runtime.source_mgr.sources,
        channel=channel,
    )
    tool_ctx.spawn_fn = create_spawn_fn(
        executor=executor,
        model=model,
        max_depth=max_depth,
        current_depth=0,
        cancel_check=cancel_check,
    )

    return Agent(
        tools=tools,
        tool_executor=executor,
        model=model,
        system_prompt=system_prompt,
        ctx=tool_ctx,
        max_depth=max_depth,
        current_depth=0,
        cancel_check=cancel_check,
    )
