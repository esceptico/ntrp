import asyncio

from fastapi import HTTPException, Request

from ntrp.automation.builtins import seed_builtins
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.channel import Channel
from ntrp.config import Config, get_config
from ntrp.core.factory import AgentConfig
from ntrp.events.internal import FactCreated, FactDeleted, FactUpdated, MemoryCleared, RunCompleted, SourceChanged
from ntrp.events.triggers import TRIGGER_EVENT_TYPES, TriggerEvent
from ntrp.llm.router import close as llm_close
from ntrp.llm.router import init as llm_init
from ntrp.llm.router import reset as llm_reset
from ntrp.logging import get_logger
from ntrp.mcp.manager import MCPManager
from ntrp.memory.extraction_handler import create_chat_extraction_handler
from ntrp.memory.facts import FactMemory
from ntrp.memory.indexable import MemoryIndexable
from ntrp.memory.service import MemoryService
from ntrp.monitor.calendar import CalendarMonitor
from ntrp.monitor.service import Monitor
from ntrp.notifiers.base import NotifierContext
from ntrp.notifiers.service import NotifierService
from ntrp.operator.runner import OperatorDeps
from ntrp.server.indexer import Indexer
from ntrp.server.sources import SourceManager
from ntrp.server.state import RunRegistry
from ntrp.server.stores import Stores
from ntrp.services.config import ConfigService
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.service import SkillService, get_skills_dirs
from ntrp.sources.base import CalendarSource, Indexable
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.channel = Channel()
        self.source_mgr = SourceManager(self.config, self.channel)
        self.run_registry = RunRegistry()

        self.embedding = self.config.embedding
        self.indexer = (
            Indexer(db_path=self.config.search_db_path, embedding=self.embedding, channel=self.channel)
            if self.embedding
            else None
        )

        self.stores: Stores | None = None
        self.memory: FactMemory | None = None
        self.memory_service: MemoryService | None = None
        self.search_index = None
        self.indexables: dict[str, Indexable] = {}
        self.mcp_manager: MCPManager | None = None
        self.executor: ToolExecutor | None = None
        self.automation_service: AutomationService | None = None
        self.scheduler: Scheduler | None = None
        self.skill_registry: SkillRegistry | None = None
        self.skill_service: SkillService | None = None
        self.notifier_service: NotifierService | None = None
        self.monitor: Monitor | None = None
        self.config_service: ConfigService | None = None

        self._connected = False
        self._closing = False
        self._config_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def session_service(self) -> SessionService | None:
        return self.stores.sessions if self.stores else None

    @property
    def tool_services(self) -> dict[str, object]:
        services = dict(self.source_mgr.sources)
        if self.memory:
            services["memory"] = self.memory
        if self.search_index:
            services["search_index"] = self.search_index
        if self.automation_service:
            services["automation"] = self.automation_service
        if self.skill_registry:
            services["skill_registry"] = self.skill_registry
        if self.mcp_manager and self.mcp_manager.tools:
            services["mcp"] = self.mcp_manager
        if self.notifier_service and self.notifier_service.notifiers:
            services["notifiers"] = self.notifier_service
        return services

    def _create_executor(self) -> ToolExecutor:
        mcp_tools = list(self.mcp_manager.tools) if self.mcp_manager else None
        return ToolExecutor(
            mcp_tools=mcp_tools,
            get_services=lambda: self.tool_services,
        )

    # --- Subsystem lifecycle ---

    async def reload_config(self) -> None:
        if self._closing:
            return
        async with self._config_lock:
            self.config = get_config()
            await llm_reset()
            llm_init(self.config)
            self.source_mgr.sync(self.config)
            await self._sync_embedding()
            await self._sync_memory()
            self._sync_indexables()
            await self.sync_mcp()

    async def sync_mcp(self) -> None:
        if self.mcp_manager:
            await self.mcp_manager.close()
            self.mcp_manager = None

        if self.config.mcp_servers:
            self.mcp_manager = MCPManager()
            await self.mcp_manager.connect(self.config.mcp_servers)

        if self.executor:
            self.executor = self._create_executor()

    @property
    def _memory_ready(self) -> bool:
        return bool(self.config.memory and self.embedding and self.config.memory_model)

    async def _create_memory(self) -> None:
        self.memory = await FactMemory.create(
            db_path=self.config.memory_db_path,
            embedding=self.embedding,
            model=self.config.memory_model,
            channel=self.channel,
        )
        self.memory.dreams_enabled = self.config.dreams
        self.memory_service = MemoryService(self.memory, self.channel)

    async def _close_memory(self) -> None:
        if self.memory:
            await self.memory.close()
        self.memory = None
        self.memory_service = None

    async def _sync_memory(self) -> None:
        if self._memory_ready and not self.memory:
            await self._create_memory()
        elif self.config.memory and self.memory:
            if not self._memory_ready:
                await self._close_memory()
                if not self.embedding:
                    _logger.warning("Memory disabled — no embedding model configured")
                else:
                    _logger.warning("Memory disabled — no memory model configured")
                return
            if self.memory.model != self.config.memory_model:
                self.memory.update_model(self.config.memory_model)
            self.memory.dreams_enabled = self.config.dreams
        elif not self.config.memory and self.memory:
            await self._close_memory()

    async def _sync_embedding(self) -> None:
        new_embedding = self.config.embedding
        if new_embedding != self.embedding:
            self.embedding = new_embedding
            if self.indexer:
                await self.indexer.update_embedding(new_embedding)
            if self.memory:
                self.memory.start_reembed(new_embedding, rebuild=True)

    def _sync_indexables(self) -> None:
        prev = set(self.indexables.keys())
        self.indexables.clear()
        for name, source in self.source_mgr.sources.items():
            if isinstance(source, Indexable):
                self.indexables[name] = source
        if self.memory:
            self.indexables["memory"] = MemoryIndexable(self.memory.db)
        if set(self.indexables.keys()) != prev:
            self.start_indexing()

    # --- Connect / close ---

    async def connect(self) -> None:
        if self._connected:
            return

        llm_init(self.config)
        self.stores = await Stores.connect(self.config)
        await self._init_search()
        self._wire_events()
        self._init_indexables()
        await self._init_memory()
        self._init_skills()
        await self._init_notifiers()
        self._init_automation()
        await self._init_mcp()
        self._init_tools()

        self._connected = True
        _logger.info(
            "Runtime ready",
            sources=len(self.source_mgr.sources),
            tools=len(self.executor.registry),
        )

    async def _init_search(self) -> None:
        if self.indexer:
            await self.indexer.connect()
            self.search_index = self.indexer.index

    def _init_indexables(self) -> None:
        for name, source in self.source_mgr.sources.items():
            if isinstance(source, Indexable):
                self.indexables[name] = source

    async def _init_memory(self) -> None:
        if self._memory_ready:
            await self._create_memory()
            self.indexables["memory"] = MemoryIndexable(self.memory.db)
        elif self.config.memory:
            _logger.warning("Memory enabled but no embedding model configured — skipping")

    def _init_skills(self) -> None:
        self.skill_registry = SkillRegistry()
        self.skill_registry.load(get_skills_dirs())
        self.skill_service = SkillService(self.skill_registry)

    async def _init_notifiers(self) -> None:
        self.notifier_service = NotifierService(
            store=self.stores.notifiers,
            ctx=NotifierContext(
                get_source=lambda name: self.source_mgr.sources.get(name),
                get_config_value=lambda key: getattr(self.config, key, None),
            ),
        )
        await self.notifier_service.seed_defaults()
        await self.notifier_service.rebuild()

    def _init_automation(self) -> None:
        self.scheduler = Scheduler(
            store=self.stores.automations,
            build_deps=self.build_operator_deps,
        )
        self.automation_service = AutomationService(
            store=self.stores.automations,
            scheduler=self.scheduler,
        )

    async def _init_mcp(self) -> None:
        if self.config.mcp_servers:
            self.mcp_manager = MCPManager()
            await self.mcp_manager.connect(self.config.mcp_servers)

    def _init_tools(self) -> None:
        self.executor = self._create_executor()
        self.config_service = ConfigService(on_config_change=self.reload_config)

    async def close(self) -> None:
        self._closing = True

        # Phase 1: stop accepting new work
        cancelled = await self.run_registry.cancel_all()
        if cancelled:
            _logger.info("Cancelled %d active run(s)", cancelled)

        # Phase 2: stop background services
        if self.monitor:
            await self.monitor.stop()
        if self.scheduler:
            await self.scheduler.stop()
        if self.indexer:
            await self.indexer.stop()

        # Phase 3: close resources
        if self.mcp_manager:
            await self.mcp_manager.close()
        await self._close_memory()
        if self.stores:
            await self.stores.close()
        if self.indexer:
            await self.indexer.close()
        await llm_close()
        await self.channel.stop()

    # --- Queries ---

    def get_available_sources(self) -> list[str]:
        sources = self.source_mgr.get_available()
        if self.memory:
            sources.append("memory")
        return sources

    def get_source_errors(self) -> dict[str, str]:
        errors = dict(self.source_mgr.errors)
        if self.indexer and self.indexer.error:
            errors["index"] = self.indexer.error
        return errors

    # --- Background tasks ---

    def build_operator_deps(self) -> OperatorDeps:
        return OperatorDeps(
            executor=self.executor,
            memory=self.memory,
            config=AgentConfig.from_config(self.config),
            channel=self.channel,
            source_details=self.source_mgr.get_details(),
            create_session=self.stores.sessions.create,
            notifier_names=list(self.notifier_service.notifiers) if self.notifier_service else [],
        )

    async def start_scheduler(self) -> None:
        if self.memory:
            self.scheduler.register_handler(
                "chat_extraction",
                create_chat_extraction_handler(self.memory, self.channel),
            )
            self.scheduler.register_handler(
                "consolidation",
                self._build_consolidation_handler(),
            )

        await seed_builtins(self.stores.automations)
        self.scheduler.start()
        self._wire_event_triggers()

    def _wire_events(self) -> None:
        if not self.indexer:
            return

        async def on_fact_upserted(event: FactCreated | FactUpdated) -> None:
            await self.indexer.index.upsert(
                source="memory",
                source_id=f"fact:{event.fact_id}",
                title=event.text[:50],
                content=event.text,
            )

        async def on_fact_deleted(event: FactDeleted) -> None:
            await self.indexer.index.delete("memory", f"fact:{event.fact_id}")

        async def on_memory_cleared(_event: MemoryCleared) -> None:
            await self.indexer.index.clear_source("memory")

        async def on_source_changed(event: SourceChanged) -> None:
            name = event.source_name
            source = self.source_mgr.sources.get(name)
            if source and isinstance(source, Indexable):
                self.indexables[name] = source
                self.start_indexing()
            elif source is None:
                self.indexables.pop(name, None)
                await self.indexer.index.clear_source(name)

        self.channel.subscribe(FactCreated, on_fact_upserted)
        self.channel.subscribe(FactUpdated, on_fact_upserted)
        self.channel.subscribe(FactDeleted, on_fact_deleted)
        self.channel.subscribe(MemoryCleared, on_memory_cleared)
        self.channel.subscribe(SourceChanged, on_source_changed)

    def _build_consolidation_handler(self):
        async def handler(context: dict | None) -> str | None:
            if not self.memory:
                return None
            return await self.memory.run_consolidation()

        return handler

    def _wire_event_triggers(self) -> None:
        async def on_trigger(event: TriggerEvent) -> None:
            if self.scheduler:
                await self.scheduler.fire_event(event)

        for event_cls in TRIGGER_EVENT_TYPES:
            self.channel.subscribe(event_cls, on_trigger)

        async def on_run_completed(event: RunCompleted) -> None:
            if self.scheduler:
                await self.scheduler.handle_run_completed(event)

        self.channel.subscribe(RunCompleted, on_run_completed)

    def start_monitor(self) -> None:
        if self.stores.monitor is None:
            raise RuntimeError("Monitor state store is not initialized")

        self.monitor = Monitor(self.channel)
        calendar_source = self.source_mgr.sources.get("calendar")
        if calendar_source and isinstance(calendar_source, CalendarSource):
            self.monitor.register(CalendarMonitor(calendar_source, state_store=self.stores.monitor))

        self.monitor.start()

    async def sync_google_sources(self) -> None:
        await self.source_mgr.reinit("gmail", self.config)
        await self.source_mgr.reinit("calendar", self.config)
        await self.restart_monitor()

    async def restart_monitor(self) -> None:
        if self.stores.monitor is None:
            return
        if self.monitor:
            await self.monitor.stop()
        self.start_monitor()

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(list(self.indexables.values()))

    async def get_index_status(self) -> dict:
        status = await self.indexer.get_status() if self.indexer else {"status": "disabled"}
        if self.memory:
            status["reembedding"] = self.memory.reembed_running
            status["reembed_progress"] = self.memory.reembed_progress
        return status


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime | None = getattr(request.app.state, "runtime", None)
    if runtime is None or not runtime.connected:
        raise HTTPException(status_code=503, detail="Server is initializing")
    return runtime
