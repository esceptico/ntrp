from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution

if TYPE_CHECKING:
    from mcp.types import Tool as McpTool

    from ntrp.mcp.session import MCPServerSession


class MCPTool(Tool):
    requires: ClassVar[frozenset[str]] = frozenset({"mcp"})
    input_model = None
    mutates = True

    def __init__(self, server_name: str, mcp_tool: McpTool, session: MCPServerSession):
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
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                elif hasattr(block, "data"):
                    parts.append(f"[{block.type}: {len(block.data)} bytes]")
                else:
                    parts.append(str(block))
            content = "\n".join(parts)
            return ToolResult(
                content=content,
                preview=content[:100] if content else "Empty result",
                is_error=bool(result.isError),
            )
        except Exception as e:
            return ToolResult(
                content=f"MCP tool error ({self._server_name}/{self._mcp_tool.name}): {e}",
                preview="MCP error",
                is_error=True,
            )

    def to_dict(self) -> dict:
        schema: dict = {"name": self.name, "description": self.description}
        input_schema = self._mcp_tool.inputSchema
        if input_schema:
            schema["parameters"] = {
                "type": "object",
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", []),
            }
        return {"type": "function", "function": schema}
