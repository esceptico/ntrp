import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ntrp.schedule.models import Recurrence, ScheduledTask, compute_next_run
from ntrp.schedule.store import ScheduleStore

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60


class Scheduler:
    def __init__(self, runtime: "Runtime", store: ScheduleStore):
        self.runtime = runtime
        self.store = store
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduler started (polling every %ds)", POLL_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self) -> None:
        now = datetime.now()
        due_tasks = await self.store.list_due(now)
        for task in due_tasks:
            await self.store.mark_running(task.task_id, now)
            try:
                await self._execute_task(task)
            except Exception:
                logger.exception("Failed to execute scheduled task %s", task.task_id)
            finally:
                await self.store.clear_running(task.task_id)

    async def _execute_task(self, task: ScheduledTask) -> None:
        runtime = self.runtime
        logger.info("Executing scheduled task %s: %s", task.task_id, task.description[:80])

        # Build system prompt with memory context
        memory_context = None
        if runtime.memory:
            from ntrp.memory.formatting import format_memory_context

            user_facts, recent_facts = await runtime.memory.get_context()
            memory_context = format_memory_context(user_facts, recent_facts) or None

        from ntrp.server.prompts import build_system_prompt

        system_prompt = build_system_prompt(
            source_details=runtime.get_source_details(),
            memory_context=memory_context,
        )

        session_state = runtime.create_session()

        from ntrp.tools.core.context import ToolContext

        tool_ctx = ToolContext(
            session_state=session_state,
            executor=runtime.executor,
        )

        # Read-only tools only — scheduled tasks gather and summarize,
        # email notification is handled below outside the agent.
        # TODO: per-task tool access control
        from ntrp.core.agent import Agent

        tools = runtime.executor.get_tools(mutates=False)
        agent = Agent(
            tools=tools,
            tool_executor=runtime.executor,
            model=runtime.config.chat_model,
            system_prompt=system_prompt,
            ctx=tool_ctx,
            max_depth=runtime.max_depth,
            current_depth=0,
        )

        result = await agent.run(task.description)

        # Send email if configured
        if task.notify_email and runtime.gmail:
            accounts = runtime.gmail.list_accounts()
            if accounts:
                subject = f"[ntrp] {task.description}"
                body = result or "(no output)"
                runtime.gmail.send_email(
                    account=accounts[0],
                    to=task.notify_email,
                    subject=subject,
                    body=body,
                )

        # Store result and update timing
        now = datetime.now()
        if task.recurrence == Recurrence.ONCE:
            await self.store.update_last_run(task.task_id, now, now, result=result)
            await self.store.set_enabled(task.task_id, False)
        else:
            next_run = compute_next_run(task.time_of_day, task.recurrence, after=now)
            await self.store.update_last_run(task.task_id, now, next_run, result=result)

        logger.info("Completed scheduled task %s", task.task_id)
