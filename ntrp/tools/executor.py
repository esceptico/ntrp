from typing import Any

from ntrp.core.isolation import IsolationLevel
from ntrp.memory.facts import FactMemory
from ntrp.sources.base import NotesSource
from ntrp.tools.ask_choice import AskChoiceTool
from ntrp.tools.bash import BashTool
from ntrp.tools.browser import ListBrowserTool, SearchBrowserTool
from ntrp.tools.calendar import (
    CreateCalendarEventTool,
    DeleteCalendarEventTool,
    EditCalendarEventTool,
    ListCalendarTool,
    SearchCalendarTool,
)
from ntrp.tools.core.base import Tool, ToolResult
from ntrp.tools.core.context import ToolContext, ToolExecution
from ntrp.tools.core.registry import ToolRegistry
from ntrp.tools.email import ListEmailTool, ReadEmailTool, SearchEmailTool, SendEmailTool
from ntrp.tools.explore import ExploreTool
from ntrp.tools.files import ReadFileTool
from ntrp.tools.memory import ForgetTool, RecallTool, RememberTool
from ntrp.tools.notes import (
    CreateNoteTool,
    DeleteNoteTool,
    EditNoteTool,
    ListNotesTool,
    MoveNoteTool,
    ReadNoteTool,
    SearchNotesTool,
)
from ntrp.tools.scratchpad import ReadScratchpadTool, WriteScratchpadTool
from ntrp.tools.web import WebFetchTool, WebSearchTool

# Source-based tools: auto-matched by source_type, instantiated with source
SOURCE_TOOLS: list[type[Tool]] = [
    # Notes (CRUD, no search - search needs index)
    ListNotesTool,
    ReadNoteTool,
    EditNoteTool,
    CreateNoteTool,
    DeleteNoteTool,
    MoveNoteTool,
    # Email
    SendEmailTool,
    ReadEmailTool,
    ListEmailTool,
    SearchEmailTool,
    # Calendar
    ListCalendarTool,
    SearchCalendarTool,
    CreateCalendarEventTool,
    EditCalendarEventTool,
    DeleteCalendarEventTool,
    # Browser
    ListBrowserTool,
    SearchBrowserTool,
    # Web
    WebSearchTool,
    WebFetchTool,
]

# Memory tools: use FactMemory (which has built-in vector search)
MEMORY_TOOLS: list[type[Tool]] = [RememberTool, RecallTool, ForgetTool]


class ToolExecutor:
    def __init__(
        self,
        sources: dict[str, Any],
        model: str,
        memory: FactMemory | None = None,
        working_dir: str | None = None,
        search_index: Any | None = None,
    ):
        self.sources = sources
        self.memory = memory
        self.model = model
        self.search_index = search_index

        self.registry = ToolRegistry()
        self._register_tools(working_dir)

    async def spawn(
        self,
        ctx: ToolContext,
        task: str,
        *,
        system_prompt: str,
        tools: list[dict] | None = None,
        timeout: int = 120,
        model_override: str | None = None,
        parent_id: str | None = None,
        isolation: IsolationLevel = IsolationLevel.FULL,
    ) -> str:
        if not ctx.spawn_fn:
            return "Error: spawn capability not available"

        return await ctx.spawn_fn(
            ctx,
            task,
            system_prompt=system_prompt,
            tools=tools,
            timeout=timeout,
            model_override=model_override,
            parent_id=parent_id,
            isolation=isolation,
        )

    def _register_tools(self, working_dir: str | None) -> None:
        # 1. Source-based tools (auto-matched by source_type)
        for tool_cls in SOURCE_TOOLS:
            if tool_cls.source_type is None:
                continue
            if source := self._get_source_for_type(tool_cls.source_type):
                self.registry.register(tool_cls(source))

        # 2. Memory tools (FactMemory has built-in vector search)
        if self.memory:
            for tool_cls in MEMORY_TOOLS:
                self.registry.register(tool_cls(self.memory))

        # 3. Search tools (need source + search index for hybrid search)
        if notes := self._get_source_for_type(NotesSource):
            self.registry.register(SearchNotesTool(notes, search_index=self.search_index))

        # 4. Standalone tools (no dependencies)
        self.registry.register(BashTool(working_dir=working_dir))
        self.registry.register(ReadFileTool(base_path=working_dir))
        self.registry.register(ExploreTool())
        self.registry.register(AskChoiceTool())
        self.registry.register(WriteScratchpadTool())
        self.registry.register(ReadScratchpadTool())

    def _get_source_for_type(self, source_type: type) -> Any | None:
        for source in self.sources.values():
            if isinstance(source, source_type):
                return source
        return None

    async def execute(self, tool_name: str, arguments: dict, execution: ToolExecution) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(f"Unknown tool: {tool_name}. Check available tools in the system prompt.", "Unknown tool")

        return await self.registry.execute(tool_name, execution, **arguments)

    def get_tools(self, mutates: bool | None = None) -> list[dict]:
        """Get tools in OpenAI format.

        Args:
            mutates: Filter by mutates value. None = all, False = read-only.
        """
        return self.registry.get_schemas(mutates=mutates)
