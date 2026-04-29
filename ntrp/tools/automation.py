from typing import Literal

from pydantic import BaseModel, Field

from ntrp.automation.models import Automation
from ntrp.automation.triggers import build_trigger
from ntrp.events.triggers import EVENT_APPROACHING
from ntrp.tools.core import EmptyInput, ToolResult, tool
from ntrp.tools.core.context import ToolExecution
from ntrp.tools.core.types import ApprovalInfo

# --- Descriptions ---

CREATE_AUTOMATION_DESCRIPTION = (
    "Create an automation — a task the agent runs autonomously. "
    "Trigger types: 'time' (runs at a scheduled time or interval), 'event' (runs when an event fires, "
    f"e.g. '{EVENT_APPROACHING}'). "
    "Time triggers support two modes: schedule ('at' a specific time) or interval ('every' N hours/minutes). "
    "Optional model override per automation (falls back to default chat model when omitted). "
    "Read-only by default, set writable=true for memory/note writes."
)

LIST_AUTOMATIONS_DESCRIPTION = "List all automations with their trigger, status, and next run."

UPDATE_AUTOMATION_DESCRIPTION = (
    "Update an existing automation. Only provide the fields you want to change. "
    "Use list_automations to find IDs. "
    "Trigger fields (trigger_type, at, days, every, event_type, lead_minutes, start, end) are merged with "
    "the current trigger — only provide what should change. "
    "Set enabled=false to pause or enabled=true to resume."
)

DELETE_AUTOMATION_DESCRIPTION = "Delete an automation by its ID. Use list_automations to find IDs."

GET_AUTOMATION_RESULT_DESCRIPTION = "Get the last execution result of an automation by its ID."

RUN_AUTOMATION_DESCRIPTION = (
    "Trigger an immediate execution of an automation. "
    "The automation runs in the background — use get_automation_result to check the outcome. "
    "Use list_automations to find IDs."
)


# --- Helpers ---


def _triggers_label(triggers: list) -> str:
    return " | ".join(t.label for t in triggers)


def _format_automation_list(automations: list[Automation]) -> str:
    lines = []
    for a in automations:
        status = "enabled" if a.enabled else "disabled"
        next_run = a.next_run_at.strftime("%Y-%m-%d %H:%M") if a.next_run_at else "—"
        last_run = a.last_run_at.strftime("%Y-%m-%d %H:%M") if a.last_run_at else "never"
        label = a.name or a.description[:60]
        builtin_tag = " [builtin]" if a.builtin else ""

        lines.append(
            f"[{a.task_id}] {label}{builtin_tag}\n"
            f"  {_triggers_label(a.triggers)} · {status}\n"
            f"  next: {next_run} · last: {last_run}" + (f"\n  model: {a.model}" if a.model else "")
        )
    return "\n\n".join(lines)


# --- Input Models ---


class CreateAutomationInput(BaseModel):
    name: str = Field(description="Short human-readable label (e.g. 'morning briefing', 'pre-meeting prep')")
    description: str = Field(description="What the agent should do (natural language task)")
    model: str | None = Field(default=None, description="Optional agent model override for this automation.")
    trigger_type: Literal["time", "event"] = Field(
        description="Trigger type: 'time' (scheduled or interval), 'event' (reacts to events like calendar_approaching, new_email)",
    )
    at: str | None = Field(
        default=None,
        description="Time of day in HH:MM format (24h, local time). For schedule-based time triggers.",
    )
    days: str | None = Field(
        default=None,
        description="Which days to run: 'daily', 'weekdays', or comma-separated days (e.g. 'mon,wed,fri'). Omit for one-shot schedule or always-on interval.",
    )
    every: str | None = Field(
        default=None,
        description="Interval: e.g. '30m', '2h', '1h30m'. For interval-based time triggers. Cannot be combined with 'at'.",
    )
    start: str | None = Field(
        default=None,
        description="Start of active window in HH:MM (24h). Only for interval mode. Must be set with 'end'.",
    )
    end: str | None = Field(
        default=None,
        description="End of active window in HH:MM (24h). Only for interval mode. Must be set with 'start'.",
    )
    event_type: str | None = Field(
        default=None,
        description=f"Event type to react to (e.g. '{EVENT_APPROACHING}'). Required for trigger_type='event'",
    )
    lead_minutes: int | str | None = Field(
        default=None,
        description="For event_approaching only: trigger when event is this many minutes away (default 60).",
    )
    writable: bool = Field(default=False, description="Allow automation to write to memory and notes")


