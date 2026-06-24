from collections.abc import Callable
from datetime import datetime

from ntrp.agent_surface.schedules import compile_schedules_to_automations
from ntrp.automation.builtins import seed_builtins
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.automation.suggestions import AutomationSuggester, AutomationSuggestion
from ntrp.events.sse import AutomationSuggestionsUpdatedEvent
from ntrp.integrations.calendar.client import MultiCalendarSource
from ntrp.logging import get_logger
from ntrp.monitor.calendar import CalendarMonitor
from ntrp.monitor.service import Monitor
from ntrp.operator.runner import OperatorDeps
from ntrp.server.indexer import Indexer
from ntrp.server.runtime.outbox import RuntimeOutbox
from ntrp.server.stores import Stores

_logger = get_logger(__name__)


class SuggesterUnavailableError(Exception):
    """Raised when the automation suggester cannot run (memory or cheap_llm missing)."""


class AutomationRuntime:
    def __init__(
        self,
        *,
        stores: Stores,
        build_operator_deps: Callable[[], OperatorDeps],
        get_records: Callable[[], object | None],
        get_chat_connector: Callable[[], object | None],
        get_calendar_source: Callable[[], object | None],
        get_slack_client: Callable[[], object | None],
        get_cheap_llm: Callable[[], object | None],
        cheap_model: str | None,
        indexer: Indexer | None,
        get_consolidate: Callable[[], object | None] = lambda: None,
        get_knowledge: Callable[[], object | None] = lambda: None,
        get_integration_clients: Callable[[], dict[str, object]] = dict,
    ):
        self.stores = stores
        self.get_records = get_records
        self.get_calendar_source = get_calendar_source
        self.get_slack_client = get_slack_client
        self.get_cheap_llm = get_cheap_llm
        self.get_consolidate = get_consolidate
        self.get_knowledge = get_knowledge
        self.get_integration_clients = get_integration_clients
        self.cheap_model = cheap_model
        self.scheduler = Scheduler(
            store=stores.automations,
            build_deps=build_operator_deps,
        )
        self.automation_service = AutomationService(
            store=stores.automations,
            scheduler=self.scheduler,
            session_service=stores.sessions,
            get_slack_client=self.get_slack_client,
        )
        self.outbox_runtime = RuntimeOutbox(
            outbox_store=stores.outbox,
            automation_store=stores.automations,
            scheduler=self.scheduler,
            indexer=indexer,
            get_chat_connector=get_chat_connector,
        )
        self.monitor: Monitor | None = None

    async def stop(self) -> None:
        if self.monitor:
            await self.monitor.stop()
        await self.outbox_runtime.stop()
        await self.scheduler.stop()

    async def start_scheduler(self) -> None:
        self.scheduler.register_handler(
            "automation_suggester_daily",
            self._build_automation_suggester_handler(),
        )
        self.scheduler.register_handler(
            "memory_consolidate",
            self._build_memory_consolidate_handler(),
        )
        self.scheduler.register_handler(
            "integration_sync",
            self._build_integration_sync_handler(),
        )
        self.scheduler.register_handler(
            "memory_dream",
            self._build_memory_dream_handler(),
        )
        self.scheduler.register_handler(
            "memory_synthesize",
            self._build_memory_synthesize_handler(),
        )
        self.scheduler.register_handler(
            "memory_retention",
            self._build_memory_retention_handler(),
        )

        await seed_builtins(self.stores.automations)
        await compile_schedules_to_automations(".", self.stores.automations)
        await self.automation_service.backfill_channels()
        self.scheduler.start()
        self.outbox_runtime.start()

    def _build_automation_suggester_handler(self):
        async def handler(context: dict | None) -> str | None:
            return await self._run_suggester()

        return handler

    def _build_memory_consolidate_handler(self):
        async def handler(context: dict | None) -> str | None:
            consolidate = self.get_consolidate()
            if consolidate is None:
                return "memory consolidation unavailable (no memory model configured)"
            totals: dict[str, int] | None = None
            # run_once is O(delta)-bounded (200/call); loop so one scheduled run
            # drains the day's backlog. Empty pass -> done.
            for _ in range(8):
                rep = await consolidate.run_once()
                if totals is None:
                    totals = {key: 0 for key in rep.summary_counts}
                for key, value in rep.summary_counts.items():
                    totals[key] += value
                if not rep.changed_memory:
                    break
            assert totals is not None
            ordered_keys = (
                "merged",
                "superseded",
                "dropped",
                "retyped",
                "relabeled",
                "reclassified",
                "pruned",
            )
            return ", ".join(f"{key} {totals[key]}" for key in ordered_keys if key in totals)

        return handler

    def _build_memory_dream_handler(self):
        async def handler(context: dict | None) -> str | None:
            knowledge = self.get_knowledge()
            if knowledge is None or not knowledge.memory_ready:
                return "memory dream unavailable (memory not ready)"
            from ntrp.memory.dreamer import run_dream
            from ntrp.memory.file_store import load_conventions
            from ntrp.memory.maintenance import append_learnings, read_learnings
            from ntrp.memory.models import now_iso

            llm, model = knowledge._memory_llm()
            effort = knowledge._memory_reasoning_effort(knowledge.config.memory_model)
            # B: per-automation continual learning — read prior gotchas, append new ones.
            root = knowledge.record_store._root
            learnings = read_learnings(root, "memory_dream")
            summary, new = await run_dream(
                knowledge.record_store, llm, model, reasoning_effort=effort,
                conventions=load_conventions(), learnings=learnings,
            )
            append_learnings(root, "memory_dream", new, date=now_iso())
            return summary

        return handler

    def _build_memory_synthesize_handler(self):
        async def handler(context: dict | None) -> str | None:
            knowledge = self.get_knowledge()
            if knowledge is None or not knowledge.memory_ready:
                return "memory synthesis unavailable (memory not ready)"
            from ntrp.memory.synthesize import run_synthesis

            llm, model = knowledge._memory_llm()
            effort = knowledge._memory_reasoning_effort(knowledge.config.memory_model)
            # Tag untagged records with their named subject FIRST, so recurring people/
            # orgs/products promote to topic pages that this same pass then synthesizes.
            tagged = 0
            if knowledge.memory_curator is not None:
                tagged = await knowledge.memory_curator.backfill_entity_labels()
            summary = await run_synthesis(knowledge.record_store, llm, model, reasoning_effort=effort)
            return f"{summary} (+{tagged} entity tags)" if tagged else summary

        return handler

    def _build_memory_retention_handler(self):
        async def handler(context: dict | None) -> str | None:
            knowledge = self.get_knowledge()
            if knowledge is None or not knowledge.memory_ready:
                return "memory retention unavailable (memory not ready)"
            from ntrp.memory.retention import run_retention

            store = knowledge.record_store
            report = await run_retention(store)
            # Retention tombstones atoms; fold any entity page that just dropped
            # below the promotion threshold back into me.md the same night.
            stats = await store.reconcile_entities()
            detail = f"; entities {stats}" if (stats["promoted"] or stats["demoted"]) else ""
            return report.summary() + detail

        return handler

    def _build_integration_sync_handler(self):
        async def handler(context: dict | None) -> str | None:
            knowledge = self.get_knowledge()
            if knowledge is None or not knowledge.memory_ready:
                return "integration sync unavailable (memory not ready)"
            clients = self.get_integration_clients() or {}
            if not clients:
                return "integration sync skipped (no integrations connected)"
            from ntrp.memory.init import run_integration_ingest

            report = await run_integration_ingest(knowledge, integration_clients=clients)
            parts = [f"{src}: {d.get('admitted', 0)} new" for src, d in report["integrations"].items()]
            return "; ".join(parts) or "no connected sources"

        return handler

    def _suggester_available(self) -> bool:
        return self.get_records() is not None and self.get_cheap_llm() is not None

    async def _run_suggester(self) -> str | None:
        if not self._suggester_available():
            return None
        suggester = AutomationSuggester(
            records=self.get_records(),
            sessions=self.stores.sessions,
            automations=self.stores.automations,
            cheap_llm=self.get_cheap_llm(),
            model=self.cheap_model,
        )
        summary = await suggester.run()
        await self.scheduler.emit_automation_event(AutomationSuggestionsUpdatedEvent())
        return summary

    async def refresh_suggestions(self) -> list[AutomationSuggestion]:
        if not self._suggester_available():
            raise SuggesterUnavailableError("memory or cheap_llm is not available")
        await self._run_suggester()
        return await self.stores.automations.list_active_suggestions()

    def start_monitor(self) -> None:
        if self.stores.monitor is None:
            raise RuntimeError("Monitor state store is not initialized")

        self.monitor = Monitor(self.scheduler.fire_event)
        calendar_source = self.get_calendar_source()
        if calendar_source and isinstance(calendar_source, MultiCalendarSource):
            self.monitor.register(CalendarMonitor(calendar_source, state_store=self.stores.monitor))

        self.monitor.start()

    async def restart_monitor(self) -> None:
        if self.stores.monitor is None:
            return
        if self.monitor:
            await self.monitor.stop()
        self.start_monitor()

    async def get_scheduler_status(self) -> dict:
        if not self.scheduler:
            return {"status": "disabled", "running_tasks": 0, "registered_handlers": []}
        return await self.scheduler.get_status()

    async def get_outbox_status(self) -> dict:
        return await self.outbox_runtime.get_status()

    async def get_outbox_health(self) -> dict:
        return await self.outbox_runtime.get_health()

    async def replay_outbox_dead_events(self, event_ids: list[int]) -> dict:
        return await self.outbox_runtime.replay_dead_events(event_ids)

    async def prune_outbox_completed(self, *, before: datetime, limit: int) -> dict:
        return await self.outbox_runtime.prune_completed(before=before, limit=limit)
