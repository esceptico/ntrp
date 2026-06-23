from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime

from ntrp.automation.models import Automation
from ntrp.automation.store import AutomationStore
from ntrp.automation.triggers import TimeTrigger, Trigger
from ntrp.constants import (
    AUTOMATION_SUGGESTER_DAILY_AT,
    BUILTIN_AUTOMATION_SUGGESTER_DAILY_ID,
    BUILTIN_INTEGRATION_SYNC_ID,
    BUILTIN_MEMORY_CONSOLIDATE_ID,
    BUILTIN_MEMORY_DREAM_ID,
    BUILTIN_MEMORY_RETENTION_ID,
    BUILTIN_MEMORY_SYNTHESIZE_ID,
    INTEGRATION_SYNC_AT,
    MEMORY_CONSOLIDATE_AT,
    MEMORY_DREAM_AT,
    MEMORY_RETENTION_AT,
    MEMORY_SYNTHESIZE_AT,
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
        task_id=BUILTIN_AUTOMATION_SUGGESTER_DAILY_ID,
        name="Automation Suggester Daily",
        description="Draft contextual automation suggestions from memory, chats, and actions",
        triggers=[
            TimeTrigger(at=AUTOMATION_SUGGESTER_DAILY_AT, days="daily"),
        ],
        handler="automation_suggester_daily",
        auto_approve=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_MEMORY_CONSOLIDATE_ID,
        name="Memory Maintenance",
        description="Nightly sleep-time reconcile pass: merge duplicate records, supersede stale or contradicted ones, retype mis-classified records, fold near-duplicate labels, and prune tombstones from the canonical memory pool.",
        triggers=[
            TimeTrigger(at=MEMORY_CONSOLIDATE_AT, days="daily"),
        ],
        handler="memory_consolidate",
        auto_approve=True,
        enabled=False,  # file-canonical build: SQLite-engine consolidation deferred
    ),
    BuiltinSpec(
        task_id=BUILTIN_MEMORY_SYNTHESIZE_ID,
        name="Memory Synthesis",
        description="Nightly file-native synthesis: rewrite the prose summary of me.md, entity/project pages, and active-work.md from the canonical timeline atoms, with inline (record:id) provenance. Stale-gated so only changed pages re-synthesize.",
        triggers=[
            TimeTrigger(at=MEMORY_SYNTHESIZE_AT, days="daily"),
        ],
        handler="memory_synthesize",
        auto_approve=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_MEMORY_DREAM_ID,
        name="Memory Dream",
        description="Nightly cross-domain reflection: derive the most salient questions spanning different topics, retrieve cross-topic evidence, and write up to 5 cited cross-domain insights back into memory.",
        triggers=[
            TimeTrigger(at=MEMORY_DREAM_AT, days="daily"),
        ],
        handler="memory_dream",
        auto_approve=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_MEMORY_RETENTION_ID,
        name="Memory Retention",
        description="Nightly deterministic retention: supersede source lines older than 180 days and fact/changelog lines older than 730 days; pinned records and directives are exempt.",
        triggers=[
            TimeTrigger(at=MEMORY_RETENTION_AT, days="daily"),
        ],
        handler="memory_retention",
        auto_approve=True,
    ),
    BuiltinSpec(
        task_id=BUILTIN_INTEGRATION_SYNC_ID,
        name="Integration Sync",
        description="Incrementally pull new calendar, gmail, and slack activity since the last run into memory. Runs just before the nightly maintenance pass so the fresh items get consolidated and synthesized the same night.",
        triggers=[
            TimeTrigger(at=INTEGRATION_SYNC_AT, days="daily"),
        ],
        handler="integration_sync",
        auto_approve=True,
    ),
]

_CURRENT_BUILTIN_IDS = {spec.task_id for spec in BUILTINS}
# Handlers we seed today, plus retired ones whose registration is gone — both
# must be swept so previously-seeded automations don't dangle on a missing
# handler. (pattern_finder/skill_inducer died with the claims+lens pipeline.)
_RETIRED_HANDLERS = {"pattern_finder_daily", "skill_inducer_daily", "memory_publish"}
_KNOWLEDGE_HANDLERS = {spec.handler for spec in BUILTINS} | _RETIRED_HANDLERS


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
