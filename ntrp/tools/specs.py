from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ntrp.memory.facts import FactMemory
from ntrp.schedule.store import ScheduleStore
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.tool import UseSkillTool
from ntrp.sources.base import BrowserSource, CalendarSource, EmailSource, NotesSource, Source, WebSearchSource
from ntrp.tools.ask_choice import AskChoiceTool
from ntrp.tools.bash import BashTool
from ntrp.tools.browser import BrowserTool
from ntrp.tools.calendar import (
    CalendarTool,
    CreateCalendarEventTool,
    DeleteCalendarEventTool,
    EditCalendarEventTool,
)
from ntrp.tools.core.base import Tool
from ntrp.tools.directives import SetDirectivesTool
from ntrp.tools.email import EmailsTool, ReadEmailTool, SendEmailTool
from ntrp.tools.explore import ExploreTool
from ntrp.tools.files import ReadFileTool
from ntrp.tools.memory import ForgetTool, RecallTool, RememberTool
from ntrp.tools.notes import (
    CreateNoteTool,
    DeleteNoteTool,
    EditNoteTool,
    MoveNoteTool,
    NotesTool,
    ReadNoteTool,
)
from ntrp.tools.schedule import CancelScheduleTool, GetScheduleResultTool, ListSchedulesTool, ScheduleTaskTool
from ntrp.tools.web import WebFetchTool, WebSearchTool


@dataclass(frozen=True)
class ToolDeps:
    sources: dict[str, Source]
    memory: FactMemory | None = None
    search_index: Any | None = None
    schedule_store: ScheduleStore | None = None
    default_notifiers: list[str] | None = None
    working_dir: str | None = None
    skill_registry: SkillRegistry | None = None


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
        NotesTool(source, search_index=deps.search_index),
        ReadNoteTool(source),
        EditNoteTool(source),
        CreateNoteTool(source),
        DeleteNoteTool(source),
        MoveNoteTool(source),
    ]


def _create_email_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, EmailSource)
    if not source:
        return []
    return [
        SendEmailTool(source),
        ReadEmailTool(source),
        EmailsTool(source),
    ]


def _create_calendar_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, CalendarSource)
    if not source:
        return []
    return [
        CalendarTool(source),
        CreateCalendarEventTool(source),
        EditCalendarEventTool(source),
        DeleteCalendarEventTool(source),
    ]


def _create_browser_tools(deps: ToolDeps) -> list[Tool]:
    source = _find_source(deps.sources, BrowserSource)
    if not source:
        return []
    return [
        BrowserTool(source),
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
        ScheduleTaskTool(deps.schedule_store, deps.default_notifiers),
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
        SetDirectivesTool(),
    ]


def _create_skill_tools(deps: ToolDeps) -> list[Tool]:
    if not deps.skill_registry:
        return []
    return [UseSkillTool(deps.skill_registry)]


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
    _create_skill_tools,
]
