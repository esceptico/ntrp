from typing import TYPE_CHECKING

from ntrp.tools.core.base import ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.specs import TOOL_FACTORIES, ToolDeps

if TYPE_CHECKING:
    from ntrp.server.runtime import Runtime


class ToolExecutor:
    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime
        self.registry = ToolRegistry()

        deps = ToolDeps(
            search_index=runtime.indexer.index,
            schedule_store=runtime.schedule_store,
            skill_registry=runtime.skill_registry,
            notifier_service=runtime.notifier_service,
        )
        for create_tools in TOOL_FACTORIES:
            for tool in create_tools(deps):
                self.registry.register(tool)

    def with_registry(self, registry: ToolRegistry) -> "ToolExecutor":
        clone = ToolExecutor.__new__(ToolExecutor)
        clone.runtime = self.runtime
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
            sources=self.runtime.source_mgr.sources,
            has_memory=self.runtime.memory is not None,
            mutates=mutates,
        )

    def get_tool_metadata(self) -> list[dict]:
        return [tool.get_metadata() for tool in self.registry.tools.values()]
