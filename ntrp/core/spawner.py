import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from ntrp.agent import Agent, Result, Role, ToolCompleted, ToolStarted
from ntrp.constants import SUBAGENT_DEFAULT_TIMEOUT
from ntrp.context.models import SessionState
from ntrp.core.isolation import IsolationLevel
from ntrp.core.llm_client import llm_client
from ntrp.core.tool_executor import NtrpToolExecutor
from ntrp.events.sse import BackgroundTaskEvent, agent_event_to_sse
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

        if background or silent:
            bg_io = IOBridge()
        else:
            bg_io = calling_ctx.io

        child_ctx = ToolContext(
            session_state=child_state,
            registry=executor.registry,
            run=child_run,
            io=bg_io,
            services=calling_ctx.services,
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

        sub_agent = Agent(
            tools=filtered_tools,
            client=llm_client,
            executor=child_executor,
            model=child_model,
            max_depth=max_depth,
            current_depth=current_depth + 1,
            parent_id=parent_id,
        )

        child_messages = [
            {"role": Role.SYSTEM, "content": system_prompt},
            {"role": Role.USER, "content": task},
        ]

        parent_emit = calling_ctx.io.emit if not silent else None

        async def _stream_to(to_event) -> str:
            text = ""
            async for event in sub_agent.stream(child_messages):
                if isinstance(event, Result):
                    text = event.text
                elif parent_emit and (out := to_event(event)):
                    await parent_emit(out)
            return text

        if not background:
            try:
                return await asyncio.wait_for(_stream_to(agent_event_to_sse), timeout=timeout)
            except TimeoutError:
                return f"Error: Sub-agent timed out after {timeout}s"

        registry = calling_ctx.background_tasks
        task_id = registry.generate_id()
        label = task[:80]

        def _to_bg_event(event):
            if isinstance(event, ToolStarted):
                detail = event.display_name or event.name
            elif isinstance(event, ToolCompleted):
                detail = f"{event.display_name or event.name}: {event.preview}"
            else:
                return None
            return BackgroundTaskEvent(task_id=task_id, command=label, status="activity", detail=detail)

        async def _run_background():
            try:
                result = await asyncio.wait_for(_stream_to(_to_bg_event), timeout=timeout)
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
                    emit=parent_emit,
                )
            except Exception:
                _logger.exception("Background task %s delivery failed", task_id)

        bg_task = asyncio.create_task(_run_background())
        registry.register(task_id, bg_task, command=label)

        if calling_ctx.io.emit:
            await calling_ctx.io.emit(BackgroundTaskEvent(task_id=task_id, command=label, status="started"))

        return f"Background task {task_id} started: {task}"

    return spawn_child
