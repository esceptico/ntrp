"""Core integrations — builtin tools that ship with ntrp.

These are not user-facing integrations (no service_fields, no notifier_class,
no build). They exist to keep the tool registration flow uniform: all tools
belong to an Integration, including the ones ntrp ships out of the box.
"""

from ntrp.integrations.base import Integration
from ntrp.skills.tool import use_skill_tool
from ntrp.tools.automation import (
    create_automation_tool,
    delete_automation_tool,
    get_automation_result_tool,
    list_automations_tool,
    run_automation_tool,
    update_automation_tool,
)
from ntrp.tools.background import (
    background_tool,
    cancel_background_task_tool,
    get_background_result_tool,
    list_background_tasks_tool,
)
from ntrp.tools.bash import bash_tool
from ntrp.tools.deferred import load_tools_tool
from ntrp.tools.directives import set_directives_tool
from ntrp.tools.files import read_file_tool
from ntrp.tools.memory import forget_tool, recall_tool, remember_tool
from ntrp.tools.notify import notify_tool
from ntrp.tools.research import research_tool
from ntrp.tools.time import current_time_tool

SYSTEM = Integration(
    id="_system",
    label="System",
    tools={
        "bash": bash_tool,
        "read_file": read_file_tool,
        "current_time": current_time_tool,
        "research": research_tool,
        "load_tools": load_tools_tool,
    },
)

MEMORY_TOOLS = Integration(
    id="_memory",
    label="Memory",
    tools={"remember": remember_tool, "recall": recall_tool, "forget": forget_tool},
)

AUTOMATION = Integration(
    id="_automation",
    label="Automation",
    tools={
        "create_automation": create_automation_tool,
        "list_automations": list_automations_tool,
        "update_automation": update_automation_tool,
        "delete_automation": delete_automation_tool,
        "get_automation_result": get_automation_result_tool,
        "run_automation": run_automation_tool,
    },
)

BACKGROUND = Integration(
    id="_background",
    label="Background tasks",
    tools={
        "background": background_tool,
        "cancel_background_task": cancel_background_task_tool,
        "get_background_result": get_background_result_tool,
        "list_background_tasks": list_background_tasks_tool,
    },
)

NOTIFICATIONS = Integration(
    id="_notifications",
    label="Notifications",
    tools={"notify": notify_tool},
)

DIRECTIVES = Integration(
    id="_directives",
    label="Directives",
    tools={"set_directives": set_directives_tool},
)

SKILLS = Integration(
    id="_skills",
    label="Skills",
    tools={"use_skill": use_skill_tool},
)

CORE_INTEGRATIONS = [SYSTEM, MEMORY_TOOLS, AUTOMATION, BACKGROUND, NOTIFICATIONS, DIRECTIVES, SKILLS]
