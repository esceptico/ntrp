from typing import Any

from pydantic import ValidationError

from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolExecution


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._schemas: dict[str, dict] = {}  # Pre-computed schemas

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self._schemas[tool.name] = tool.to_dict()

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

        info = await tool.approval_info(**arguments)
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
