import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from ntrp.automation.models import Automation
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import TimeTrigger, Trigger, build_trigger, parse_one
from ntrp.llm.models import get_models


def _normalize_and_validate_model(model: str | None) -> str | None:
    if model is None:
        return None
    normalized = model.strip()
    if not normalized:
        return None
    available = get_models()
    if normalized not in available:
        raise ValueError(f"Unknown model: {normalized}")
    return normalized


@dataclass(frozen=True)
class TriggerPatch:
    trigger_type: str | None = None
    at: str | None = None
    days: str | None = None
    every: str | None = None
    event_type: str | None = None
    lead_minutes: int | str | None = None
    start: str | None = None
    end: str | None = None

    @property
    def has_changes(self) -> bool:
        return any(v is not None for v in asdict(self).values())

    @property
    def overrides(self) -> dict[str, str | int]:
        d = asdict(self)
        d.pop("trigger_type", None)
        return {k: v for k, v in d.items() if v is not None}


class AutomationService:
    def __init__(
        self,
        store: AutomationStore,
        scheduler: Scheduler,
        get_notifiers: Callable[[], dict[str, Any]],
    ):
        self.store = store
        self.scheduler = scheduler
        self._get_notifiers = get_notifiers

    @property
    def is_running(self) -> bool:
        return self.scheduler.is_running

    async def list_all(self) -> list[Automation]:
        return await self.store.list_all()

    async def get(self, task_id: str) -> Automation:
        if not (task := await self.store.get(task_id)):
            raise KeyError(f"Automation {task_id} not found")
        return task

    async def toggle_enabled(self, task_id: str) -> bool:
        task = await self.get(task_id)
        new_enabled = not task.enabled
        await self.store.set_enabled(task_id, new_enabled)
        return new_enabled

    async def toggle_writable(self, task_id: str) -> bool:
        task = await self.get(task_id)
        new_writable = not task.writable
        await self.store.set_writable(task_id, new_writable)
        return new_writable

    async def run_now(self, task_id: str) -> None:
        if not self.scheduler.is_running:
            raise RuntimeError("Scheduler not running")
        await self.get(task_id)
        self.scheduler.schedule_run(task_id)

    def _validate_notifiers(self, notifiers: list[str]) -> None:
        available = self._get_notifiers()
        unknown = set(notifiers) - set(available)
        if unknown:
            raise ValueError(f"Unknown notifier(s): {', '.join(sorted(unknown))}")

    def _build_metadata_changes(
        self,
        *,
        name: str | None,
        description: str | None,
        writable: bool | None,
        enabled: bool | None,
        model: str | None,
        notifiers: list[str] | None,
        cooldown_minutes: int | None = None,
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if name is not None:
            changes["name"] = name
        if description is not None:
            changes["description"] = description
        if writable is not None:
            changes["writable"] = writable
        if enabled is not None:
            changes["enabled"] = enabled
        if model is not None:
            changes["model"] = _normalize_and_validate_model(model)
        if notifiers is not None:
            self._validate_notifiers(notifiers)
            changes["notifiers"] = notifiers
        if cooldown_minutes is not None:
            changes["cooldown_minutes"] = cooldown_minutes
        return changes

    @staticmethod
    def _build_updated_trigger(current: Trigger, patch: TriggerPatch) -> tuple[Trigger, datetime | None] | None:
        if not patch.has_changes:
            return None

        effective_type = patch.trigger_type or current.type

        # Keep current params when staying in same type; blank slate on type switch.
        base = current.params() if effective_type == current.type else {}
        merged = {**base, **patch.overrides}

        # Schedule (at) and interval (every) are mutually exclusive within time triggers.
        if effective_type == "time":
            if patch.every is not None:
                merged.pop("at", None)
            elif patch.at is not None:
                for k in ("every", "start", "end"):
                    merged.pop(k, None)
        elif effective_type == "event":
            time_fields = {"at", "every", "days", "start", "end"} & patch.overrides.keys()
            if time_fields:
                raise ValueError(f"Time fields ({', '.join(sorted(time_fields))}) cannot be set on an event trigger")

        return build_trigger(effective_type, **{k: v for k, v in merged.items() if v is not None})

    async def update(
        self,
        task_id: str,
        name: str | None = None,
        description: str | None = None,
        trigger_type: str | None = None,
        at: str | None = None,
        days: str | None = None,
        every: str | None = None,
        event_type: str | None = None,
        lead_minutes: int | str | None = None,
        start: str | None = None,
        end: str | None = None,
        notifiers: list[str] | None = None,
        writable: bool | None = None,
        enabled: bool | None = None,
        model: str | None = None,
        triggers: list[dict] | None = None,
        cooldown_minutes: int | None = None,
    ) -> Automation:
        task = await self.get(task_id)
        changes = self._build_metadata_changes(
            name=name,
            description=description,
            writable=writable,
            enabled=enabled,
            model=model,
            notifiers=notifiers,
            cooldown_minutes=cooldown_minutes,
        )

        trigger_patch = TriggerPatch(
            trigger_type=trigger_type,
            at=at,
            days=days,
            every=every,
            event_type=event_type,
            lead_minutes=lead_minutes,
            start=start,
            end=end,
        )

        # Full triggers list replacement takes precedence over field-level patching
        if triggers:
            parsed_triggers = [parse_one(t) for t in triggers]
            time_triggers = [t for t in parsed_triggers if isinstance(t, TimeTrigger)]
            changes["triggers"] = parsed_triggers
            changes["next_run_at"] = time_triggers[0].next_run(datetime.now(UTC)) if time_triggers else None
        else:
            # For single-trigger patching via field params
            if task.triggers:
                current_trigger = task.triggers[0]
            else:
                current_trigger = TimeTrigger(at="00:00")

            trigger_result = self._build_updated_trigger(current_trigger, trigger_patch)
            if trigger_result:
                new_trigger, new_next_run = trigger_result
                changes["triggers"] = [new_trigger]
                changes["next_run_at"] = new_next_run

        updated = replace(task, **changes) if changes else task
        if changes:
            await self.store.update_metadata(updated)
        return updated

    async def create(
        self,
        name: str,
        description: str,
        trigger_type: str | None = None,
        at: str | None = None,
        days: str | None = None,
        every: str | None = None,
        event_type: str | None = None,
        lead_minutes: int | str | None = None,
        notifiers: list[str] | None = None,
        writable: bool = False,
        start: str | None = None,
        end: str | None = None,
        model: str | None = None,
        triggers: list[dict] | None = None,
        cooldown_minutes: int | None = None,
    ) -> Automation:
        if triggers:
            parsed_triggers = [parse_one(t) for t in triggers]
            time_triggers = [t for t in parsed_triggers if isinstance(t, TimeTrigger)]
            next_run = time_triggers[0].next_run(datetime.now(UTC)) if time_triggers else None
        elif trigger_type:
            trigger, next_run = build_trigger(
                trigger_type,
                at=at,
                days=days,
                every=every,
                event_type=event_type,
                lead_minutes=lead_minutes,
                start=start,
                end=end,
            )
            parsed_triggers = [trigger]
        else:
            raise ValueError("Either 'triggers' list or 'trigger_type' is required")

        if notifiers:
            self._validate_notifiers(notifiers)

        now = datetime.now(UTC)
        automation = Automation(
            task_id=secrets.token_hex(4),
            name=name,
            description=description,
            model=_normalize_and_validate_model(model),
            triggers=parsed_triggers,
            enabled=True,
            created_at=now,
            next_run_at=next_run,
            last_run_at=None,
            notifiers=notifiers or [],
            last_result=None,
            running_since=None,
            writable=writable,
            cooldown_minutes=cooldown_minutes,
        )
        await self.store.save(automation)
        return automation

    async def set_notifiers(self, task_id: str, notifier_names: list[str]) -> None:
        await self.get(task_id)
        self._validate_notifiers(notifier_names)
        await self.store.set_notifiers(task_id, notifier_names)

    async def delete(self, task_id: str) -> None:
        task = await self.get(task_id)
        if task.builtin:
            raise ValueError(f"Cannot delete builtin automation '{task.name}'")
        deleted = await self.store.delete(task_id)
        if not deleted:
            raise KeyError(f"Automation {task_id} not found")
