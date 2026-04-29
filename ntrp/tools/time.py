from datetime import datetime

from ntrp.tools.core import EmptyInput, ToolResult, tool
from ntrp.tools.core.context import ToolExecution


async def current_time(execution: ToolExecution, args: EmptyInput) -> ToolResult:
    now = datetime.now()
    formatted = now.strftime("%A, %B %d, %Y at %H:%M")
    return ToolResult(content=formatted, preview=formatted)


current_time_tool = tool(
    display_name="Current Time",
    description="Get the current date and time.",
    execute=current_time,
)
