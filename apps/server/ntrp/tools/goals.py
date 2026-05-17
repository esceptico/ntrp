from pydantic import BaseModel, Field

from ntrp.events.sse import GoalUpdatedEvent
from ntrp.tools.core import EmptyInput, ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope


def _format_goal(goal: dict | None) -> str:
    if not goal:
        return "No active goal for this session."
    lines = [
        f"Goal: {goal['objective']}",
        f"Status: {goal['status']}",
    ]
    if goal.get("blocked_reason"):
        lines.append(f"Blocked: {goal['blocked_reason']}")
    evidence = goal.get("evidence") or []
    if evidence:
        lines.append("Evidence:")
        lines.extend(f"- {item.get('text', '')}" for item in evidence[-5:])
    return "\n".join(lines)


async def _emit_goal_updated(execution: ToolExecution, goal: dict) -> None:
    if execution.ctx.io.emit:
        await execution.ctx.io.emit(GoalUpdatedEvent(session_id=execution.ctx.session_id, goal=goal))


async def get_goal(execution: ToolExecution, args: EmptyInput) -> ToolResult:
    svc = execution.ctx.services.get("session")
    if not svc:
        return ToolResult(content="Session service unavailable.", preview="No session service", is_error=True)
    goal = await svc.get_goal(execution.ctx.session_id)
    return ToolResult(content=_format_goal(goal), preview=goal["status"] if goal else "No goal")


async def complete_goal(execution: ToolExecution, args: EmptyInput) -> ToolResult:
    svc = execution.ctx.services.get("session")
    if not svc:
        return ToolResult(content="Session service unavailable.", preview="No session service", is_error=True)
    goal = await svc.update_goal(execution.ctx.session_id, status="complete")
    if not goal:
        return ToolResult(content="No active goal for this session.", preview="No goal", is_error=True)
    await _emit_goal_updated(execution, goal)
    return ToolResult(
        content=(
            "Goal marked complete. Now send the user a visible concise completion report in chat. "
            "Include what changed, exact verification performed, and any remaining risks."
        ),
        preview="Goal complete",
    )


class BlockGoalInput(BaseModel):
    reason: str = Field(max_length=20_000, description="Why progress cannot continue without user/system input.")
    evidence: str | None = Field(default=None, max_length=20_000, description="Optional evidence for the blocker.")


async def block_goal(execution: ToolExecution, args: BlockGoalInput) -> ToolResult:
    svc = execution.ctx.services.get("session")
    if not svc:
        return ToolResult(content="Session service unavailable.", preview="No session service", is_error=True)
    goal = await svc.update_goal(
        execution.ctx.session_id,
        status="blocked",
        blocked_reason=args.reason,
        evidence=args.evidence,
    )
    if not goal:
        return ToolResult(content="No active goal for this session.", preview="No goal", is_error=True)
    await _emit_goal_updated(execution, goal)
    return ToolResult(content=_format_goal(goal), preview="Goal blocked")


get_goal_tool = tool(
    display_name="Get Goal",
    description="Read the durable goal for the current session.",
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL, permissions=frozenset({"session"})),
    execute=get_goal,
)

complete_goal_tool = tool(
    display_name="Complete Goal",
    description=(
        "Mark the current session goal complete after the completion audit passes. "
        "This tool takes no input. Put evidence and verification in the visible assistant report after the tool succeeds."
    ),
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL, permissions=frozenset({"session"})),
    execute=complete_goal,
)

block_goal_tool = tool(
    display_name="Block Goal",
    description=(
        "Mark the current session goal blocked when progress needs user/system input. "
        "After this tool succeeds, send the user a concise blocked report with the reason and next required input."
    ),
    input_model=BlockGoalInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL, permissions=frozenset({"session"})),
    execute=block_goal,
)
