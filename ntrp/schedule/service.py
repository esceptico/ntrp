import asyncio
from typing import TYPE_CHECKING

from ntrp.schedule.models import ScheduledTask
from ntrp.schedule.store import ScheduleStore

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


class ScheduleService:
    def __init__(self, store: ScheduleStore, runtime: "Runtime"):
        self.store = store
        self.runtime = runtime

    @property
    def is_running(self) -> bool:
        scheduler = self.runtime.scheduler
        return scheduler is not None and scheduler.is_running

    async def list_all(self) -> list[ScheduledTask]:
        return await self.store.list_all()

    async def get(self, task_id: str) -> ScheduledTask:
        task = await self.store.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task

    async def toggle_enabled(self, task_id: str) -> bool:
        task = await self.get(task_id)
        new_enabled = not task.enabled
        await self.store.set_enabled(task_id, new_enabled)
        return new_enabled

    async def toggle_writable(self, task_id: str) -> bool:
        task = await self.get(task_id)
        new_writable = not task.writable
        await self.store.set_writable(task_id, new_writable)
        return new_writable

    async def run_now(self, task_id: str) -> None:
        scheduler = self.runtime.scheduler
        if not scheduler:
            raise RuntimeError("Scheduler not available")
        task = await self.get(task_id)
        if task.running_since:
            raise ValueError(f"Task {task_id} is already running")
        asyncio.create_task(scheduler.run_now(task_id))

    async def update(self, task_id: str, name: str | None = None, description: str | None = None) -> ScheduledTask:
        task = await self.get(task_id)
        if name is not None:
            await self.store.update_name(task_id, name)
        if description is not None:
            await self.store.update_description(task_id, description)
        return ScheduledTask(
            task_id=task.task_id,
            name=name if name is not None else task.name,
            description=description if description is not None else task.description,
            time_of_day=task.time_of_day,
            recurrence=task.recurrence,
            enabled=task.enabled,
            created_at=task.created_at,
            next_run_at=task.next_run_at,
            last_run_at=task.last_run_at,
            notifiers=task.notifiers,
            last_result=task.last_result,
            running_since=task.running_since,
            writable=task.writable,
        )

    async def set_notifiers(self, task_id: str, notifier_names: list[str]) -> None:
        await self.get(task_id)
        notifiers = self.runtime.notifier_service.notifiers if self.runtime.notifier_service else {}
        for name in notifier_names:
            if name not in notifiers:
                raise ValueError(f"Unknown notifier: {name}")
        await self.store.set_notifiers(task_id, notifier_names)

    async def delete(self, task_id: str) -> None:
        deleted = await self.store.delete(task_id)
        if not deleted:
            raise KeyError(f"Task {task_id} not found")