class UpdateAutomationInput(BaseModel):
    task_id: str = Field(description="The automation ID to update")
    name: str | None = Field(default=None, description="New name")
    description: str | None = Field(default=None, description="New task description")
    model: str | None = Field(default=None, description="New model override")
    trigger_type: Literal["time", "event"] | None = Field(
        default=None,
        description="New trigger type: 'time' or 'event'. Only set when switching trigger type.",
    )
    at: str | None = Field(default=None, description="New time of day HH:MM (24h). For schedule-based time triggers.")
    days: str | None = Field(
        default=None, description="New days: 'daily', 'weekdays', or comma-separated (e.g. 'mon,wed,fri')"
    )
    every: str | None = Field(
        default=None, description="New interval: e.g. '30m', '2h'. For interval-based time triggers."
    )
    start: str | None = Field(default=None, description="New active window start HH:MM (interval mode only)")
    end: str | None = Field(default=None, description="New active window end HH:MM (interval mode only)")
    event_type: str | None = Field(default=None, description=f"New event type (e.g. '{EVENT_APPROACHING}')")
    lead_minutes: int | str | None = Field(
        default=None,
        description="New lead time for event_approaching (minutes or duration like '2h30m')",
    )
    writable: bool | None = Field(default=None, description="Allow writes to memory and notes")
    enabled: bool | None = Field(default=None, description="Enable or disable the automation")


class DeleteAutomationInput(BaseModel):
    task_id: str = Field(description="The automation ID to delete")


class GetAutomationResultInput(BaseModel):
    task_id: str = Field(description="The automation ID to get results for")


class RunAutomationInput(BaseModel):
    task_id: str = Field(description="The automation ID to run")


# --- Tools ---


async def approve_create_automation(execution: ToolExecution, args: CreateAutomationInput) -> ApprovalInfo | None:
    try:
        trigger, next_run = build_trigger(
            args.trigger_type,
            at=args.at,
            days=args.days,
            every=args.every,
            event_type=args.event_type,
            lead_minutes=args.lead_minutes,
            start=args.start,
            end=args.end,
        )
    except ValueError:
        return None

    preview = f"Trigger: {_triggers_label([trigger])}"
    if next_run:
        preview += f"\nNext run: {next_run.strftime('%Y-%m-%d %H:%M')}"
    if args.model:
        preview += f"\nModel: {args.model}"
    if args.writable:
        preview += "\nWritable: yes"

    return ApprovalInfo(description=args.description, preview=preview, diff=None)


async def create_automation(execution: ToolExecution, args: CreateAutomationInput) -> ToolResult:
    try:
        automation = await execution.ctx.services["automation"].create(
            name=args.name,
            description=args.description,
            trigger_type=args.trigger_type,
            at=args.at,
            days=args.days,
            every=args.every,
            event_type=args.event_type,
            lead_minutes=args.lead_minutes,
            writable=args.writable,
            start=args.start,
            end=args.end,
            model=args.model,
        )
    except ValueError as e:
        return ToolResult(content=f"Error: {e}", preview="Failed", is_error=True)

    lines = [
        f"Created automation: {automation.description}",
        f"ID: {automation.task_id}",
        f"Trigger: {_triggers_label(automation.triggers)}",
    ]
    if automation.model:
        lines.append(f"Model: {automation.model}")
    if automation.next_run_at:
        lines.append(f"Next run: {automation.next_run_at.strftime('%Y-%m-%d %H:%M')}")

    return ToolResult(content="\n".join(lines), preview=f"Created ({automation.task_id})")


async def list_automations(execution: ToolExecution, args: EmptyInput) -> ToolResult:
    automations = await execution.ctx.services["automation"].list_all()
    if not automations:
        return ToolResult(content="No automations.", preview="0 automations")

    content = _format_automation_list(automations)
    return ToolResult(content=content, preview=f"{len(automations)} automations")


async def approve_update_automation(execution: ToolExecution, args: UpdateAutomationInput) -> ApprovalInfo | None:
    try:
        automation = await execution.ctx.services["automation"].get(args.task_id)
    except KeyError:
        return None

    changes = []
    fields = {
        "name": args.name,
        "description": args.description,
        "enabled": args.enabled,
        "writable": args.writable,
        "model": args.model,
        "trigger_type": args.trigger_type,
        "at": args.at,
        "days": args.days,
        "every": args.every,
        "event_type": args.event_type,
        "lead_minutes": args.lead_minutes,
        "start": args.start,
        "end": args.end,
    }
    for key, value in fields.items():
        if value is not None:
            changes.append(f"{key}: {value}")

    label = automation.name or automation.description[:60]
    return ApprovalInfo(
        description=f"Update: {label} ({args.task_id})",
        preview="\n".join(changes) if changes else "No changes",
        diff=None,
    )


