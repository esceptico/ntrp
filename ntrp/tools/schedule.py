from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ntrp.schedule.models import Recurrence, ScheduledTask, compute_next_run
from ntrp.schedule.store import ScheduleStore
from ntrp.tools.core.base import ApprovalInfo, Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

SCHEDULE_TASK_DESCRIPTION = (
    "Schedule a task for the agent to run at a specific time. "
    "The task runs autonomously — read-only by default, set writable=true for memory/note writes. "
    "Results are stored on the task and optionally sent via configured notifiers."
)

LIST_SCHEDULES_DESCRIPTION = "List all scheduled tasks with their status, timing, and next run."

CANCEL_SCHEDULE_DESCRIPTION = "Cancel (delete) a scheduled task by its ID. Use list_schedules to find task IDs."

GET_SCHEDULE_RESULT_DESCRIPTION = "Get the last execution result of a scheduled task by its ID."


def _format_schedule_list(tasks: list[ScheduledTask]) -> str:
    lines = []
    for t in tasks:
        status = "enabled" if t.enabled else "disabled"
        next_run = t.next_run_at.strftime("%Y-%m-%d %H:%M") if t.next_run_at else "—"
        last_run = t.last_run_at.strftime("%Y-%m-%d %H:%M") if t.last_run_at else "never"
        label = t.name or t.description[:60]
        lines.append(
            f"[{t.task_id}] {label}\n"
            f"  {t.time_of_day} · {t.recurrence.value} · {status}\n"
            f"  next: {next_run} · last: {last_run}"
        )
    return "\n\n".join(lines)


class ScheduleTaskInput(BaseModel):
    name: str = Field(
        description="Short human-readable label for the schedule (e.g. 'morning briefing', 'inbox check')"
    )
    description: str = Field(description="What the agent should do (natural language task)")
    time: str = Field(description="Time of day in HH:MM format (24h, local time)")
    recurrence: str = Field(
        description="How often: once, daily, weekdays (Mon-Fri), weekly",
        json_schema_extra={"enum": ["once", "daily", "weekdays", "weekly"]},
    )
    notify: bool = Field(default=False, description="Send results via configured notifiers (default: false)")
    writable: bool = Field(default=False, description="Allow task to write to memory and notes (default: false)")


