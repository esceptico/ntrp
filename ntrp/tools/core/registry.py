from typing import Any

from pydantic import ValidationError

from ntrp.sources.base import Source
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def copy_with(self, *extra_tools: Tool) -> "ToolRegistry":
        registry = ToolRegistry()
        registry._tools = dict(self._tools)
        for tool in extra_tools:
            registry.register(tool)
        return registry

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(self, name: str, execution: ToolExecution, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools[name]

        if tool.input_model is not None:
            try:
                validated = tool.input_model(**arguments)
                arguments = validated.model_dump()
            except ValidationError as e:
                errors = "; ".join(
                    f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}" for err in e.errors() if err.get("loc")
                )
                return ToolResult(
                    content=f"Invalid arguments: {errors}",
                    preview="Validation error",
                    is_error=True,
                )

        if tool.source_type is not None and not execution.ctx.get_source(tool.source_type):
            return ToolResult(
                content=f"Required source ({tool.source_type.__name__}) is no longer available.",
                preview="Source unavailable",
                is_error=True,
            )
        if tool.requires_memory and not execution.ctx.memory:
            return ToolResult(
                content="Memory is not available.",
                preview="No memory",
                is_error=True,
            )

        info = await tool.approval_info(execution, **arguments)
        if info is not None:
            rejection = await execution.request_approval(
                info.description,
                preview=info.preview,
                diff=info.diff,
            )
            if rejection is not None:
                return rejection.to_result()

        return await tool.execute(execution, **arguments)

    def get_schemas(
        self,
        *,
        sources: dict[str, Source] | None = None,
        has_memory: bool = False,
        names: set[str] | None = None,
        mutates: bool | None = None,
    ) -> list[dict]:
        schemas = []
        for name, tool in self._tools.items():
            if names is not None and name not in names:
                continue
            if mutates is not None and tool.mutates != mutates:
                continue
            if tool.source_type is not None:
                if not sources or not any(isinstance(s, tool.source_type) for s in sources.values()):
                    continue
            if tool.requires_memory and not has_memory:
                continue
            schemas.append(tool.to_dict())
        return schemas

    @property
    def tools(self) -> dict[str, Tool]:
        return self._tools

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
