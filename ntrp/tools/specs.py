from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ntrp.memory.facts import FactMemory
from ntrp.schedule.store import ScheduleStore
from ntrp.sources.base import BrowserSource, CalendarSource, EmailSource, NotesSource, Source, WebSearchSource
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
from ntrp.tools.core.base import Tool
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
from ntrp.tools.schedule import CancelScheduleTool, GetScheduleResultTool, ListSchedulesTool, ScheduleTaskTool
from ntrp.tools.scratchpad import ListScratchpadTool, ReadScratchpadTool, WriteScratchpadTool
from ntrp.tools.web import WebFetchTool, WebSearchTool


@dataclass(frozen=True)
class ToolDeps:
    sources: dict[str, Source]
    memory: FactMemory | None = None
    search_index: Any | None = None
    schedule_store: ScheduleStore | None = None
    default_email: str | None = None
    working_dir: str | None = None


def _find_source(sources: dict[str, Source], source_type: type) -> Any | None:
    for source in sources.values():
        if isinstance(source, source_type):
            return source
    return None


def _create_notes_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, NotesSource)
    if not source:
        return []
    return [
        ListNotesTool(source),
        ReadNoteTool(source),
        EditNoteTool(source),
        CreateNoteTool(source),
        DeleteNoteTool(source),
        MoveNoteTool(source),
        SearchNotesTool(source, search_index=deps.search_index),
    ]


def _create_email_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, EmailSource)
    if not source:
        return []
    return [
        SendEmailTool(source),
        ReadEmailTool(source),
        ListEmailTool(source),
        SearchEmailTool(source),
    ]


def _create_calendar_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, CalendarSource)
    if not source:
        return []
    return [
        ListCalendarTool(source),
        SearchCalendarTool(source),
        CreateCalendarEventTool(source),
        EditCalendarEventTool(source),
        DeleteCalendarEventTool(source),
    ]


def _create_browser_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, BrowserSource)
    if not source:
        return []
    return [
        ListBrowserTool(source),
        SearchBrowserTool(source),
    ]


def _create_web_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, WebSearchSource)
    if not source:
        return []
    return [
        WebSearchTool(source),
        WebFetchTool(source),
    ]


def _create_memory_tools(deps: ToolDeps) -> list[Tool]:
    if not deps.memory:
        return []
    return [
        RememberTool(deps.memory),
        RecallTool(deps.memory),
        ForgetTool(deps.memory),
    ]


def _create_schedule_tools(deps: ToolDeps) -> list[Tool]:
    if not deps.schedule_store:
        return []
    return [
        ScheduleTaskTool(deps.schedule_store, deps.default_email),
        ListSchedulesTool(deps.schedule_store),
        CancelScheduleTool(deps.schedule_store),
        GetScheduleResultTool(deps.schedule_store),
    ]


def _create_core_tools(deps: ToolDeps) -> list[Tool]:
    return [
        BashTool(working_dir=deps.working_dir),
        ReadFileTool(base_path=deps.working_dir),
        ExploreTool(),
        AskChoiceTool(),
        WriteScratchpadTool(),
        ReadScratchpadTool(),
        ListScratchpadTool(),
    ]


ToolFactory = Callable[[ToolDeps], list[Tool]]

TOOL_FACTORIES: list[ToolFactory] = [
    _create_notes_tools,
    _create_email_tools,
    _create_calendar_tools,
    _create_browser_tools,
    _create_web_tools,
    _create_memory_tools,
    _create_schedule_tools,
    _create_core_tools,
]
