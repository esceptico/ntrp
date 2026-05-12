"""Core integrations — builtin tools that ship with ntrp.

These are not user-facing integrations (no service_fields, no notifier_class,
no build). They exist to keep the tool registration flow uniform: all tools
belong to an Integration, including the ones ntrp ships out of the box.
"""

from ntrp.integrations.base import Integration
from ntrp.skills.tool import create_skill_tool, use_skill_tool
from ntrp.tools.automation import (
    create_automation_tool,
    create_loop_tool,
    delete_automation_tool,
    get_automation_result_tool,
    list_automations_tool,
    loop_done_tool,
    run_automation_tool,
    schedule_wakeup_tool,
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
from ntrp.tools.files import (
    edit_file_tool,
    find_files_tool,
    list_files_tool,
    read_file_tool,
    search_text_tool,
    write_file_tool,
)
from ntrp.tools.memory import forget_tool, recall_tool, remember_tool
from ntrp.tools.notify import notify_tool
from ntrp.tools.research import research_tool
from ntrp.tools.sessions import list_recent_sessions_tool, read_session_tool
from ntrp.tools.time import current_time_tool

SYSTEM = Integration(
    id="_system",
    label="System",
    tools={
        "bash": bash_tool,
        "read_file": read_file_tool,
        "list_files": list_files_tool,
        "find_files": find_files_tool,
        "search_text": search_text_tool,
        "write_file": write_file_tool,
        "edit_file": edit_file_tool,
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
        "create_loop": create_loop_tool,
        "schedule_wakeup": schedule_wakeup_tool,
        "loop_done": loop_done_tool,
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
    tools={
        "use_skill": use_skill_tool,
        "create_skill": create_skill_tool,
    },
)

SESSIONS = Integration(
    id="_sessions",
    label="Sessions",
    tools={
        "list_recent_sessions": list_recent_sessions_tool,
        "read_session": read_session_tool,
    },
)

CORE_INTEGRATIONS = [SYSTEM, MEMORY_TOOLS, AUTOMATION, BACKGROUND, NOTIFICATIONS, DIRECTIVES, SKILLS, SESSIONS]
