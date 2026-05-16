from datetime import datetime

from ntrp.tools.core import EmptyInput, ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ToolAction, ToolPolicy, ToolScope


async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
    now = datetime.now()
    formatted = now.strftime("%A, %B %d, %Y at %H:%M")
    return ToolResult(content=formatted, preview=formatted)


current_time_tool = tool(
    display_name="Current Time",
    description="Get the current date and time.",
    policy=ToolPolicy(action=ToolAction.READ, scope=ToolScope.INTERNAL),
    execute=current_time,
)
