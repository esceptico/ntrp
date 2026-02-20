import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ntrp.logging import get_logger
from ntrp.operator.runner import RunRequest, run_agent
from ntrp.schedule.models import Recurrence, ScheduledTask, compute_next_run
from ntrp.schedule.store import ScheduleStore

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime

_logger = get_logger(__name__)

POLL_INTERVAL = 60


class Scheduler:
    def __init__(self, runtime: "Runtime", store: ScheduleStore):
        self.runtime = runtime
        self.store = store
        self._task: asyncio.Task | None = None
        self._running_execution: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._startup_and_loop())
        _logger.info("Scheduler started (polling every %ds)", POLL_INTERVAL)

    @property
    def is_running(self) -> bool:
        return self._task is not None

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._running_execution and not self._running_execution.done():
            try:
                await asyncio.wait_for(self._running_execution, timeout=30)
            except (TimeoutError, asyncio.CancelledError):
                self._running_execution.cancel()
            self._running_execution = None

        _logger.info("Scheduler stopped")

    async def _startup_and_loop(self) -> None:
        try:
            await self._reconcile()
        except Exception:
            _logger.exception("Scheduler reconciliation failed")
        await self._loop()

    async def _reconcile(self) -> None:
        cleared = await self.store.clear_all_running()
        if cleared:
            _logger.info("Cleared %d stale running flags", cleared)

        now = datetime.now(UTC)
        for task in await self.store.list_due(now):
            if task.recurrence == Recurrence.ONCE:
                continue  # one-shot tasks should still fire
            next_run = compute_next_run(task.time_of_day, task.recurrence, after=now)
            await self.store.update_last_run(task.task_id, task.last_run_at or now, next_run)
            _logger.info("Advanced stale task %s to %s", task.task_id, next_run)

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
            execution = asyncio.create_task(self._run_and_finalize(task))
            self._running_execution = execution
            try:
                await asyncio.shield(execution)
            except asyncio.CancelledError:
                return  # Loop cancelled, but execution continues — stop() will await it
            self._running_execution = None

    async def _run_and_finalize(self, task: ScheduledTask) -> None:
        try:
            await self._execute_task(task)
        except Exception:
            _logger.exception("Failed to execute scheduled task %s", task.task_id)
        finally:
            await self.store.clear_running(task.task_id)

    async def _run_agent(self, task: ScheduledTask) -> str | None:
        from ntrp.core.prompts import scheduled_task_suffix

        _logger.info("Executing scheduled task %s: %s", task.task_id, task.description[:80])
        request = RunRequest(
            prompt=task.description,
            prompt_suffix=scheduled_task_suffix(),
            writable=task.writable,
            notifiers=task.notifiers,
            source_id=task.task_id,
        )
        result = await run_agent(self.runtime.build_operator_deps(), request)
        return result.output

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
