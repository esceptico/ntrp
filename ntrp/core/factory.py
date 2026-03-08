from dataclasses import dataclass

from ntrp.channel import Channel
from ntrp.context.models import SessionState
from ntrp.core.agent import Agent
from ntrp.core.ledger import ExplorationLedger
from ntrp.core.spawner import create_spawn_fn
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext
from ntrp.tools.executor import ToolExecutor


@dataclass(frozen=True)
class AgentConfig:
    model: str
    explore_model: str | None
    max_depth: int
    compression_threshold: float = 0.8
    max_messages: int = 120
    compression_keep_ratio: float = 0.2
    summary_max_tokens: int = 1500


def create_agent(
    *,
    executor: ToolExecutor,
    config: AgentConfig,
    tools: list[dict],
    system_prompt: str | list[dict],
    session_state: SessionState,
    channel: Channel,
    run_id: str,
    io: IOBridge | None = None,
    extra_auto_approve: set[str] | None = None,
) -> Agent:
    run_ctx = RunContext(
        run_id=run_id,
        max_depth=config.max_depth,
        extra_auto_approve=extra_auto_approve or set(),
        explore_model=config.explore_model,
    )

    tool_ctx = ToolContext(
        session_state=session_state,
        registry=executor.registry,
        run=run_ctx,
        io=io or IOBridge(),
        services=executor.runtime.tool_services,
        channel=channel,
        ledger=ExplorationLedger(),
    )
    tool_ctx.spawn_fn = create_spawn_fn(
        executor=executor,
        model=config.model,
        max_depth=config.max_depth,
        current_depth=0,
    )

    return Agent(
        tools=tools,
        tool_executor=executor,
        model=config.model,
        system_prompt=system_prompt,
        ctx=tool_ctx,
        max_depth=config.max_depth,
        current_depth=0,
        compression_threshold=config.compression_threshold,
        max_messages=config.max_messages,
        compression_keep_ratio=config.compression_keep_ratio,
        summary_max_tokens=config.summary_max_tokens,
    )
