from collections.abc import Mapping, Sequence
from typing import Any, Self

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.middleware import DEFAULT_TOOL_MIDDLEWARE, ToolCall, ToolMiddleware
from ntrp.tools.core.types import ApprovalMode, ToolAction, ToolOverrideDecision, ToolPolicy


def tool_changes_state(tool: Tool) -> bool:
    return tool.policy.action in {ToolAction.DRAFT, ToolAction.WRITE, ToolAction.EXECUTE}


class ToolRegistry:
    def __init__(
        self,
        middlewares: Sequence[ToolMiddleware] = DEFAULT_TOOL_MIDDLEWARE,
        tool_overrides: Mapping[str, ToolOverrideDecision | str] | None = None,
    ):
        self._tools: dict[str, Tool] = {}
        self._sources: dict[str, str] = {}
        self._middlewares = tuple(middlewares)
        self._tool_overrides = _normalize_overrides(tool_overrides)

    def register(self, name: str, tool: Tool, *, source: str = "unknown") -> None:
        if name in self._tools:
            raise ValueError(f"duplicate tool name: {name}")
        self._tools[name] = tool
        self._sources[name] = source

    def copy_with(self, extra_tools: dict[str, Tool]) -> Self:
        registry = ToolRegistry(middlewares=self._middlewares, tool_overrides=self._tool_overrides)
        registry._tools = dict(self._tools)
        registry._sources = dict(self._sources)
        for name, tool in extra_tools.items():
            registry.register(name, tool)
        return registry

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_source(self, name: str) -> str | None:
        return self._sources.get(name)

    def get_override(self, name: str) -> ToolOverrideDecision | None:
        return self._tool_overrides.get(name)

    async def execute(self, name: str, execution: ToolExecution, arguments: dict[str, Any]) -> ToolResult:
        if self._tool_overrides.get(name) == ToolOverrideDecision.DENY:
            return ToolResult(
                content=f"Tool denied by settings: {name}",
                preview="Denied by settings",
                is_error=True,
            )
        tool = self._tools[name]
        call = ToolCall(name=name, tool=self._effective_tool(name, tool), execution=execution, arguments=dict(arguments))
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
        read_only: bool | None = None,
        actions: frozenset[ToolAction] | None = None,
    ) -> list[dict]:
        schemas = []
        for name, tool in self._tools.items():
            if self._tool_overrides.get(name) == ToolOverrideDecision.DENY:
                continue
            tool = self._effective_tool(name, tool)
            if names is not None and name not in names:
                continue
            if read_only is not None and (tool.policy.action == ToolAction.READ) != read_only:
                continue
            if actions is not None and tool.policy.action not in actions:
                continue
            if not tool.policy.permissions.issubset(capabilities):
                continue
            schemas.append(tool.to_dict(name))
        return schemas

    def get_metadata(self) -> list[dict]:
        metadata = []
        for name, tool in self._tools.items():
            effective = self._effective_tool(name, tool)
            item = effective.get_metadata(name)
            item["source"] = self._sources.get(name)
            if override := self._tool_overrides.get(name):
                item["override"] = override.value
            metadata.append(item)
        return metadata

    def _effective_tool(self, name: str, tool: Tool) -> Tool:
        override = self._tool_overrides.get(name)
        if override == ToolOverrideDecision.APPROVE:
            policy = tool.policy.model_copy(update={"requires_approval": False, "approval_mode": ApprovalMode.NEVER})
            return _PolicyOverrideTool(tool, policy)
        if override == ToolOverrideDecision.ASK:
            policy = tool.policy.model_copy(update={"requires_approval": True, "approval_mode": ApprovalMode.ALWAYS})
            return _PolicyOverrideTool(tool, policy)
        return tool

    @property
    def tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


class _PolicyOverrideTool(Tool):
    def __init__(self, inner: Tool, policy: ToolPolicy):
        self._inner = inner
        self.policy = policy

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def display_name(self) -> str | None:
        return self._inner.display_name

    @property
    def description(self) -> str:
        return self._inner.description

    @property
    def input_model(self):
        return self._inner.input_model

    @property
    def kind(self) -> str:
        return self._inner.kind

    async def approval_info(self, execution: ToolExecution, **kwargs: Any):
        return await self._inner.approval_info(execution, **kwargs)

    async def execute(self, execution: ToolExecution, **kwargs: Any) -> ToolResult:
        return await self._inner.execute(execution, **kwargs)

    def to_dict(self, name: str) -> dict:
        return self._inner.to_dict(name)


def _normalize_overrides(
    raw: Mapping[str, ToolOverrideDecision | str] | None,
) -> dict[str, ToolOverrideDecision]:
    overrides: dict[str, ToolOverrideDecision] = {}
    for name, value in (raw or {}).items():
        try:
            overrides[name] = value if isinstance(value, ToolOverrideDecision) else ToolOverrideDecision(value)
        except ValueError:
            continue
    return overrides
