"""Core integrations — builtin tools that ship with ntrp.

These are not user-facing integrations (no service_fields, no notifier_class,
no build). They exist to keep the tool registration flow uniform: all tools
belong to an Integration, including the ones ntrp ships out of the box.
"""

from ntrp.integrations.base import Integration
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
from ntrp.tools.directives import SetDirectivesTool
from ntrp.tools.files import ReadFileTool
from ntrp.tools.memory import ForgetTool, RecallTool, RememberTool
from ntrp.tools.notify import NotifyTool
from ntrp.tools.research import ResearchTool
from ntrp.tools.time import CurrentTimeTool


SYSTEM = Integration(
    id="_system",
    label="System",
    tools=[BashTool, ReadFileTool, CurrentTimeTool, SetDirectivesTool, NotifyTool, ResearchTool],
)

MEMORY_TOOLS = Integration(
    id="_memory",
    label="Memory",
    tools=[RememberTool, RecallTool, ForgetTool],
)

AUTOMATION = Integration(
    id="_automation",
    label="Automation",
    tools=[
        CreateAutomationTool,
        ListAutomationsTool,
        UpdateAutomationTool,
        DeleteAutomationTool,
        GetAutomationResultTool,
        RunAutomationTool,
    ],
)

BACKGROUND = Integration(
    id="_background",
    label="Background tasks",
    tools=[BackgroundTool, CancelBackgroundTaskTool, GetBackgroundResultTool, ListBackgroundTasksTool],
)

SKILLS = Integration(
    id="_skills",
    label="Skills",
    tools=[UseSkillTool],
)

CORE_INTEGRATIONS = [SYSTEM, MEMORY_TOOLS, AUTOMATION, BACKGROUND, SKILLS]
