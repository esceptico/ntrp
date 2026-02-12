"""
ntrp MCP Server

Exposes ntrp's tool registry as MCP tools so any MCP client
(Claude Desktop, Cursor, Claude Code, etc.) can use them directly.

Transports:
    # stdio (default) — for Claude Desktop / Claude Code
    ntrp mcp

    # Streamable HTTP — for remote clients
    ntrp mcp --http
    ntrp mcp --http --port 3001
"""

import contextlib
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

from mcp.server import Server
from mcp.types import TextContent, Tool

from ntrp.context.models import SessionState
from ntrp.logging import get_logger
from ntrp.server.runtime import Runtime
from ntrp.tools.core.base import ToolResult
from ntrp.tools.core.context import ToolContext, ToolExecution

_logger = get_logger(__name__)

# Tools to exclude from MCP exposure
EXCLUDED_TOOLS = frozenset(
    {
        "explore",  # Needs spawn_fn for sub-agent spawning
        "ask_choice",  # Needs interactive UI (choice queue)
        "bash",  # MCP clients already have shell access
        "read_file",  # MCP clients already have file reading
        "write_scratchpad",  # Session-scoped, resets each connection
        "read_scratchpad",  # Session-scoped, resets each connection
        "list_scratchpad",  # Session-scoped, resets each connection
    }
)


def _ntrp_tool_to_mcp(name: str, schema: dict) -> Tool:
    """Convert an ntrp tool schema (OpenAI function format) to MCP Tool."""
    func = schema.get("function", {})
    params = func.get("parameters")
    input_schema = params if params else {"type": "object", "properties": {}}
    return Tool(
        name=name,
        description=func.get("description", ""),
        inputSchema=input_schema,
    )


async def create_server() -> tuple[Server, Runtime]:
    """Create and configure the MCP server backed by an ntrp Runtime."""
    runtime = Runtime()
    await runtime.connect()

    server = Server("ntrp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for name, tool in runtime.executor.registry.tools.items():
            if name in EXCLUDED_TOOLS:
                continue
            schema = tool.to_dict()
            tools.append(_ntrp_tool_to_mcp(name, schema))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name in EXCLUDED_TOOLS:
            return [TextContent(type="text", text=f"Tool '{name}' is not available via MCP.")]

        tool = runtime.executor.registry.get(name)
        if not tool:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        # Fresh session per call — MCP is stateless request/response
        now = datetime.now(UTC)
        session_state = SessionState(
            session_id=f"mcp_{now.strftime('%Y%m%d_%H%M%S')}",
            started_at=now,
            skip_approvals=True,  # No UI for approval prompts
        )

        tool_ctx = ToolContext(
            session_state=session_state,
            registry=runtime.executor.registry,
            memory=runtime.memory,
            channel=runtime.channel,
            run_id=str(uuid4())[:8],
        )

        execution = ToolExecution(
            tool_id=str(uuid4())[:8],
            tool_name=name,
            ctx=tool_ctx,
        )

        try:
            result: ToolResult = await runtime.executor.registry.execute(name, execution, arguments)
            return [TextContent(type="text", text=result.content)]
        except Exception as e:
            _logger.exception("MCP tool execution failed: %s", name)
            return [TextContent(type="text", text=f"Error executing {name}: {e}")]

    return server, runtime


async def run_stdio() -> None:
    """Run the MCP server over stdio transport."""
    from mcp.server.stdio import stdio_server

    server, runtime = await create_server()
    print("ntrp MCP server starting (stdio)", file=sys.stderr)

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await runtime.close()


async def run_http(host: str = "127.0.0.1", port: int = 3000) -> None:
    """Run the MCP server over streamable HTTP transport."""
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    server, runtime = await create_server()

    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield
        await runtime.close()

    app = Starlette(
        routes=[Mount("/mcp", app=session_manager.handle_request)],
        lifespan=lifespan,
    )

    import uvicorn

    print(f"ntrp MCP server starting (HTTP) on {host}:{port}", file=sys.stderr)
    config = uvicorn.Config(app, host=host, port=port)
    srv = uvicorn.Server(config)
    await srv.serve()
