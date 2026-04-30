from typing import Any, ClassVar, Protocol

from mcp.types import CallToolResult
from mcp.types import Tool as McpTool

from ntrp.mcp.results import call_tool_result_to_tool_result
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class MCPToolSession(Protocol):
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> CallToolResult: ...


class MCPTool(Tool):
    requires: ClassVar[frozenset[str]] = frozenset({"mcp"})
    input_model = None
    mutates = True

    def __init__(self, server_name: str, mcp_tool: McpTool, session: MCPToolSession):
        self._server_name = server_name
        self._mcp_tool = mcp_tool
        self._session = session

    @property
    def name(self) -> str:
        return f"mcp_{self._server_name}__{self._mcp_tool.name}"

    @property
    def display_name(self) -> str:
        return f"{self._mcp_tool.name} ({self._server_name})"

    @property
    def description(self) -> str:
        return self._mcp_tool.description or f"MCP tool from {self._server_name}"

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        try:
            result = await self._session.call_tool(self._mcp_tool.name, kwargs)
            return call_tool_result_to_tool_result(result)
        except Exception as e:
            return ToolResult(
                content=f"MCP tool error ({self._server_name}/{self._mcp_tool.name}): {e}",
                preview="MCP error",
                is_error=True,
            )

    def to_dict(self, name: str) -> dict:
        schema: dict = {"name": name, "description": self.description}
        input_schema = self._mcp_tool.inputSchema
        if input_schema:
            schema["parameters"] = {
                "type": "object",
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", []),
            }
        return {"type": "function", "function": schema}
