from collections.abc import Callable
from datetime import datetime

from ntrp.automation.builtins import seed_builtins
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.integrations.calendar.client import MultiCalendarSource
from ntrp.memory.extraction_handler import create_chat_extraction_handler
from ntrp.memory.facts import FactMemory
from ntrp.memory.service import MemoryService
from ntrp.monitor.calendar import CalendarMonitor
from ntrp.monitor.service import Monitor
from ntrp.operator.runner import OperatorDeps
from ntrp.server.indexer import Indexer
from ntrp.server.runtime.outbox import RuntimeOutbox
from ntrp.server.stores import Stores


class AutomationRuntime:
    def __init__(
        self,
        *,
        stores: Stores,
        build_operator_deps: Callable[[], OperatorDeps],
        get_memory: Callable[[], FactMemory | None],
        get_calendar_source: Callable[[], object | None],
        indexer: Indexer | None,
    ):
        self.stores = stores
        self.get_memory = get_memory
        self.get_calendar_source = get_calendar_source
        self.scheduler = Scheduler(
            store=stores.automations,
            build_deps=build_operator_deps,
        )
        self.automation_service = AutomationService(
            store=stores.automations,
            scheduler=self.scheduler,
        )
        self.outbox_runtime = RuntimeOutbox(
            outbox_store=stores.outbox,
            automation_store=stores.automations,
            scheduler=self.scheduler,
            indexer=indexer,
        )
        self.monitor: Monitor | None = None

    async def stop(self) -> None:
        if self.monitor:
            await self.monitor.stop()
        await self.outbox_runtime.stop()
        await self.scheduler.stop()

    async def start_scheduler(self) -> None:
        memory = self.get_memory()
        if memory:
            self.scheduler.register_handler(
                "chat_extraction",
                create_chat_extraction_handler(memory, self.stores.automations),
            )
            self.scheduler.register_handler(
                "consolidation",
                self._build_consolidation_handler(),
            )
            self.scheduler.register_handler(
                "memory_maintenance",
                self._build_memory_maintenance_handler(),
            )
            self.scheduler.register_handler(
                "memory_health",
                self._build_memory_health_handler(),
            )
            self.scheduler.register_handler(
                "learning_review",
                self._build_learning_review_handler(),
            )

        await seed_builtins(self.stores.automations)
        self.scheduler.start()
        self.outbox_runtime.start()

    def _build_consolidation_handler(self):
        async def handler(context: dict | None) -> str | None:
            memory = self.get_memory()
            if not memory:
                return None
            return await memory.run_consolidation()

        return handler

    def _build_memory_maintenance_handler(self):
        async def handler(context: dict | None) -> str | None:
            memory = self.get_memory()
            if not memory:
                return None
            return await memory.run_memory_maintenance()

        return handler

    def _build_memory_health_handler(self):
        async def handler(context: dict | None) -> str | None:
            memory = self.get_memory()
            if not memory:
                return None
            return await memory.run_memory_health_audit()

        return handler

    def _build_learning_review_handler(self):
        async def handler(context: dict | None) -> str | None:
            memory = self.get_memory()
            if not memory:
                return None
            result = await MemoryService(memory).learning.propose_from_memory_policy()
            return (
                "Learning review scan: "
                f"{len(result.created_candidates)} new, "
                f"{len(result.skipped_candidates)} existing, "
                f"{result.proposals_considered} considered"
            )

        return handler

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