async def update_automation(execution: ToolExecution, args: UpdateAutomationInput) -> ToolResult:
    try:
        automation = await execution.ctx.services["automation"].update(
            args.task_id,
            name=args.name,
            description=args.description,
            model=args.model,
            trigger_type=args.trigger_type,
            at=args.at,
            days=args.days,
            every=args.every,
            event_type=args.event_type,
            lead_minutes=args.lead_minutes,
            start=args.start,
            end=args.end,
            writable=args.writable,
            enabled=args.enabled,
        )
    except KeyError:
        return ToolResult(content=f"Error: automation '{args.task_id}' not found", preview="Not found", is_error=True)
    except ValueError as e:
        return ToolResult(content=f"Error: {e}", preview="Invalid update", is_error=True)

    label = automation.name or automation.description[:60]
    lines = [
        f"Updated automation: {label}",
        f"ID: {automation.task_id}",
        f"Trigger: {_triggers_label(automation.triggers)}",
        f"Enabled: {automation.enabled}",
    ]
    if automation.next_run_at:
        lines.append(f"Next run: {automation.next_run_at.strftime('%Y-%m-%d %H:%M')}")

    return ToolResult(content="\n".join(lines), preview=f"Updated ({automation.task_id})")


async def approve_delete_automation(execution: ToolExecution, args: DeleteAutomationInput) -> ApprovalInfo | None:
    try:
        automation = await execution.ctx.services["automation"].get(args.task_id)
    except KeyError:
        return None
    return ApprovalInfo(description=f"Delete: {automation.description}", preview=None, diff=None)


async def delete_automation(execution: ToolExecution, args: DeleteAutomationInput) -> ToolResult:
    try:
        automation = await execution.ctx.services["automation"].get(args.task_id)
        await execution.ctx.services["automation"].delete(args.task_id)
    except KeyError:
        return ToolResult(content=f"Error: automation '{args.task_id}' not found", preview="Not found", is_error=True)
    except ValueError as e:
        return ToolResult(content=f"Error: {e}", preview="Cannot delete", is_error=True)

    return ToolResult(content=f"Deleted: {automation.description} ({args.task_id})", preview="Deleted")


async def get_automation_result(execution: ToolExecution, args: GetAutomationResultInput) -> ToolResult:
    try:
        automation = await execution.ctx.services["automation"].get(args.task_id)
    except KeyError:
        return ToolResult(content=f"Error: automation '{args.task_id}' not found", preview="Not found", is_error=True)

    if not automation.last_result:
        last_run = automation.last_run_at.strftime("%Y-%m-%d %H:%M") if automation.last_run_at else "never"
        return ToolResult(
            content=f"No result yet for '{automation.description}' (last run: {last_run})",
            preview="No result",
        )

    header = (
        f"Automation: {automation.description}\n"
        f"Last run: {automation.last_run_at.strftime('%Y-%m-%d %H:%M') if automation.last_run_at else '—'}\n"
        f"---\n"
    )
    return ToolResult(content=header + automation.last_result, preview=f"Result ({automation.task_id})")


async def approve_run_automation(execution: ToolExecution, args: RunAutomationInput) -> ApprovalInfo | None:
    try:
        automation = await execution.ctx.services["automation"].get(args.task_id)
    except KeyError:
        return None
    return ApprovalInfo(
        description=f"Run now: {automation.name or automation.description[:60]}",
        preview=None,
        diff=None,
    )


async def run_automation(execution: ToolExecution, args: RunAutomationInput) -> ToolResult:
    try:
        await execution.ctx.services["automation"].run_now(args.task_id)
    except KeyError:
        return ToolResult(content=f"Error: automation '{args.task_id}' not found", preview="Not found", is_error=True)
    except RuntimeError as e:
        return ToolResult(content=f"Error: {e}", preview="Unavailable", is_error=True)

    return ToolResult(
        content=f"Automation {args.task_id} started. Use get_automation_result to check the outcome.",
        preview="Started",
    )


create_automation_tool = tool(
    display_name="CreateAutomation",
    description=CREATE_AUTOMATION_DESCRIPTION,
    input_model=CreateAutomationInput,
    mutates=True,
    requires={"automation"},
    approval=approve_create_automation,
    execute=create_automation,
)

list_automations_tool = tool(
    display_name="ListAutomations",
    description=LIST_AUTOMATIONS_DESCRIPTION,
    requires={"automation"},
    execute=list_automations,
)

update_automation_tool = tool(
    display_name="UpdateAutomation",
    description=UPDATE_AUTOMATION_DESCRIPTION,
    input_model=UpdateAutomationInput,
    mutates=True,
    requires={"automation"},
    approval=approve_update_automation,
    execute=update_automation,
)

delete_automation_tool = tool(
    display_name="DeleteAutomation",
    description=DELETE_AUTOMATION_DESCRIPTION,
    input_model=DeleteAutomationInput,
    mutates=True,
    requires={"automation"},
    approval=approve_delete_automation,
    execute=delete_automation,
)

get_automation_result_tool = tool(
    display_name="AutomationResult",
    description=GET_AUTOMATION_RESULT_DESCRIPTION,
    input_model=GetAutomationResultInput,
    requires={"automation"},
    execute=get_automation_result,
)

run_automation_tool = tool(
    display_name="RunAutomation",
    description=RUN_AUTOMATION_DESCRIPTION,
    input_model=RunAutomationInput,
    mutates=True,
    requires={"automation"},
    approval=approve_run_automation,
    execute=run_automation,
)
