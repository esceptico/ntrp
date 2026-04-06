import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from ntrp.agent import Agent, AgentHooks, Role
from ntrp.constants import SUBAGENT_DEFAULT_TIMEOUT
from ntrp.context.models import SessionState
from ntrp.core.agent_callbacks import NtrpAgentCallbacks
from ntrp.core.isolation import IsolationLevel
from ntrp.core.llm_client import llm_client
from ntrp.core.tool_executor import NtrpToolExecutor
from ntrp.events.sse import BackgroundTaskEvent, ToolCallEvent, ToolResultEvent
from ntrp.logging import get_logger
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)


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
        silent: bool = False,
        background: bool = False,
    ) -> str:
        filtered_tools = tools or executor.get_tools()
        child_state = _create_session_state(calling_ctx, isolation)
        child_model = model_override or model

        child_run = RunContext(
            run_id=calling_ctx.run.run_id,
            current_depth=current_depth + 1,
            max_depth=max_depth,
            extra_auto_approve=calling_ctx.run.extra_auto_approve,
            research_model=calling_ctx.run.research_model,
        )

        if background:
            registry = calling_ctx.background_tasks
            task_id = registry.generate_id()
            label = task[:80]

        if background and calling_ctx.io.emit:
            parent_emit = calling_ctx.io.emit

            async def _bg_emit(event):
                if isinstance(event, ToolCallEvent):
                    await parent_emit(
                        BackgroundTaskEvent(
                            task_id=task_id,
                            command=label,
                            status="activity",
                            detail=event.display_name or event.name,
                        )
                    )
                elif isinstance(event, ToolResultEvent):
                    await parent_emit(
                        BackgroundTaskEvent(
                            task_id=task_id,
                            command=label,
                            status="activity",
                            detail=f"{event.display_name or event.name}: {event.preview}",
                        )
                    )

            bg_io = IOBridge(emit=_bg_emit)
        elif silent or background:
            bg_io = IOBridge()
        else:
            bg_io = calling_ctx.io

        child_ctx = ToolContext(
            session_state=child_state,
            registry=executor.registry,
            run=child_run,
            io=bg_io,
            services=calling_ctx.services,
            channel=calling_ctx.channel,
            ledger=calling_ctx.ledger,
            background_tasks=calling_ctx.background_tasks,
        )
        child_ctx.spawn_fn = create_spawn_fn(
            executor=executor,
            model=child_model,
            max_depth=max_depth,
            current_depth=current_depth + 1,
        )

        child_executor = NtrpToolExecutor(executor, child_ctx, ledger=calling_ctx.ledger)

        child_callbacks = NtrpAgentCallbacks(
            channel=calling_ctx.channel,
            session_id=child_state.session_id,
            model=child_model,
            is_root=False,
        )

        sub_agent = Agent(
            tools=filtered_tools,
            client=llm_client,
            executor=child_executor,
            model=child_model,
            max_depth=max_depth,
            current_depth=current_depth + 1,
            hooks=AgentHooks(on_response=child_callbacks.on_response),
        )

        child_messages = [
            {"role": Role.SYSTEM, "content": system_prompt},
            {"role": Role.USER, "content": task},
        ]

        if not background:
            try:
                run_result = await asyncio.wait_for(sub_agent.run(child_messages), timeout=timeout)
                return run_result.text
            except TimeoutError:
                return f"Error: Sub-agent timed out after {timeout}s"

        captured_emit = calling_ctx.io.emit

        async def _run_background():
            try:
                run_result = await asyncio.wait_for(sub_agent.run(child_messages), timeout=timeout)
                result = run_result.text
                status = "completed"
            except asyncio.CancelledError:
                return
            except TimeoutError:
                result = f"Error: Background agent timed out after {timeout}s"
                status = "failed"
            except Exception as e:
                result = f"Error: {e}"
                status = "failed"
                _logger.warning("Background task %s failed: %s", task_id, e)
            try:
                await registry.deliver_result(
                    task_id=task_id,
                    result=result,
                    label=label,
                    status=status,
                    emit=captured_emit,
                )
            except Exception:
                _logger.exception("Background task %s delivery failed", task_id)

        bg_task = asyncio.create_task(_run_background())
        registry.register(task_id, bg_task, command=label)

        if calling_ctx.io.emit:
            await calling_ctx.io.emit(BackgroundTaskEvent(task_id=task_id, command=label, status="started"))

        return f"Background task {task_id} started: {task}"

    return spawn_child
