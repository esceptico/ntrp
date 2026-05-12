from datetime import UTC, datetime, timedelta
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
        description="Interval: e.g. '30m', '2h', '1h30m', '1d', '2d12h'. For interval-based time triggers. Cannot be combined with 'at'.",
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
    writable: bool = Field(default=False, description="Allow automation to write to memory and connected services")


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
        default=None, description="New interval: e.g. '30m', '2h', '1d', '2d12h'. For interval-based time triggers."
    )
    start: str | None = Field(default=None, description="New active window start HH:MM (interval mode only)")
    end: str | None = Field(default=None, description="New active window end HH:MM (interval mode only)")
    event_type: str | None = Field(default=None, description=f"New event type (e.g. '{EVENT_APPROACHING}')")
    lead_minutes: int | str | None = Field(
        default=None,
        description="New lead time for event_approaching (minutes or duration like '2h30m')",
    )
    writable: bool | None = Field(default=None, description="Allow writes to memory and connected services")
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

    # Multi-line preview the frontend can render as a structured card.
    # Order is intentional: name first, then schedule (what people scan
    # for), then writable warning, then the full prompt body so reviewers
    # can read what'll actually run without expanding anything.
    lines: list[str] = [f"Name: {args.name}", f"Schedule: {_triggers_label([trigger])}"]
    if next_run:
        lines.append(f"Next run: {next_run.strftime('%Y-%m-%d %H:%M')}")
    if args.model:
        lines.append(f"Model: {args.model}")
    if args.writable:
        lines.append("Writable: yes (can write to memory + services)")
    lines.append("")
    lines.append("Prompt:")
    lines.append(args.description)

    return ApprovalInfo(
        description=f"Create automation: {args.name}",
        preview="\n".join(lines),
        diff=None,
    )


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


# --- Self-paced loop tools ---

SCHEDULE_WAKEUP_DESCRIPTION = (
    "Self-paced loop control: schedule the next iteration of THIS loop. "
    "Only usable when the current run was triggered by a loop. "
    "Pass delay_seconds (minimum 60). Use this to back off when the watched condition "
    "isn't ready yet (e.g. 'check again in 5 minutes') or to poll more aggressively "
    "near a transition. If you call this multiple times in one iteration the last "
    "call wins."
)

LOOP_DONE_DESCRIPTION = (
    "Self-paced loop control: mark THIS loop as done and stop further iterations. "
    "Only usable when the current run was triggered by a loop. "
    "Call this when the loop's goal has been reached (e.g. CI turned green, deploy "
    "succeeded, condition met). Pass a short reason so the user understands why "
    "the loop stopped."
)


class ScheduleWakeupInput(BaseModel):
    delay_seconds: int = Field(
        description="Seconds until the next iteration. Minimum 60.",
        ge=60,
    )


class LoopDoneInput(BaseModel):
    reason: str = Field(description="Why the loop is stopping. Shown to the user.")


def _loop_task_id_or_error(execution: ToolExecution) -> tuple[str | None, ToolResult | None]:
    task_id = execution.ctx.run.loop_task_id
    if not task_id:
        return None, ToolResult(
            content="This tool is only available inside a loop iteration.",
            preview="Not a loop",
            is_error=True,
        )
    return task_id, None


async def schedule_wakeup(execution: ToolExecution, args: ScheduleWakeupInput) -> ToolResult:
    task_id, err = _loop_task_id_or_error(execution)
    if err:
        return err
    svc = execution.ctx.services.get("automation")
    if svc is None:
        return ToolResult(content="Automation service unavailable.", preview="Unavailable", is_error=True)
    next_run = datetime.now(UTC) + timedelta(seconds=args.delay_seconds)
    await svc.store.set_next_run(task_id, next_run)
    return ToolResult(
        content=f"Next iteration scheduled in {args.delay_seconds}s ({next_run.isoformat()}).",
        preview=f"Wake in {args.delay_seconds}s",
    )


async def loop_done(execution: ToolExecution, args: LoopDoneInput) -> ToolResult:
    task_id, err = _loop_task_id_or_error(execution)
    if err:
        return err
    svc = execution.ctx.services.get("automation")
    if svc is None:
        return ToolResult(content="Automation service unavailable.", preview="Unavailable", is_error=True)
    await svc.store.set_enabled(task_id, False)
    return ToolResult(
        content=f"Loop stopped: {args.reason}",
        preview="Loop done",
    )


