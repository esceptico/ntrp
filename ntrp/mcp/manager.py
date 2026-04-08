from ntrp.integrations.base import IntegrationHealth, ToolProviderStatus
from ntrp.logging import get_logger
from ntrp.mcp.models import parse_server_config
from ntrp.mcp.session import MCPServerSession
from ntrp.mcp.tool import MCPTool

_logger = get_logger(__name__)


class MCPManager:
    def __init__(self):
        self._sessions: dict[str, MCPServerSession] = {}
        self._tools: list[MCPTool] = []
        self._errors: dict[str, str] = {}

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    @property
    def sessions(self) -> dict[str, MCPServerSession]:
        return self._sessions

    async def connect(self, server_configs: dict[str, dict]) -> None:
        for name, raw in server_configs.items():
            if raw.get("enabled") is False:
                continue
            try:
                config = parse_server_config(name, raw)
            except ValueError as e:
                _logger.warning("Invalid MCP config for %r: %s", name, e)
                self._errors[name] = str(e)
                continue

            session = MCPServerSession(config)
            try:
                await session.connect()
                self._sessions[name] = session
                for mcp_tool in session.tools:
                    self._tools.append(MCPTool(name, mcp_tool, session))
                _logger.info("MCP server %r connected", name, tools=len(session.tools))
            except BaseException as e:
                _logger.warning("Failed to connect MCP server %r: %s", name, e)
                self._errors[name] = str(e)
                try:
                    await session.close()
                except BaseException:
                    pass

    def list_providers(self) -> list[ToolProviderStatus]:
        out: list[ToolProviderStatus] = []
        for name, session in self._sessions.items():
            out.append(
                ToolProviderStatus(
                    id=f"mcp:{name}",
                    label=name,
                    kind="mcp",
                    health=IntegrationHealth(status="connected"),
                    tool_count=len(session.tools),
                )
            )
        for name, error in self._errors.items():
            if name in self._sessions:
                continue
            out.append(
                ToolProviderStatus(
                    id=f"mcp:{name}",
                    label=name,
                    kind="mcp",
                    health=IntegrationHealth(status="error", detail=error),
                    tool_count=0,
                )
            )
        return out

    async def close(self) -> None:
        for name, session in self._sessions.items():
            try:
                await session.close()
            except BaseException:
                _logger.warning("Error closing MCP server %r", name, exc_info=True)
        self._sessions.clear()
        self._tools.clear()
        self._errors.clear()
