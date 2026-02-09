from typing import Any

from ntrp.memory.facts import FactMemory
from ntrp.schedule.store import ScheduleStore
from ntrp.sources.base import Source
from ntrp.tools.core.base import ToolResult
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.specs import TOOL_FACTORIES, ToolDeps


class ToolExecutor:
    def __init__(
        self,
        sources: dict[str, Source],
        model: str,
        memory: FactMemory | None = None,
        working_dir: str | None = None,
        search_index: Any | None = None,
        schedule_store: ScheduleStore | None = None,
        default_notifiers: list[str] | None = None,
        registry: ToolRegistry | None = None,
    ):
        self.sources = sources
        self.memory = memory
        self.model = model
        self.search_index = search_index

        self.registry = registry or ToolRegistry()

        deps = ToolDeps(
            sources=sources,
            memory=memory,
            search_index=search_index,
            schedule_store=schedule_store,
            default_notifiers=default_notifiers,
            working_dir=working_dir,
        )
        for create_tools in TOOL_FACTORIES:
            for tool in create_tools(deps):
                self.registry.register(tool)

    async def execute(self, tool_name: str, arguments: dict, execution: ToolExecution) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(
                content=f"Unknown tool: {tool_name}. Check available tools in the system prompt.",
                preview="Unknown tool",
            )

        return await self.registry.execute(tool_name, execution, **arguments)

    def get_tools(self, mutates: bool | None = None) -> list[dict]:
        return self.registry.get_schemas(mutates=mutates)