schedule_wakeup_tool = tool(
    display_name="ScheduleWakeup",
    description=SCHEDULE_WAKEUP_DESCRIPTION,
    input_model=ScheduleWakeupInput,
    mutates=True,
    requires={"automation"},
    execute=schedule_wakeup,
)

loop_done_tool = tool(
    display_name="LoopDone",
    description=LOOP_DONE_DESCRIPTION,
    input_model=LoopDoneInput,
    mutates=True,
    requires={"automation"},
    execute=loop_done,
)


# --- create_loop ---

CREATE_LOOP_DESCRIPTION = (
    "Create a loop — a repeating prompt scoped to the CURRENT chat session. "
    "Each iteration posts the prompt as a new user turn in this chat. "
    "Use this when the user wants to monitor or babysit something on a cadence: "
    "'watch CI', 'check the deploy every 5 minutes', 'keep an eye on X'. "
    "Two modes: "
    "(a) fixed interval: pass 'every' (e.g. '5m', '1h', '2h30m'). "
    "(b) self-paced: pass 'every' as the initial cadence; inside each iteration, "
    "the agent calls schedule_wakeup to adjust the next interval, or loop_done "
    "to terminate when the goal is reached. "
    "Optional max_iterations caps the loop. "
    "Optional stop_when is a natural-language predicate the agent checks each iteration."
)


class CreateLoopInput(BaseModel):
    prompt: str = Field(
        description="What the loop should do on each iteration. Posted as a user message into this chat. Stand-alone.",
        min_length=1,
    )
    every: str = Field(
        description="Initial interval between iterations: '5m', '30m', '1h', '2h30m', '1d'. Minimum 1 minute.",
        min_length=1,
    )
    max_iterations: int | None = Field(
        default=None,
        description="Optional hard cap on how many times the loop runs.",
        ge=1,
    )
    stop_when: str | None = Field(
        default=None,
        description="Optional natural-language predicate. Each iteration checks if this is met; if so, call loop_done.",
    )
    max_age_days: int | None = Field(
        default=None,
        description="Optional hard cap in days from creation. After this many days, the loop disables itself on the next fire even if max_iterations hasn't been hit.",
        ge=1,
    )


async def approve_create_loop(execution: ToolExecution, args: CreateLoopInput) -> ApprovalInfo | None:
    lines = [f"Every: {args.every}", ""]
    if args.max_iterations:
        lines.insert(1, f"Max iterations: {args.max_iterations}")
    if args.max_age_days:
        lines.insert(-1, f"Auto-expires: after {args.max_age_days} day(s)")
    if args.stop_when:
        lines.insert(-1, f"Stop when: {args.stop_when}")
    lines.append("Prompt:")
    lines.append(args.prompt)
    return ApprovalInfo(
        description="Create loop in this chat",
        preview="\n".join(lines),
        diff=None,
    )


async def create_loop(execution: ToolExecution, args: CreateLoopInput) -> ToolResult:
    session_id = execution.ctx.session_id
    if not session_id:
        return ToolResult(content="No active session.", preview="No session", is_error=True)
    svc = execution.ctx.services.get("automation")
    if svc is None:
        return ToolResult(content="Automation service unavailable.", preview="Unavailable", is_error=True)
    try:
        loop = await svc.create_loop(
            session_id=session_id,
            prompt=args.prompt,
            every=args.every,
            max_iterations=args.max_iterations,
            stop_when=args.stop_when,
            max_age_days=args.max_age_days,
        )
    except ValueError as e:
        return ToolResult(content=f"Error: {e}", preview="Failed", is_error=True)

    lines = [
        f"Created loop {loop.task_id}",
        f"Every: {args.every}",
        f"Prompt: {loop.loop_prompt}",
    ]
    if loop.max_iterations:
        lines.append(f"Max iterations: {loop.max_iterations}")
    if loop.max_age_days:
        lines.append(f"Auto-expires: after {loop.max_age_days} day(s)")
    if loop.stop_when:
        lines.append(f"Stop when: {loop.stop_when}")
    if loop.next_run_at:
        lines.append(f"First run: {loop.next_run_at.strftime('%Y-%m-%d %H:%M')}")
    return ToolResult(content="\n".join(lines), preview=f"Loop · every {args.every}")


create_loop_tool = tool(
    display_name="CreateLoop",
    description=CREATE_LOOP_DESCRIPTION,
    input_model=CreateLoopInput,
    mutates=True,
    requires={"automation"},
    approval=approve_create_loop,
    execute=create_loop,
)
