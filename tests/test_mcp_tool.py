from datetime import UTC, datetime
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as McpTool

from ntrp.context.models import SessionState
from ntrp.mcp.tool import MCPTool
from ntrp.tools.core.context import IOBridge, RunContext, ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry


class FakeMCPSession:
    def __init__(self, result: CallToolResult):
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((tool_name, arguments))
        return self.result


@pytest.mark.asyncio
async def test_mcp_tool_executes_remote_tool_and_adapts_result():
    mcp_tool = McpTool(
        name="search",
        description="Search notes",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    session = FakeMCPSession(
        CallToolResult(
            content=[TextContent(type="text", text="Found 1 note")],
            structuredContent={"hits": [{"path": "Note.md"}]},
        )
    )
    tool = MCPTool("obsidian", mcp_tool, session)
    execution = ToolExecution(
        tool_id="call-1",
        tool_name=tool.name,
        ctx=ToolContext(
            session_state=SessionState(session_id="session-1", started_at=datetime(2026, 4, 30, tzinfo=UTC)),
            registry=ToolRegistry(),
            run=RunContext(run_id="run-1"),
            io=IOBridge(),
        ),
    )

    result = await tool.execute(execution, query="notes")

    assert session.calls == [("search", {"query": "notes"})]
    assert result.content == "Found 1 note"
    assert result.data == {"structuredContent": {"hits": [{"path": "Note.md"}]}}
