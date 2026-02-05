import asyncio
from collections.abc import Callable

from ntrp.constants import SUBAGENT_DEFAULT_ITERATIONS, SUBAGENT_DEFAULT_TIMEOUT
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
        max_iterations: int = SUBAGENT_DEFAULT_ITERATIONS,
        timeout: int = SUBAGENT_DEFAULT_TIMEOUT,
        model_override: str | None = None,
        parent_id: str | None = None,
    ) -> str:
        from ntrp.core.agent import Agent

        filtered_tools = tools or executor.registry.get_schemas()

        child_ctx = ToolContext(
            session_state=calling_ctx.session_state,
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
                sub_agent.run(task, max_iterations=max_iterations),
                timeout=timeout,
            )
        except TimeoutError:
            return f"Error: Sub-agent timed out after {timeout}s"

    return spawn_child
