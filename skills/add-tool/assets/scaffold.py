from pydantic import BaseModel, Field

from ntrp.tools.core import ToolResult, tool
from ntrp.tools.core.context import ToolExecution

# from ntrp.tools.core.types import ApprovalInfo


class ToolInput(BaseModel):
    query: str = Field(description="TODO: describe this parameter")


async def execute_tool(execution: ToolExecution, args: ToolInput) -> ToolResult:
    result = f"You asked: {args.query}"
    return ToolResult(content=result, preview="Done")


# async def approve_tool(execution: ToolExecution, args: ToolInput) -> ApprovalInfo | None:
#     return ApprovalInfo(
#         description="what will be affected",
#         preview="human-readable summary",
#         diff=None,
#     )


tools = {
    "__TOOL_NAME__": tool(
        display_name="__DISPLAY_NAME__",
        description="TODO: what this tool does; the LLM reads this to decide when to use it",
        input_model=ToolInput,
        # requires={"memory"},  # uncomment if the tool needs a service
        # mutates=True,         # uncomment if the tool modifies external state
        # approval=approve_tool,
        execute=execute_tool,
    )
}
