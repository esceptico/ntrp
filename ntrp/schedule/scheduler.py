import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ntrp.schedule.models import Recurrence, ScheduledTask, compute_next_run
from ntrp.schedule.store import ScheduleStore

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime

from ntrp.logging import get_logger

_logger = get_logger(__name__)

POLL_INTERVAL = 60


class Scheduler:
    def __init__(self, runtime: "Runtime", store: ScheduleStore):
        self.runtime = runtime
        self.store = store
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            _logger.info("Scheduler started (polling every %ds)", POLL_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            _logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("Scheduler tick failed")
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        due_tasks = await self.store.list_due(now)
        for task in due_tasks:
            await self.store.mark_running(task.task_id, now)
            try:
                await self._execute_task(task)
            except Exception:
                _logger.exception("Failed to execute scheduled task %s", task.task_id)
            finally:
                await self.store.clear_running(task.task_id)

    async def _run_agent(self, task: ScheduledTask) -> str | None:
        runtime = self.runtime
        _logger.info("Executing scheduled task %s: %s", task.task_id, task.description[:80])

        memory_context = None
        if runtime.memory:
            from ntrp.memory.formatting import format_memory_context

            user_facts, recent_facts = await runtime.memory.get_context()
            memory_context = format_memory_context(user_facts, recent_facts) or None

        from ntrp.core.prompts import build_system_prompt

        system_prompt = build_system_prompt(
            source_details=runtime.get_source_details(),
            memory_context=memory_context,
        )
        system_prompt += (
            "\n\nYou are executing a scheduled task autonomously. "
            "Do the work described directly — gather information, produce output, and return the result. "
            "Do not schedule new tasks or ask for confirmation. "
            "Return only the final output — no preamble, no narration, no thinking out loud."
        )

        session_state = runtime.create_session()

        from ntrp.core.spawner import create_spawn_fn
        from ntrp.tools.core.context import ToolContext

        tool_ctx = ToolContext(
            session_state=session_state,
            registry=runtime.executor.registry,
            memory=runtime.memory,
        )
        tool_ctx.spawn_fn = create_spawn_fn(
            executor=runtime.executor,
            model=runtime.config.chat_model,
            max_depth=runtime.max_depth,
            current_depth=0,
            cancel_check=None,
        )

        from ntrp.core.agent import Agent

        tools = runtime.executor.get_tools() if task.writable else runtime.executor.get_tools(mutates=False)
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

        if task.notify_email and runtime.gmail:
            accounts = runtime.gmail.list_accounts()
            if accounts:
                subject = f"[ntrp] {task.description}"
                body = result or "(no output)"
                try:
                    await asyncio.to_thread(
                        runtime.gmail.send_email,
                        account=accounts[0],
                        to=task.notify_email,
                        subject=subject,
                        body=body,
                        html=True,
                    )
                except Exception:
                    _logger.exception("Failed to send email for task %s", task.task_id)

        return result

    async def _execute_task(self, task: ScheduledTask) -> None:
        result = await self._run_agent(task)
        now = datetime.now(UTC)
        if task.recurrence == Recurrence.ONCE:
            await self.store.update_last_run(task.task_id, now, now, result=result)
            await self.store.set_enabled(task.task_id, False)
        else:
            next_run = compute_next_run(task.time_of_day, task.recurrence, after=now)
            await self.store.update_last_run(task.task_id, now, next_run, result=result)
        _logger.info("Completed scheduled task %s", task.task_id)

    async def run_now(self, task_id: str) -> str | None:
        task = await self.store.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.running_since:
            raise ValueError(f"Task {task_id} is already running")

        await self.store.mark_running(task.task_id, datetime.now(UTC))
        try:
            result = await self._run_agent(task)
            now = datetime.now(UTC)
            if task.recurrence == Recurrence.ONCE:
                await self.store.update_last_run(task.task_id, now, task.next_run_at, result=result)
            else:
                next_run = compute_next_run(task.time_of_day, task.recurrence, after=now)
                await self.store.update_last_run(task.task_id, now, next_run, result=result)
            return result
        finally:
            await self.store.clear_running(task.task_id)
