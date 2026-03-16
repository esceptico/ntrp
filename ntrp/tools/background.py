from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ntrp.constants import NTRP_TMP_BASE
from ntrp.events.sse import BackgroundTaskEvent
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class CancelBackgroundTaskInput(BaseModel):
    task_id: str = Field(description="The ID of the background task to cancel")


class CancelBackgroundTaskTool(Tool):
    name = "cancel_background_task"
    display_name = "Cancel Background Task"
    description = "Cancel a running background task by its ID."
    input_model = CancelBackgroundTaskInput
    mutates = True

    async def execute(self, execution: ToolExecution, task_id: str, **kwargs: Any) -> ToolResult:
        registry = execution.ctx.background_tasks
        if (command := registry.cancel(task_id)) is None:
            return ToolResult(content=f"No running task with ID {task_id}", preview="Not found", is_error=True)

        if emit := execution.ctx.io.emit:
            await emit(BackgroundTaskEvent(task_id=task_id, command=command, status="cancelled"))

        return ToolResult(content=f"Cancelled task {task_id}: {command}", preview=f"Cancelled · {task_id}")


class GetBackgroundResultInput(BaseModel):
    task_id: str = Field(description="The ID of the background task")


class GetBackgroundResultTool(Tool):
    name = "get_background_result"
    display_name = "Get Background Result"
    description = "Read the result of a completed background task by its ID."
    input_model = GetBackgroundResultInput

    async def execute(self, execution: ToolExecution, task_id: str, **kwargs: Any) -> ToolResult:
        session_id = execution.ctx.background_tasks.session_id or execution.ctx.session_id
        path = Path(NTRP_TMP_BASE) / session_id / "bg_results" / f"{task_id}.txt"
        if not path.exists():
            return ToolResult(
                content=f"No result file for task {task_id}. Results are also delivered inline — check the preceding messages.",
                preview="Not found",
                is_error=True,
            )
        content = path.read_text(encoding="utf-8")
        lines = content.count("\n") + 1
        return ToolResult(content=content, preview=f"{lines} lines")


class ListBackgroundTasksTool(Tool):
    name = "list_background_tasks"
    display_name = "List Background Tasks"
    description = (
        "List all running background tasks. "
        "Results are delivered automatically when tasks finish — do NOT poll this tool in a loop."
    )
    volatile = True

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        pending = execution.ctx.background_tasks.list_pending()
        if not pending:
            return ToolResult(content="No background tasks running.", preview="0 tasks")

        lines = [f"- {tid}: {cmd}" for tid, cmd in pending]
        content = (
            f"{len(pending)} running:\n" + "\n".join(lines) + "\n\nResults are delivered automatically — do not poll. "
            "Continue with other work or respond to the user."
        )
        return ToolResult(content=content, preview=f"{len(pending)} tasks")
