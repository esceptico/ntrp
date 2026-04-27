from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime

from ntrp.automation.models import Automation
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import CountTrigger, IdleTrigger, TimeTrigger, Trigger
from ntrp.constants import (
    BUILTIN_CHAT_EXTRACTION_ID,
    BUILTIN_CONSOLIDATION_ID,
    DEFAULT_CONSOLIDATION_COOLDOWN_MINUTES,
    DEFAULT_CONSOLIDATION_IDLE_MINUTES,
    DEFAULT_EXTRACTION_IDLE_MINUTES,
    EXTRACTION_EVERY_N_TURNS,
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
    writable: bool = False
    cooldown_minutes: int | None = None


BUILTINS = [
    BuiltinSpec(
        task_id=BUILTIN_CHAT_EXTRACTION_ID,
        name="Chat Extraction",
        description="Extract durable facts from conversations",
        triggers=[
            CountTrigger(every_n=EXTRACTION_EVERY_N_TURNS),
            IdleTrigger(idle_minutes=DEFAULT_EXTRACTION_IDLE_MINUTES),
        ],
        handler="chat_extraction",
        cooldown_minutes=DEFAULT_EXTRACTION_IDLE_MINUTES,
        writable=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_CONSOLIDATION_ID,
        name="Memory Consolidation",
        description="Consolidate, merge, and archive memory",
        triggers=[
            TimeTrigger(every="30m"),
            IdleTrigger(idle_minutes=DEFAULT_CONSOLIDATION_IDLE_MINUTES),
        ],
        handler="consolidation",
        cooldown_minutes=DEFAULT_CONSOLIDATION_COOLDOWN_MINUTES,
        writable=True,
    ),
]


async def seed_builtins(store: AutomationStore) -> None:
    for spec in BUILTINS:
        existing = await store.get(spec.task_id)
        if existing:
            changes: dict = {}
            if existing.cooldown_minutes is None and spec.cooldown_minutes is not None:
                changes["cooldown_minutes"] = spec.cooldown_minutes
            spec_triggers = [{"type": t.type, **t.params()} for t in spec.triggers]
            existing_triggers = [{"type": t.type, **t.params()} for t in existing.triggers]
            if existing_triggers != spec_triggers:
                changes["triggers"] = spec.triggers
                time_triggers = [t for t in spec.triggers if isinstance(t, TimeTrigger)]
                changes["next_run_at"] = time_triggers[0].next_run(datetime.now(UTC)) if time_triggers else None
            if changes:
                updated = dc_replace(existing, **changes)
                await store.update_metadata(updated)
                _logger.info("Updated builtin automation defaults: %s", spec.name)
            continue

        automation = Automation(
            task_id=spec.task_id,
            name=spec.name,
            description=spec.description,
            model=None,
            triggers=spec.triggers,
            enabled=True,
            created_at=datetime.now(UTC),
            next_run_at=None,
            last_run_at=None,
            last_result=None,
            running_since=None,
            writable=spec.writable,
            handler=spec.handler,
            builtin=True,
            cooldown_minutes=spec.cooldown_minutes,
        )
        await store.save(automation)
        _logger.info("Seeded builtin automation: %s", spec.name)
