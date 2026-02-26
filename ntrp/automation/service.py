import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ntrp.automation.models import Automation, Trigger, build_trigger
from ntrp.automation.store import AutomationStore
from ntrp.llm.models import get_models

if TYPE_CHECKING:
    from ntrp.automation.scheduler import Scheduler


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
        return any(
            value is not None
            for value in (
                self.trigger_type,
                self.at,
                self.days,
                self.every,
                self.event_type,
                self.lead_minutes,
                self.start,
                self.end,
            )
        )

    @property
    def overrides(self) -> dict[str, str | int]:
        return {
            key: value
            for key, value in {
                "at": self.at,
                "days": self.days,
                "every": self.every,
                "event_type": self.event_type,
                "lead_minutes": self.lead_minutes,
                "start": self.start,
                "end": self.end,
            }.items()
            if value is not None
        }


class AutomationService:
    def __init__(
        self,
        store: AutomationStore,
        scheduler: "Scheduler",
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
        task = await self.store.get(task_id)
        if not task:
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
    ) -> Automation:
        task = await self.get(task_id)
        changes = self._build_metadata_changes(
            name=name,
            description=description,
            writable=writable,
            enabled=enabled,
            model=model,
            notifiers=notifiers,
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
        trigger_result = self._build_updated_trigger(task.trigger, trigger_patch)
        if trigger_result:
            changes["trigger"], changes["next_run_at"] = trigger_result

        updated = replace(task, **changes) if changes else task
        if changes:
            await self.store.update_metadata(updated)
        return updated

    async def create(
        self,
        name: str,
        description: str,
        trigger_type: str,
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
    ) -> Automation:
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

        if notifiers:
            self._validate_notifiers(notifiers)

        now = datetime.now(UTC)
        automation = Automation(
            task_id=secrets.token_hex(4),
            name=name,
            description=description,
            model=_normalize_and_validate_model(model),
            trigger=trigger,
            enabled=True,
            created_at=now,
            next_run_at=next_run,
            last_run_at=None,
            notifiers=notifiers or [],
            last_result=None,
            running_since=None,
            writable=writable,
        )
        await self.store.save(automation)
        return automation

    async def set_notifiers(self, task_id: str, notifier_names: list[str]) -> None:
        await self.get(task_id)
        self._validate_notifiers(notifier_names)
        await self.store.set_notifiers(task_id, notifier_names)

    async def delete(self, task_id: str) -> None:
        deleted = await self.store.delete(task_id)
        if not deleted:
            raise KeyError(f"Automation {task_id} not found")
