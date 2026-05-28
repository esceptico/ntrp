from pydantic import BaseModel, Field

from ntrp.constants import BACKGROUND_AGENT_TIMEOUT
from ntrp.events.sse import BackgroundTaskEvent
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.skills.activation import (
    activated_skill_entries,
    append_context_block,
    format_activated_skill_context,
    record_auto_activated_skill_events,
)
from ntrp.tools.core import EmptyInput, ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope

BACKGROUND_SYSTEM_PROMPT = (
    "You are a background agent. Complete the given task using available read-only tools, "
    "then return a concise, self-contained report. Be thorough but focused. "
    "Include any relevant source names, IDs, links, or evidence directly in your final report. "
    "Do not refer to separate files, hidden messages, or context outside your final report. "
    "You are read-only — report what you find, the caller decides what to do with it."
)

BACKGROUND_DESCRIPTION = (
    "Spawn a background agent that runs independently and delivers results automatically when done. "
    "The agent has read-only tool access (search, read, web, memory, bash). "
    "Use for long-running tasks: deep research, multi-source investigation, data gathering. "
    "When it finishes, the result is delivered back into the parent conversation as a hidden meta message. "
    "Do not inspect the filesystem for background results. "
    "Use cancel_background_task to stop, list_background_tasks to check currently running tasks, "
    "and get_background_result only when the user explicitly asks to retrieve a result by task ID."
)


class BackgroundInput(BaseModel):
    task: str = Field(description="What the background agent should do.")


async def _build_background_system_prompt(ctx, task: str, tool_id: str) -> str:
    memory_retrieval = ctx.services.get("memory_retrieval")
    if memory_retrieval is None:
        return BACKGROUND_SYSTEM_PROMPT

    bundle = await memory_retrieval.search(
        MemoryActivationRequest(
            query=task,
            task="background_prompt",
            task_id=tool_id,
            session_id=ctx.session_id,
            run_id=ctx.run.run_id,
            surface="prompt",
            budget_chars=1_500,
            limit=8,
            record_access=True,
        )
    )
    skill_registry = ctx.services.get("skill_registry")
    selected_skill_entries = activated_skill_entries(bundle, skill_registry)
    memory_context = append_context_block(
        bundle.prompt_context,
        format_activated_skill_context(selected_skill_entries),
    )
    await record_auto_activated_skill_events(
        ctx.services.get("memory"),
        bundle,
        skill_registry,
        task="background_prompt_auto_skill_activation",
        activation_surface="background_prompt",
        task_id=tool_id,
        session_id=ctx.session_id,
        run_id=ctx.run.run_id,
        entries=selected_skill_entries,
    )
    return append_context_block(BACKGROUND_SYSTEM_PROMPT, memory_context) or BACKGROUND_SYSTEM_PROMPT


async def background(execution: ToolExecution, args: BackgroundInput) -> ToolResult:
    ctx = execution.ctx

    if not ctx.spawn_fn:
        return ToolResult(content="Error: spawn capability not available", preview="Error", is_error=True)

    tools = ctx.registry.get_schemas(read_only=True, capabilities=ctx.capabilities)

    system_prompt = await _build_background_system_prompt(ctx, args.task, execution.tool_id)

    spawn = await ctx.spawn_fn(
        ctx,
        task=args.task,
        system_prompt=system_prompt,
        tools=tools,
        timeout=BACKGROUND_AGENT_TIMEOUT,
        parent_id=execution.tool_id,
        background=True,
        kind="background",
    )

    return ToolResult(content=spawn.text, preview=spawn.text[:80])


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
    content = await execution.ctx.background_tasks.read_background_result(args.task_id)
    if content is None:
        return ToolResult(
            content=(
                f"No stored result for task {args.task_id}. "
                "If it is still running, wait for the hidden completion notification; do not search files."
            ),
            preview="Not found",
            is_error=True,
        )
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
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=background,
)

cancel_background_task_tool = tool(
    display_name="Cancel Background Task",
    description="Cancel a running background task by its ID.",
    input_model=CancelBackgroundTaskInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL, requires_approval=True),
    execute=cancel_background_task,
)

get_background_result_tool = tool(
    display_name="Get Background Result",
    description="Read the result of a completed background task by its ID.",
    input_model=GetBackgroundResultInput,
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=get_background_result,
)

list_background_tasks_tool = tool(
    display_name="List Background Tasks",
    description=(
        "List currently running background tasks only. Finished task results are delivered automatically "
        "as hidden parent-conversation notifications — do not poll or inspect files for results."
    ),
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=list_background_tasks,
)
