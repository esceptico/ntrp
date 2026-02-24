from datetime import datetime

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class CurrentTimeTool(Tool):
    name = "current_time"
    display_name = "Current Time"
    description = "Get the current date and time."

    async def execute(self, execution: ToolExecution, **kwargs) -> ToolResult:
        now = datetime.now()
        formatted = now.strftime("%A, %B %d, %Y at %H:%M")
        return ToolResult(content=formatted, preview=formatted)
