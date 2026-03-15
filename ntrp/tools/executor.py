from collections.abc import Callable
from typing import Any, Self

from ntrp.logging import get_logger
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.discover import discover_user_tools
from ntrp.tools.specs import ALL_TOOLS

_logger = get_logger(__name__)


class ToolExecutor:
    def __init__(
        self,
        mcp_tools: list[Tool] | None = None,
        get_services: Callable[[], dict[str, Any]] = dict,
    ):
        self._get_services = get_services
        self.registry = ToolRegistry()
        for cls in ALL_TOOLS:
            self.registry.register(cls())
        for cls in discover_user_tools():
            if cls.name in self.registry:
                _logger.warning("User tool %r skipped — conflicts with built-in", cls.name)
            else:
                self.registry.register(cls())
                _logger.info("Loaded user tool: %s", cls.name)
        if mcp_tools:
            for tool in mcp_tools:
                if tool.name in self.registry:
                    _logger.warning("MCP tool %r skipped — conflicts with existing tool", tool.name)
                else:
                    self.registry.register(tool)
                    _logger.info("Loaded MCP tool: %s", tool.name)

        capabilities = frozenset(self._get_services())
        hidden = [t for t in self.registry.tools.values() if t.requires and not t.requires.issubset(capabilities)]
        if hidden:
            by_req = {}
            for t in hidden:
                key = ", ".join(sorted(t.requires))
                by_req.setdefault(key, []).append(t.name)
            for req, names in by_req.items():
                _logger.info("Tools hidden (missing %s): %s", req, ", ".join(names))

    @property
    def tool_services(self) -> dict[str, Any]:
        return self._get_services()

    def with_registry(self, registry: ToolRegistry) -> Self:
        clone = ToolExecutor.__new__(ToolExecutor)
        clone._get_services = self._get_services
        clone.registry = registry
        return clone

    async def execute(self, tool_name: str, arguments: dict, execution: ToolExecution) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(
                content=f"Unknown tool: {tool_name}. Check available tools in the system prompt.",
                preview="Unknown tool",
            )

        return await self.registry.execute(tool_name, execution, arguments)

    def get_tools(self, mutates: bool | None = None) -> list[dict]:
        return self.registry.get_schemas(
            capabilities=frozenset(self._get_services()),
            mutates=mutates,
        )

    def get_tool_metadata(self) -> list[dict]:
        return [tool.get_metadata() for tool in self.registry.tools.values()]
