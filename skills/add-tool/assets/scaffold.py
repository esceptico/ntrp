from typing import Any

from pydantic import BaseModel, Field

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class ToolInput(BaseModel):
    query: str = Field(description="TODO: describe this parameter")


class UserTool(Tool):
    name = "todo_tool_name"
    display_name = "TodoDisplayName"
    description = "TODO: what this tool does — the LLM reads this to decide when to use it"
    # requires = frozenset({"notes"})  # uncomment if tool needs a source/service
    # mutates = True                   # uncomment if tool modifies external state
    input_model = ToolInput

    # async def approval_info(self, execution: ToolExecution, **kwargs: Any) -> ApprovalInfo | None:
    #     """Uncomment if mutates = True. Describes the action before user approves."""
    #     return ApprovalInfo(
    #         description="what will be affected",
    #         preview="human-readable summary",
    #         diff=None,
    #     )

    async def execute(self, execution: ToolExecution, query: str, **kwargs: Any) -> ToolResult:
        # TODO: implement tool logic
        result = f"You asked: {query}"
        return ToolResult(content=result, preview="Done")
