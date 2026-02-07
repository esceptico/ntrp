from typing import Any

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
from ntrp.tools.core.context import ToolExecution
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
from ntrp.tools.scratchpad import ListScratchpadTool, ReadScratchpadTool, WriteScratchpadTool
from ntrp.tools.web import WebFetchTool, WebSearchTool

SOURCE_TOOLS: list[type[Tool]] = [
    ListNotesTool,
    ReadNoteTool,
    EditNoteTool,
    CreateNoteTool,
    DeleteNoteTool,
    MoveNoteTool,
    SendEmailTool,
    ReadEmailTool,
    ListEmailTool,
    SearchEmailTool,
    ListCalendarTool,
    SearchCalendarTool,
    CreateCalendarEventTool,
    EditCalendarEventTool,
    DeleteCalendarEventTool,
    ListBrowserTool,
    SearchBrowserTool,
    WebSearchTool,
    WebFetchTool,
]

MEMORY_TOOLS: list[type[Tool]] = [RememberTool, RecallTool, ForgetTool]


class ToolExecutor:
    def __init__(
        self,
        sources: dict[str, Any],
        model: str,
        memory: FactMemory | None = None,
        working_dir: str | None = None,
        search_index: Any | None = None,
        registry: ToolRegistry | None = None,
    ):
        self.sources = sources
        self.memory = memory
        self.model = model
        self.search_index = search_index

        self.registry = registry or ToolRegistry()
        self._register_tools(working_dir)

    def _register_tools(self, working_dir: str | None) -> None:
        for tool_cls in SOURCE_TOOLS:
            if tool_cls.source_type is None:
                continue
            if source := self._get_source_for_type(tool_cls.source_type):
                self.registry.register(tool_cls(source))

        if self.memory:
            for tool_cls in MEMORY_TOOLS:
                self.registry.register(tool_cls(self.memory))

        if notes := self._get_source_for_type(NotesSource):
            self.registry.register(SearchNotesTool(notes, search_index=self.search_index))

        self.registry.register(BashTool(working_dir=working_dir))
        self.registry.register(ReadFileTool(base_path=working_dir))
        self.registry.register(ExploreTool())
        self.registry.register(AskChoiceTool())
        self.registry.register(WriteScratchpadTool())
        self.registry.register(ReadScratchpadTool())
        self.registry.register(ListScratchpadTool())

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
        return self.registry.get_schemas(mutates=mutates)
