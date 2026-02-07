import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from ntrp.constants import SUBAGENT_DEFAULT_TIMEOUT
from ntrp.context.models import SessionState
from ntrp.core.isolation import IsolationLevel
from ntrp.tools.core.context import ToolContext
from ntrp.tools.executor import ToolExecutor


def _create_session_state(calling_ctx: ToolContext, isolation: IsolationLevel) -> SessionState:
    if isolation == IsolationLevel.SHARED:
        return calling_ctx.session_state

    child_session_id = f"{calling_ctx.session_id}::{uuid4().hex[:8]}"
    return SessionState(
        session_id=child_session_id,
        started_at=datetime.now(UTC),
        auto_approve=calling_ctx.session_state.auto_approve,
        skip_approvals=calling_ctx.session_state.skip_approvals,
    )


def create_spawn_fn(
    executor: ToolExecutor,
    model: str,
    max_depth: int,
    current_depth: int,
    cancel_check: Callable[[], bool] | None,
):
    async def spawn_child(
        calling_ctx: ToolContext,
        task: str,
        *,
        system_prompt: str,
        tools: list[dict] | None = None,
        timeout: int = SUBAGENT_DEFAULT_TIMEOUT,
        model_override: str | None = None,
        parent_id: str | None = None,
        isolation: IsolationLevel = IsolationLevel.FULL,
    ) -> str:
        from ntrp.core.agent import Agent

        filtered_tools = tools or executor.registry.get_schemas()
        child_state = _create_session_state(calling_ctx, isolation)

        child_ctx = ToolContext(
            session_state=child_state,
            registry=executor.registry,
            memory=executor.memory,
            emit=calling_ctx.emit,
            approval_queue=calling_ctx.approval_queue,
            extra_auto_approve=calling_ctx.extra_auto_approve,
        )
        child_ctx.spawn_fn = create_spawn_fn(
            executor=executor,
            model=model_override or model,
            max_depth=max_depth,
            current_depth=current_depth + 1,
            cancel_check=cancel_check,
        )

        sub_agent = Agent(
            tools=filtered_tools,
            tool_executor=executor,
            model=model_override or model,
            system_prompt=system_prompt,
            ctx=child_ctx,
            max_depth=max_depth,
            current_depth=current_depth + 1,
            parent_id=parent_id,
            cancel_check=cancel_check,
        )

        try:
            return await asyncio.wait_for(
                sub_agent.run(task),
                timeout=timeout,
            )
        except TimeoutError:
            return f"Error: Sub-agent timed out after {timeout}s"

    return spawn_child
