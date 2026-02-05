from typing import Any

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._schemas: dict[str, dict] = {}  # Pre-computed schemas

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        # Pre-compute and cache schema at registration time
        self._schemas[tool.name] = tool.to_dict()

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(self, name: str, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        tool = self._tools[name]
        return await tool.execute(execution, **kwargs)

    def get_schemas(
        self,
        *,
        names: set[str] | None = None,
        mutates: bool | None = None,
    ) -> list[dict]:
        schemas = []
        for name, tool in self._tools.items():
            if names is not None and name not in names:
                continue
            if mutates is not None and tool.mutates != mutates:
                continue
            schemas.append(self._schemas[name])
        return schemas

    @property
    def tools(self) -> dict[str, Tool]:
        return self._tools

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
