from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ntrp.automation.service import AutomationService
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.tool import UseSkillTool
from ntrp.tools.automation import (
    CreateAutomationTool,
    DeleteAutomationTool,
    GetAutomationResultTool,
    ListAutomationsTool,
    RunAutomationTool,
    UpdateAutomationTool,
)
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
from ntrp.tools.time import CurrentTimeTool
from ntrp.tools.web import WebFetchTool, WebSearchTool


@dataclass(frozen=True)
class ToolDeps:
    search_index: Any | None = None
    automation_service: AutomationService | None = None
    skill_registry: SkillRegistry | None = None
    notifier_service: Any | None = None


def _create_notes_tools(deps: ToolDeps) -> list[Tool]:
    return [
        NotesTool(search_index=deps.search_index),
        ReadNoteTool(),
        EditNoteTool(),
        CreateNoteTool(),
        DeleteNoteTool(),
        MoveNoteTool(),
    ]


def _create_email_tools(deps: ToolDeps) -> list[Tool]:
    return [
        SendEmailTool(),
        ReadEmailTool(),
        EmailsTool(),
    ]


def _create_calendar_tools(deps: ToolDeps) -> list[Tool]:
    return [
        CalendarTool(),
        CreateCalendarEventTool(),
        EditCalendarEventTool(),
        DeleteCalendarEventTool(),
    ]


def _create_browser_tools(deps: ToolDeps) -> list[Tool]:
    return [
        BrowserTool(),
    ]


def _create_web_tools(deps: ToolDeps) -> list[Tool]:
    return [
        WebSearchTool(),
        WebFetchTool(),
    ]


def _create_memory_tools(deps: ToolDeps) -> list[Tool]:
    return [
        RememberTool(),
        RecallTool(),
        ForgetTool(),
    ]


def _create_automation_tools(deps: ToolDeps) -> list[Tool]:
    if not deps.automation_service:
        return []
    svc = deps.automation_service
    ns = deps.notifier_service
    return [
        CreateAutomationTool(svc, notifier_service=ns),
        ListAutomationsTool(svc),
        UpdateAutomationTool(svc, notifier_service=ns),
        DeleteAutomationTool(svc),
        GetAutomationResultTool(svc),
        RunAutomationTool(svc),
    ]


def _create_core_tools(deps: ToolDeps) -> list[Tool]:
    return [
        BashTool(),
        ReadFileTool(),
        ExploreTool(),
        SetDirectivesTool(),
        CurrentTimeTool(),
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
    _create_automation_tools,
    _create_core_tools,
    _create_skill_tools,
]
