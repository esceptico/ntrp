from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime

from ntrp.automation.models import Automation
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import CountTrigger, IdleTrigger, KnowledgeEventTrigger, TimeTrigger, Trigger
from ntrp.constants import (
    BUILTIN_KNOWLEDGE_HEALTH_ID,
    BUILTIN_KNOWLEDGE_REFLECTION_ID,
    BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID,
    BUILTIN_KNOWLEDGE_RETENTION_ID,
    DEFAULT_KNOWLEDGE_HEALTH_COOLDOWN_MINUTES,
    DEFAULT_KNOWLEDGE_REFLECTION_IDLE_MINUTES,
    DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_COOLDOWN_MINUTES,
    DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_IDLE_MINUTES,
    DEFAULT_KNOWLEDGE_RETENTION_COOLDOWN_MINUTES,
    KNOWLEDGE_REFLECTION_EVERY_N_TURNS,
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
    writable: bool = False
    cooldown_minutes: int | None = None


BUILTINS = [
    BuiltinSpec(
        task_id=BUILTIN_KNOWLEDGE_REFLECTION_ID,
        name="Knowledge Reflection",
        description="Reflect durable episodes into lessons, actions, procedures, and artifacts",
        triggers=[
            KnowledgeEventTrigger(
                actions=("created",),
                object_types=("episode",),
                statuses=("active",),
            ),
            CountTrigger(every_n=KNOWLEDGE_REFLECTION_EVERY_N_TURNS),
            IdleTrigger(idle_minutes=DEFAULT_KNOWLEDGE_REFLECTION_IDLE_MINUTES),
        ],
        handler="knowledge_reflection",
        cooldown_minutes=DEFAULT_KNOWLEDGE_REFLECTION_IDLE_MINUTES,
        writable=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_KNOWLEDGE_REFLECTION_SWEEP_ID,
        name="Knowledge Reflection Sweep",
        description="Run knowledge reflection over active episodes",
        triggers=[
            TimeTrigger(every="30m"),
            IdleTrigger(idle_minutes=DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_IDLE_MINUTES),
        ],
        handler="knowledge_reflection",
        cooldown_minutes=DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_COOLDOWN_MINUTES,
        writable=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_KNOWLEDGE_RETENTION_ID,
        name="Knowledge Retention",
        description="Archive stale generated knowledge objects",
        triggers=[
            TimeTrigger(at="03:30", days="daily"),
            IdleTrigger(idle_minutes=DEFAULT_KNOWLEDGE_REFLECTION_SWEEP_IDLE_MINUTES),
        ],
        handler="knowledge_retention",
        cooldown_minutes=DEFAULT_KNOWLEDGE_RETENTION_COOLDOWN_MINUTES,
        writable=False,
    ),
    BuiltinSpec(
        task_id=BUILTIN_KNOWLEDGE_HEALTH_ID,
        name="Knowledge Health Audit",
        description="Read-only knowledge health and provenance snapshot",
        triggers=[
            TimeTrigger(at="04:00", days="daily"),
        ],
        handler="knowledge_health",
        cooldown_minutes=DEFAULT_KNOWLEDGE_HEALTH_COOLDOWN_MINUTES,
        writable=False,
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
            if existing.writable != spec.writable:
                changes["writable"] = spec.writable
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
            enabled=spec.enabled,
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
