from ntrp.skills.tool import UseSkillTool
from ntrp.tools.automation import (
    CreateAutomationTool,
    DeleteAutomationTool,
    GetAutomationResultTool,
    ListAutomationsTool,
    RunAutomationTool,
    UpdateAutomationTool,
)
from ntrp.tools.bash import BashTool, CancelBackgroundTaskTool, ListBackgroundTasksTool
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

ALL_TOOLS: list[type[Tool]] = [
    BashTool,
    CancelBackgroundTaskTool,
    ListBackgroundTasksTool,
    ReadFileTool,
    ExploreTool,
    SetDirectivesTool,
    CurrentTimeTool,
    WebSearchTool,
    WebFetchTool,
    BrowserTool,
    RememberTool,
    RecallTool,
    ForgetTool,
    NotesTool,
    ReadNoteTool,
    EditNoteTool,
    CreateNoteTool,
    DeleteNoteTool,
    MoveNoteTool,
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
