import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from ntrp.constants import SUBAGENT_DEFAULT_TIMEOUT
from ntrp.context.models import SessionState
from ntrp.core.isolation import IsolationLevel
from ntrp.tools.core.context import ToolContext
from ntrp.tools.executor import ToolExecutor


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

        # Create isolated or shared session state
        if isolation == IsolationLevel.FULL:
            # Full isolation: new session state, don't inherit gathered_context or rolling_summary
            child_state = SessionState(
                session_id=f"{calling_ctx.session_id}::{uuid4().hex[:8]}",
                user_id=calling_ctx.session_state.user_id,
                started_at=datetime.now(),
                auto_approve=calling_ctx.session_state.auto_approve,
                yolo=calling_ctx.session_state.yolo,
            )
        else:
            # Shared: use parent's session state (original behavior)
            child_state = calling_ctx.session_state

        child_ctx = ToolContext(
            session_state=child_state,
            executor=executor,
            emit=calling_ctx.emit,
            approval_queue=calling_ctx.approval_queue,
            extra_auto_approve=calling_ctx.extra_auto_approve,
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
