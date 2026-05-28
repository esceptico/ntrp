from collections.abc import Callable
from datetime import datetime

from ntrp.automation.builtins import seed_builtins
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.integrations.calendar.client import MultiCalendarSource
from ntrp.memory.pattern_finder import PatternFinder
from ntrp.memory.runtime import MemoryDatabase
from ntrp.memory.service import MemoryService
from ntrp.memory.skill_inducer import SkillInducer
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
        get_memory: Callable[[], MemoryDatabase | None],
        get_memory_service: Callable[[], MemoryService | None],
        get_pattern_finder: Callable[[], PatternFinder | None],
        get_calendar_source: Callable[[], object | None],
        indexer: Indexer | None,
    ):
        self.stores = stores
        self.get_memory = get_memory
        self.get_memory_service = get_memory_service
        self.get_pattern_finder = get_pattern_finder
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
            get_memory_service=get_memory_service,
        )
        self.monitor: Monitor | None = None

    async def stop(self) -> None:
        if self.monitor:
            await self.monitor.stop()
        await self.outbox_runtime.stop()
        await self.scheduler.stop()

    async def start_scheduler(self) -> None:
        self.scheduler.register_handler(
            "pattern_finder_daily",
            self._build_pattern_finder_daily_handler(),
        )
        self.scheduler.register_handler(
            "skill_inducer_daily",
            self._build_skill_inducer_daily_handler(),
        )

        await seed_builtins(self.stores.automations)
        self.scheduler.start()
        self.outbox_runtime.start()

    def _build_pattern_finder_daily_handler(self):
        async def handler(context: dict | None) -> str | None:
            pattern_finder = self.get_pattern_finder()
            if not pattern_finder:
                return None
            pass1 = await pattern_finder.run_pass1(window_days=7, scope="user")
            pass2 = await pattern_finder.run_pass2(window_days=30, scope="user")
            return (
                f"pass1_clusters={pass1.clusters_found}; observations={pass1.observations_written}; "
                f"pass1_superseded={pass1.observations_superseded}; pass2_clusters={pass2.clusters_found}; "
                f"claims={pass2.claims_written}; claims_superseded={pass2.claims_superseded}"
            )

        return handler

    def _build_skill_inducer_daily_handler(self):
        async def handler(context: dict | None) -> str | None:
            pattern_finder = self.get_pattern_finder()
            if not pattern_finder:
                return None
            inducer = getattr(pattern_finder, "skill_inducer", None)
            if inducer is None:
                inducer = SkillInducer(
                    repo=pattern_finder.repo,
                    draft_client=pattern_finder.summary_client,
                    embedder=pattern_finder.embedder,
                )
                pattern_finder.skill_inducer = inducer
            result = await inducer.run(window_days=30, scope="user")
            return (
                f"claims_considered={result.claims_considered}; toolable_claims={result.toolable_claims}; "
                f"clusters={result.clusters_found}; proposals={result.proposals_written}"
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
