import asyncio
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.types import CallToolResult
from mcp.types import Tool as McpTool

from ntrp.mcp.models import HttpTransport, MCPServerConfig, StdioTransport


class MCPServerSession:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._all_tools: list[McpTool] = []
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

    @property
    def all_tools(self) -> list[McpTool]:
        return self._all_tools

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
            http_client = create_mcp_http_client(headers=transport.headers or None)
            await self._exit_stack.enter_async_context(http_client)
            read, write, _ = await self._exit_stack.enter_async_context(
                streamable_http_client(transport.url, http_client=http_client)
            )
        else:
            raise ValueError(f"Unsupported transport: {type(transport)}")

        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

        response = await self._session.list_tools()
        self._all_tools = response.tools
        whitelist = self.config.tools
        if whitelist is not None:
            allowed = set(whitelist)
            self._tools = [t for t in response.tools if t.name in allowed]
        else:
            self._tools = response.tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        if not self._session:
            raise RuntimeError(f"MCP server {self.name!r} is not connected")
        return await self._session.call_tool(tool_name, arguments)

    async def close(self) -> None:
        try:
            await self._exit_stack.aclose()
        except (RuntimeError, asyncio.CancelledError):
            pass
        self._session = None
        self._all_tools = []
        self._tools = []
