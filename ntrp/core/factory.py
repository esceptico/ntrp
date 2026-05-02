from dataclasses import dataclass
from typing import Self

from ntrp.agent import Agent, AgentHooks
from ntrp.agent.ledger import SharedLedger
from ntrp.context.models import SessionState
from ntrp.core.compaction_model_request_middleware import CompactionModelRequestMiddleware
from ntrp.core.compactor import Compactor, SummaryCompactor
from ntrp.core.llm_client import llm_client
from ntrp.core.spawner import create_spawn_fn
from ntrp.core.tool_executor import NtrpToolExecutor
from ntrp.tools.core.context import BackgroundTaskRegistry, IOBridge, RunContext, ToolContext
from ntrp.tools.executor import ToolExecutor


@dataclass(frozen=True)
class AgentConfig:
    model: str
    research_model: str | None
    max_depth: int
    reasoning_effort: str | None = None
    compactor: Compactor | None = None

    @classmethod
    def from_config(cls, config, *, model: str | None = None) -> Self:
        return cls(
            model=model or config.chat_model,
            research_model=config.research_model,
            max_depth=config.max_depth,
            reasoning_effort=config.reasoning_effort,
            compactor=SummaryCompactor(
                threshold=config.compression_threshold,
                max_messages=config.max_messages,
                keep_ratio=config.compression_keep_ratio,
                summary_max_tokens=config.summary_max_tokens,
            ),
        )


def create_agent(
    *,
    executor: ToolExecutor,
    config: AgentConfig,
    tools: list[dict],
    session_state: SessionState,
    run_id: str,
    io: IOBridge | None = None,
    extra_auto_approve: set[str] | None = None,
    background_tasks: BackgroundTaskRegistry | None = None,
) -> Agent:
    run_ctx = RunContext(
        run_id=run_id,
        max_depth=config.max_depth,
        extra_auto_approve=extra_auto_approve or set(),
        research_model=config.research_model,
    )

    bg_tasks = background_tasks or BackgroundTaskRegistry(session_id=session_state.session_id)

    tool_ctx = ToolContext(
        session_state=session_state,
        registry=executor.registry,
        run=run_ctx,
        io=io or IOBridge(),
        services=executor.tool_services,
        ledger=SharedLedger(),
        background_tasks=bg_tasks,
    )
    tool_ctx.spawn_fn = create_spawn_fn(
        executor=executor,
        model=config.model,
        max_depth=config.max_depth,
        current_depth=0,
        reasoning_effort=config.reasoning_effort,
    )

    ntrp_executor = NtrpToolExecutor(executor, tool_ctx, ledger=tool_ctx.ledger)

    return Agent(
        tools=tools,
        client=llm_client,
        executor=ntrp_executor,
        model=config.model,
        max_depth=config.max_depth,
        reasoning_effort=config.reasoning_effort,
        prompt_cache_key=session_state.session_id,
        hooks=AgentHooks(),
        model_request_middlewares=(CompactionModelRequestMiddleware(compactor=config.compactor),),
    )
