from pathlib import Path

from pydantic import BaseModel, Field

from ntrp.constants import BACKGROUND_AGENT_TIMEOUT, NTRP_TMP_BASE
from ntrp.events.sse import BackgroundTaskEvent
from ntrp.tools.core import EmptyInput, ToolResult, tool
from ntrp.tools.core.context import ToolExecution

BACKGROUND_SYSTEM_PROMPT = (
    "You are a background agent. Complete the given task using available read-only tools, "
    "then return a concise summary of the result. Be thorough but focused. "
    "You are read-only — report what you find, the caller decides what to do with it."
)

BACKGROUND_DESCRIPTION = (
    "Spawn a background agent that runs independently and delivers results automatically when done. "
    "The agent has read-only tool access (search, read, web, memory, bash). "
    "Use for long-running tasks: deep research, multi-source investigation, data gathering. "
    "Use cancel_background_task to stop, list_background_tasks to check status, "
    "get_background_result to read full output."
)


class BackgroundInput(BaseModel):
    task: str = Field(description="What the background agent should do.")


async def background(execution: ToolExecution, args: BackgroundInput) -> ToolResult:
    ctx = execution.ctx

    if not ctx.spawn_fn:
        return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

    tools = ctx.registry.get_schemas(mutates=False, capabilities=ctx.capabilities)

    result = await ctx.spawn_fn(
        ctx,
        task=args.task,
        system_prompt=BACKGROUND_SYSTEM_PROMPT,
        tools=tools,
        timeout=BACKGROUND_AGENT_TIMEOUT,
        parent_id=execution.tool_id,
        background=True,
    )

    return ToolResult(content=result, preview=result[:80])


class CancelBackgroundTaskInput(BaseModel):
    task_id: str = Field(description="The ID of the background task to cancel")


async def cancel_background_task(execution: ToolExecution, args: CancelBackgroundTaskInput) -> ToolResult:
    registry = execution.ctx.background_tasks
    if (command := registry.cancel(args.task_id)) is None:
        return ToolResult(content=f"No running task with ID {args.task_id}", preview="Not found", is_error=True)

    if emit := execution.ctx.io.emit:
        await emit(BackgroundTaskEvent(task_id=args.task_id, command=command, status="cancelled"))

    return ToolResult(content=f"Cancelled task {args.task_id}: {command}", preview=f"Cancelled · {args.task_id}")


class GetBackgroundResultInput(BaseModel):
    task_id: str = Field(description="The ID of the background task")


async def get_background_result(execution: ToolExecution, args: GetBackgroundResultInput) -> ToolResult:
    session_id = execution.ctx.background_tasks.session_id or execution.ctx.session_id
    path = Path(NTRP_TMP_BASE) / session_id / "bg_results" / f"{args.task_id}.txt"
    if not path.exists():
        return ToolResult(
            content=f"No result for task {args.task_id} — use list_background_tasks to check if it's still running.",
            preview="Not found",
            is_error=True,
        )
    content = path.read_text(encoding="utf-8")
    lines = content.count("\n") + 1
    return ToolResult(content=content, preview=f"{lines} lines")


async def list_background_tasks(execution: ToolExecution, args: EmptyInput) -> ToolResult:
    pending = execution.ctx.background_tasks.list_pending()
    if not pending:
        return ToolResult(content="No background tasks running.", preview="0 tasks")

    lines = [f"- {tid}: {cmd}" for tid, cmd in pending]
    content = (
        f"{len(pending)} running:\n" + "\n".join(lines) + "\n\nResults are delivered automatically — do not poll. "
        "Continue with other work or respond to the user."
    )
    return ToolResult(content=content, preview=f"{len(pending)} tasks")


background_tool = tool(
    display_name="Background",
    description=BACKGROUND_DESCRIPTION,
    input_model=BackgroundInput,
    execute=background,
)

cancel_background_task_tool = tool(
    display_name="Cancel Background Task",
    description="Cancel a running background task by its ID.",
    input_model=CancelBackgroundTaskInput,
    mutates=True,
    execute=cancel_background_task,
)

get_background_result_tool = tool(
    display_name="Get Background Result",
    description="Read the result of a completed background task by its ID.",
    input_model=GetBackgroundResultInput,
    execute=get_background_result,
)

list_background_tasks_tool = tool(
    display_name="List Background Tasks",
    description=(
        "List all running background tasks. "
        "Results are delivered automatically when tasks finish — do NOT poll this tool in a loop."
    ),
    volatile=True,
    execute=list_background_tasks,
)