class ScheduleTaskTool(Tool):
    name = "schedule_task"
    display_name = "ScheduleTask"
    description = SCHEDULE_TASK_DESCRIPTION
    mutates = True
    input_model = ScheduleTaskInput

    def __init__(self, store: ScheduleStore, default_notifiers: list[str] | None = None):
        self.store = store
        self.default_notifiers = default_notifiers or []

    async def approval_info(
        self,
        name: str,
        description: str,
        time: str,
        recurrence: str,
        notify: bool = False,
        writable: bool = False,
        **kwargs: Any,
    ) -> ApprovalInfo | None:
        try:
            parts = time.split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
            time_normalized = f"{h:02d}:{m:02d}"
            rec = Recurrence(recurrence)
        except (ValueError, IndexError):
            return None

        now = datetime.now(UTC)
        next_run = compute_next_run(time_normalized, rec, after=now)

        preview = f"Time: {time_normalized} ({rec.value})\nNext run: {next_run.strftime('%Y-%m-%d %H:%M')}"
        if notify and self.default_notifiers:
            preview += f"\nNotify: {', '.join(self.default_notifiers)}"
        if writable:
            preview += "\nWritable: yes"

        return ApprovalInfo(description=description, preview=preview, diff=None)

    async def execute(
        self,
        execution: ToolExecution,
        name: str,
        description: str,
        time: str,
        recurrence: str,
        notify: bool = False,
        writable: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            parts = time.split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
            time_normalized = f"{h:02d}:{m:02d}"
        except (ValueError, IndexError):
            return ToolResult(
                content=f"Error: invalid time format '{time}'. Use HH:MM (24h)",
                preview="Invalid time",
                is_error=True,
            )

        try:
            rec = Recurrence(recurrence)
        except ValueError:
            return ToolResult(
                content=f"Error: invalid recurrence '{recurrence}'. Use: once, daily, weekdays, weekly",
                preview="Invalid recurrence",
                is_error=True,
            )

        notifiers = list(self.default_notifiers) if notify else []
        now = datetime.now(UTC)
        next_run = compute_next_run(time_normalized, rec, after=now)

        task = ScheduledTask(
            task_id=uuid4().hex[:8],
            name=name,
            description=description,
            time_of_day=time_normalized,
            recurrence=rec,
            enabled=True,
            created_at=now,
            next_run_at=next_run,
            last_run_at=None,
            notifiers=notifiers,
            last_result=None,
            running_since=None,
            writable=bool(writable),
        )

        await self.store.save(task)

        notify_line = f"\nNotify: {', '.join(notifiers)}" if notifiers else ""
        return ToolResult(
            content=f"Scheduled: {description}\n"
            f"ID: {task.task_id}\n"
            f"Time: {time_normalized} ({rec.value})\n"
            f"Next run: {next_run.strftime('%Y-%m-%d %H:%M')}" + notify_line,
            preview=f"Scheduled ({task.task_id})",
        )


class ListSchedulesTool(Tool):
    name = "list_schedules"
    display_name = "ListSchedules"
    description = LIST_SCHEDULES_DESCRIPTION
    input_model = None

    def __init__(self, store: ScheduleStore):
        self.store = store

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        tasks = await self.store.list_all()
        if not tasks:
            return ToolResult(content="No scheduled tasks.", preview="0 schedules")

        content = _format_schedule_list(tasks)
        return ToolResult(content=content, preview=f"{len(tasks)} schedules")


class CancelScheduleInput(BaseModel):
    task_id: str = Field(description="The task ID to cancel")


class CancelScheduleTool(Tool):
    name = "cancel_schedule"
    display_name = "CancelSchedule"
    description = CANCEL_SCHEDULE_DESCRIPTION
    mutates = True
    input_model = CancelScheduleInput

    def __init__(self, store: ScheduleStore):
        self.store = store

    async def approval_info(self, task_id: str, **kwargs: Any) -> ApprovalInfo | None:
        task = await self.store.get(task_id)
        if not task:
            return None
        return ApprovalInfo(description=f"Cancel: {task.description}", preview=None, diff=None)

    async def execute(self, execution: ToolExecution, task_id: str, **kwargs: Any) -> ToolResult:
        task = await self.store.get(task_id)
        if not task:
            return ToolResult(content=f"Error: task '{task_id}' not found", preview="Not found", is_error=True)

        await self.store.delete(task_id)

        return ToolResult(content=f"Cancelled: {task.description} ({task_id})", preview="Cancelled")


class GetScheduleResultInput(BaseModel):
    task_id: str = Field(description="The task ID to get results for")


class GetScheduleResultTool(Tool):
    name = "get_schedule_result"
    display_name = "ScheduleResult"
    description = GET_SCHEDULE_RESULT_DESCRIPTION
    input_model = GetScheduleResultInput

    def __init__(self, store: ScheduleStore):
        self.store = store

    async def execute(self, execution: ToolExecution, task_id: str, **kwargs: Any) -> ToolResult:
        task = await self.store.get(task_id)
        if not task:
            return ToolResult(content=f"Error: task '{task_id}' not found", preview="Not found", is_error=True)

        if not task.last_result:
            last_run = task.last_run_at.strftime("%Y-%m-%d %H:%M") if task.last_run_at else "never"
            return ToolResult(
                content=f"No result yet for '{task.description}' (last run: {last_run})",
                preview="No result",
            )

        header = (
            f"Task: {task.description}\n"
            f"Last run: {task.last_run_at.strftime('%Y-%m-%d %H:%M') if task.last_run_at else '—'}\n"
            f"---\n"
        )
        return ToolResult(content=header + task.last_result, preview=f"Result ({task.task_id})")
