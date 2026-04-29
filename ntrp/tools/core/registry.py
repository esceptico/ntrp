from collections.abc import Sequence
from typing import Any, Self

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.middleware import DEFAULT_TOOL_MIDDLEWARE, ToolCall, ToolMiddleware


class ToolRegistry:
    def __init__(self, middlewares: Sequence[ToolMiddleware] = DEFAULT_TOOL_MIDDLEWARE):
        self._tools: dict[str, Tool] = {}
        self._middlewares = tuple(middlewares)

    def register(self, name: str, tool: Tool) -> None:
        if name in self._tools:
            raise ValueError(f"duplicate tool name: {name}")
        self._tools[name] = tool

    def copy_with(self, extra_tools: dict[str, Tool]) -> Self:
        registry = ToolRegistry(middlewares=self._middlewares)
        registry._tools = dict(self._tools)
        for name, tool in extra_tools.items():
            registry.register(name, tool)
        return registry

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(self, name: str, execution: ToolExecution, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools[name]
        call = ToolCall(name=name, tool=tool, execution=execution, arguments=dict(arguments))
        return await self._dispatch(call)

    async def _dispatch(self, call: ToolCall) -> ToolResult:
        async def dispatch(index: int, current: ToolCall) -> ToolResult:
            if index == len(self._middlewares):
                return await current.tool.execute(current.execution, **current.arguments)

            middleware = self._middlewares[index]

            async def next_call(next_current: ToolCall) -> ToolResult:
                return await dispatch(index + 1, next_current)

            return await middleware(current, next_call)

        return await dispatch(0, call)

    def get_schemas(
        self,
        *,
        capabilities: frozenset[str] = frozenset(),
        names: set[str] | None = None,
        mutates: bool | None = None,
    ) -> list[dict]:
        schemas = []
        for name, tool in self._tools.items():
            if names is not None and name not in names:
                continue
            if mutates is not None and tool.mutates != mutates:
                continue
            if not tool.requires.issubset(capabilities):
                continue
            schemas.append(tool.to_dict(name))
        return schemas

    @property
    def tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
