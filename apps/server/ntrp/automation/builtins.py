from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime

from ntrp.automation.models import Automation
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import TimeTrigger, Trigger
from ntrp.constants import (
    BUILTIN_PATTERN_FINDER_DAILY_ID,
    BUILTIN_SKILL_INDUCER_DAILY_ID,
)
from ntrp.logging import get_logger

_logger = get_logger(__name__)


@dataclass
class BuiltinSpec:
    task_id: str
    name: str
    description: str
    triggers: list[Trigger]
    handler: str
    enabled: bool = True
    auto_approve: bool = False
    cooldown_minutes: int | None = None


BUILTINS = [
    BuiltinSpec(
        task_id=BUILTIN_PATTERN_FINDER_DAILY_ID,
        name="Pattern Finder Daily",
        description="Cluster recent memory episodes into observations and claims",
        triggers=[
            TimeTrigger(at="04:00", days="daily"),
        ],
        handler="pattern_finder_daily",
        auto_approve=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_SKILL_INDUCER_DAILY_ID,
        name="Skill Inducer Daily",
        description="Draft skill proposals from repeated toolable memory claims",
        triggers=[
            TimeTrigger(at="06:00", days="daily"),
        ],
        handler="skill_inducer_daily",
        auto_approve=True,
    ),
]

_CURRENT_BUILTIN_IDS = {spec.task_id for spec in BUILTINS}
_KNOWLEDGE_HANDLERS = {spec.handler for spec in BUILTINS}


async def seed_builtins(store: AutomationStore) -> None:
    for automation in await store.list_all():
        if (
            automation.builtin
            and automation.handler in _KNOWLEDGE_HANDLERS
            and automation.task_id not in _CURRENT_BUILTIN_IDS
        ):
            await store.delete(automation.task_id)
            _logger.info("Removed stale builtin automation: %s", automation.task_id)

    for spec in BUILTINS:
        existing = await store.get(spec.task_id)
        if existing:
            changes: dict = {}
            if existing.name != spec.name:
                changes["name"] = spec.name
            if existing.description != spec.description:
                changes["description"] = spec.description
            if existing.handler != spec.handler:
                changes["handler"] = spec.handler
            if existing.auto_approve != spec.auto_approve:
                changes["auto_approve"] = spec.auto_approve
            if existing.enabled != spec.enabled:
                changes["enabled"] = spec.enabled
            if existing.cooldown_minutes is None and spec.cooldown_minutes is not None:
                changes["cooldown_minutes"] = spec.cooldown_minutes
            spec_triggers = [{"type": t.type, **t.params()} for t in spec.triggers]
            existing_triggers = [{"type": t.type, **t.params()} for t in existing.triggers]
            time_triggers = [t for t in spec.triggers if isinstance(t, TimeTrigger)]
            if existing_triggers != spec_triggers:
                changes["triggers"] = spec.triggers
            if spec.enabled and existing.next_run_at is None and time_triggers:
                changes["next_run_at"] = time_triggers[0].next_run(datetime.now(UTC))
            if changes:
                updated = dc_replace(existing, **changes)
                await store.update_metadata(updated)
                _logger.info("Updated builtin automation defaults: %s", spec.name)
            continue

        now = datetime.now(UTC)
        time_triggers = [t for t in spec.triggers if isinstance(t, TimeTrigger)]
        automation = Automation(
            task_id=spec.task_id,
            name=spec.name,
            description=spec.description,
            model=None,
            triggers=spec.triggers,
            enabled=spec.enabled,
            created_at=now,
            next_run_at=time_triggers[0].next_run(now) if spec.enabled and time_triggers else None,
            last_run_at=None,
            last_result=None,
            running_since=None,
            auto_approve=spec.auto_approve,
            handler=spec.handler,
            builtin=True,
            cooldown_minutes=spec.cooldown_minutes,
        )
        await store.save(automation)
        _logger.info("Seeded builtin automation: %s", spec.name)
