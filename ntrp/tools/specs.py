from ntrp.integrations import ALL_INTEGRATIONS
from ntrp.skills.tool import UseSkillTool
from ntrp.tools.automation import (
    CreateAutomationTool,
    DeleteAutomationTool,
    GetAutomationResultTool,
    ListAutomationsTool,
    RunAutomationTool,
    UpdateAutomationTool,
)
from ntrp.tools.background import (
    BackgroundTool,
    CancelBackgroundTaskTool,
    GetBackgroundResultTool,
    ListBackgroundTasksTool,
)
from ntrp.tools.bash import BashTool
from ntrp.tools.calendar import (
    CalendarTool,
    CreateCalendarEventTool,
    DeleteCalendarEventTool,
    EditCalendarEventTool,
)
from ntrp.tools.core.base import Tool
from ntrp.tools.directives import SetDirectivesTool
from ntrp.tools.email import EmailsTool, ReadEmailTool, SendEmailTool
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
from ntrp.tools.notify import NotifyTool
from ntrp.tools.research import ResearchTool
from ntrp.tools.time import CurrentTimeTool

_BUILTIN_TOOLS: list[type[Tool]] = [
    BackgroundTool,
    BashTool,
    CancelBackgroundTaskTool,
    GetBackgroundResultTool,
    ListBackgroundTasksTool,
    ReadFileTool,
    ResearchTool,
    SetDirectivesTool,
    CurrentTimeTool,
    RememberTool,
    RecallTool,
    ForgetTool,
    NotesTool,
    ReadNoteTool,
    EditNoteTool,
    CreateNoteTool,
    DeleteNoteTool,
    MoveNoteTool,
    NotifyTool,
    SendEmailTool,
    ReadEmailTool,
    EmailsTool,
    CalendarTool,
    CreateCalendarEventTool,
    EditCalendarEventTool,
    DeleteCalendarEventTool,
    CreateAutomationTool,
    ListAutomationsTool,
    UpdateAutomationTool,
    DeleteAutomationTool,
    GetAutomationResultTool,
    RunAutomationTool,
    UseSkillTool,
]

ALL_TOOLS: list[type[Tool]] = [
    *_BUILTIN_TOOLS,
    *(tool for integration in ALL_INTEGRATIONS for tool in integration.tools),
]
