from typing import Any

from ntrp.memory.facts import FactMemory
from ntrp.schedule.store import ScheduleStore
from ntrp.skills.registry import SkillRegistry
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
        available_notifiers: dict[str, str] | None = None,
        registry: ToolRegistry | None = None,
        skill_registry: SkillRegistry | None = None,
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
            available_notifiers=available_notifiers,
            working_dir=working_dir,
            skill_registry=skill_registry,
        )
        for create_tools in TOOL_FACTORIES:
            for tool in create_tools(deps):
                self.registry.register(tool)

    def with_registry(self, registry: ToolRegistry) -> "ToolExecutor":
        """Create a shallow copy of this executor with a different registry."""
        clone = ToolExecutor.__new__(ToolExecutor)
        clone.sources = self.sources
        clone.memory = self.memory
        clone.model = self.model
        clone.search_index = self.search_index
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
        return self.registry.get_schemas(mutates=mutates)
