from datetime import datetime
from typing import Any
from uuid import uuid4

from ntrp.schedule.models import Recurrence, ScheduledTask, compute_next_run
from ntrp.schedule.store import ScheduleStore
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class ScheduleTaskTool(Tool):
    name = "schedule_task"
    description = (
        "Schedule a task for the agent to run at a specific time. "
        "The task runs autonomously with full tool access. "
        "Results are stored on the task and optionally emailed."
    )
    mutates = True

    def __init__(self, store: ScheduleStore, default_email: str | None = None):
        self.store = store
        self.default_email = default_email

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What the agent should do (natural language task)",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time of day in HH:MM format (24h, local time)",
                    },
                    "recurrence": {
                        "type": "string",
                        "enum": ["once", "daily", "weekdays", "weekly"],
                        "description": "How often: once, daily, weekdays (Mon-Fri), weekly",
                    },
                    "notify_email": {
                        "type": "string",
                        "description": "Email address to send results to (optional)",
                    },
                },
                "required": ["description", "time", "recurrence"],
            },
        }

    async def execute(
        self,
        execution: ToolExecution,
        description: str = "",
        time: str = "",
        recurrence: str = "",
        notify_email: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        if not description or not time or not recurrence:
            return ToolResult("Error: description, time, and recurrence are required", "Missing fields")

        # Validate time format
        try:
            parts = time.split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
            time_normalized = f"{h:02d}:{m:02d}"
        except (ValueError, IndexError):
            return ToolResult(f"Error: invalid time format '{time}'. Use HH:MM (24h)", "Invalid time")

        # Validate recurrence
        try:
            rec = Recurrence(recurrence)
        except ValueError:
            return ToolResult(
                f"Error: invalid recurrence '{recurrence}'. Use: once, daily, weekdays, weekly",
                "Invalid recurrence",
            )

        email = notify_email or self.default_email
        now = datetime.now()
        next_run = compute_next_run(time_normalized, rec, after=now)

        task = ScheduledTask(
            task_id=uuid4().hex[:8],
            description=description,
            time_of_day=time_normalized,
            recurrence=rec,
            enabled=True,
            created_at=now,
            next_run_at=next_run,
            last_run_at=None,
            notify_email=email,
            last_result=None,
        )

        preview = f"Time: {time_normalized} ({rec.value})\nNext run: {next_run.strftime('%Y-%m-%d %H:%M')}"
        if email:
            preview += f"\nEmail: {email}"

        await execution.require_approval(description, preview=preview)
        await self.store.save(task)

        return ToolResult(
            f"Scheduled: {description}\n"
            f"ID: {task.task_id}\n"
            f"Time: {time_normalized} ({rec.value})\n"
            f"Next run: {next_run.strftime('%Y-%m-%d %H:%M')}"
            + (f"\nEmail: {email}" if email else ""),
            f"Scheduled ({task.task_id})",
        )


class ListSchedulesTool(Tool):
    name = "list_schedules"
    description = "List all scheduled tasks with their status, timing, and next run."

    def __init__(self, store: ScheduleStore):
        self.store = store

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}},
        }

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        tasks = await self.store.list_all()
        if not tasks:
            return ToolResult("No scheduled tasks.", "0 schedules")

        lines = []
        for t in tasks:
            status = "enabled" if t.enabled else "disabled"
            next_run = t.next_run_at.strftime("%Y-%m-%d %H:%M") if t.next_run_at else "—"
            last_run = t.last_run_at.strftime("%Y-%m-%d %H:%M") if t.last_run_at else "never"
            lines.append(
                f"[{t.task_id}] {t.description}\n"
                f"  {t.time_of_day} · {t.recurrence.value} · {status}\n"
                f"  next: {next_run} · last: {last_run}"
            )

        return ToolResult("\n\n".join(lines), f"{len(tasks)} schedules")


class CancelScheduleTool(Tool):
    name = "cancel_schedule"
    description = "Cancel (delete) a scheduled task by its ID. Use list_schedules to find task IDs."
    mutates = True

    def __init__(self, store: ScheduleStore):
        self.store = store

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to cancel",
                    },
                },
                "required": ["task_id"],
            },
        }

    async def execute(
        self, execution: ToolExecution, task_id: str = "", **kwargs: Any
    ) -> ToolResult:
        if not task_id:
            return ToolResult("Error: task_id is required", "Missing task_id")

        task = await self.store.get(task_id)
        if not task:
            return ToolResult(f"Error: task '{task_id}' not found", "Not found")

        await execution.require_approval(f"Cancel: {task.description}")
        await self.store.delete(task_id)

        return ToolResult(f"Cancelled: {task.description} ({task_id})", "Cancelled")


class GetScheduleResultTool(Tool):
    name = "get_schedule_result"
    description = "Get the last execution result of a scheduled task by its ID."

    def __init__(self, store: ScheduleStore):
        self.store = store

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to get results for",
                    },
                },
                "required": ["task_id"],
            },
        }

    async def execute(
        self, execution: ToolExecution, task_id: str = "", **kwargs: Any
    ) -> ToolResult:
        if not task_id:
            return ToolResult("Error: task_id is required", "Missing task_id")

        task = await self.store.get(task_id)
        if not task:
            return ToolResult(f"Error: task '{task_id}' not found", "Not found")

        if not task.last_result:
            last_run = task.last_run_at.strftime("%Y-%m-%d %H:%M") if task.last_run_at else "never"
            return ToolResult(f"No result yet for '{task.description}' (last run: {last_run})", "No result")

        header = (
            f"Task: {task.description}\n"
            f"Last run: {task.last_run_at.strftime('%Y-%m-%d %H:%M') if task.last_run_at else '—'}\n"
            f"---\n"
        )
        return ToolResult(header + task.last_result, f"Result ({task.task_id})")
