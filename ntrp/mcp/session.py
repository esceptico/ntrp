from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult
from mcp.types import Tool as McpTool

from ntrp.mcp.models import HttpTransport, MCPServerConfig, StdioTransport


class MCPServerSession:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._tools: list[McpTool] = []

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def tools(self) -> list[McpTool]:
        return self._tools

    async def connect(self) -> None:
        transport = self.config.transport
        if isinstance(transport, StdioTransport):
            params = StdioServerParameters(
                command=transport.command,
                args=transport.args,
                env=transport.env,
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        elif isinstance(transport, HttpTransport):
            read, write = await self._exit_stack.enter_async_context(streamablehttp_client(transport.url))
        else:
            raise ValueError(f"Unsupported transport: {type(transport)}")

        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

        response = await self._session.list_tools()
        self._tools = response.tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        if not self._session:
            raise RuntimeError(f"MCP server {self.name!r} is not connected")
        return await self._session.call_tool(tool_name, arguments)

    async def close(self) -> None:
        await self._exit_stack.aclose()
        self._session = None
        self._tools = []
