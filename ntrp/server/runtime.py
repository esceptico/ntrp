import asyncio

from fastapi import HTTPException, Request

import ntrp.database as database
from ntrp.automation.scheduler import Scheduler
from ntrp.automation.service import AutomationService
from ntrp.automation.store import AutomationStore
from ntrp.channel import Channel
from ntrp.config import Config, get_config
from ntrp.context.store import SessionStore
from ntrp.core.factory import AgentConfig
from ntrp.events.triggers import TRIGGER_EVENT_TYPES, TriggerEvent
from ntrp.llm.router import close as llm_close
from ntrp.llm.router import init as llm_init
from ntrp.logging import get_logger
from ntrp.mcp.manager import MCPManager
from ntrp.memory.facts import FactMemory
from ntrp.memory.indexable import MemoryIndexable
from ntrp.memory.service import MemoryService
from ntrp.monitor.calendar import CalendarMonitor
from ntrp.monitor.service import Monitor
from ntrp.monitor.store import MonitorStateStore
from ntrp.notifiers.log_store import NotificationLogStore
from ntrp.notifiers.service import NotifierService
from ntrp.notifiers.store import NotifierStore
from ntrp.operator.runner import OperatorDeps
from ntrp.server.indexer import Indexer
from ntrp.server.sources import SourceManager
from ntrp.server.state import RunRegistry
from ntrp.services.config import ConfigService
from ntrp.services.lifecycle import wire_events
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.service import SKILLS_DIRS, SkillService
from ntrp.sources.base import CalendarSource, Indexable
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.channel = Channel()

        self.source_mgr = SourceManager(self.config, self.channel)

        self.embedding = self.config.embedding
        self.indexer = (
            Indexer(db_path=self.config.search_db_path, embedding=self.embedding, channel=self.channel)
            if self.embedding
            else None
        )

        self.session_service: SessionService | None = None
        self._sessions_conn = None

        self.memory: FactMemory | None = None
        self.memory_service: MemoryService | None = None
        self.search_index = None
        self.indexables: dict[str, Indexable] = {}
        self.mcp_manager: MCPManager | None = None
        self.executor: ToolExecutor | None = None

        self.automation_service: AutomationService | None = None
        self.automation_store: AutomationStore | None = None
        self.notifier_store: NotifierStore | None = None
        self.scheduler: Scheduler | None = None
        self.run_registry = RunRegistry()

        self.skill_registry: SkillRegistry | None = None
        self.skill_service: SkillService | None = None
        self.notifier_service: NotifierService | None = None
        self.notification_log: NotificationLogStore | None = None
        self.monitor: Monitor | None = None
        self.monitor_store: MonitorStateStore | None = None
        self.config_service: ConfigService | None = None
        self._connected = False
        self._closing = False
        self._config_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

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
        return services

    # --- Subsystem lifecycle ---

    async def reload_config(self) -> None:
        if self._closing:
            return
        async with self._config_lock:
            self.config = get_config()
            await llm_close()
            llm_init(self.config)
            self.source_mgr.sync(self.config)
            await self._sync_embedding()
            await self._sync_memory()
            self._sync_indexables()
            await self._sync_mcp()

    async def _sync_mcp(self) -> None:
        if self.mcp_manager:
            await self.mcp_manager.close()
            self.mcp_manager = None

        if self.config.mcp_servers:
            self.mcp_manager = MCPManager()
            await self.mcp_manager.connect(self.config.mcp_servers)

        if self.executor:
            self.executor = ToolExecutor(runtime=self)

    async def _sync_memory(self) -> None:
        if self.config.memory and not self.memory and self.embedding:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
            self.memory.dreams_enabled = self.config.dreams
            self.memory_service = MemoryService(self.memory, self.channel)
        elif self.config.memory and self.memory:
            if self.memory.extraction_model != self.config.memory_model:
                self.memory.update_extraction_model(self.config.memory_model)
            self.memory.dreams_enabled = self.config.dreams
        elif not self.config.memory and self.memory:
            if self.memory_service:
                self.memory_service.close()
            await self.memory.close()
            self.memory = None
            self.memory_service = None

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
        await self._init_db()
        await self._init_search()
        wire_events(self)
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

    async def _init_db(self) -> None:
        self.config.db_dir.mkdir(exist_ok=True)
        self._sessions_conn = await database.connect(self.config.sessions_db_path)

        session_store = SessionStore(self._sessions_conn)
        await session_store.init_schema()
        self.session_service = SessionService(session_store)

        self.automation_store = AutomationStore(self._sessions_conn)
        await self.automation_store.init_schema()

        self.notifier_store = NotifierStore(self._sessions_conn)
        await self.notifier_store.init_schema()

        self.notification_log = NotificationLogStore(self._sessions_conn)
        await self.notification_log.init_schema()

        self.monitor_store = MonitorStateStore(self._sessions_conn)
        await self.monitor_store.init_schema()

    async def _init_search(self) -> None:
        if self.indexer:
            await self.indexer.connect()
            self.search_index = self.indexer.index

    def _init_indexables(self) -> None:
        for name, source in self.source_mgr.sources.items():
            if isinstance(source, Indexable):
                self.indexables[name] = source

    async def _init_memory(self) -> None:
        if self.config.memory and self.embedding:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
            self.memory.dreams_enabled = self.config.dreams
            self.memory_service = MemoryService(self.memory, self.channel)
            self.indexables["memory"] = MemoryIndexable(self.memory.db)
        elif self.config.memory:
            _logger.warning("Memory enabled but no embedding model configured — skipping")

    def _init_skills(self) -> None:
        self.skill_registry = SkillRegistry()
        self.skill_registry.load(SKILLS_DIRS)
        self.skill_service = SkillService(self.skill_registry)

    async def _init_notifiers(self) -> None:
        self.notifier_service = NotifierService(
            store=self.notifier_store,
            runtime=self,
        )
        await self.notifier_service.seed_defaults()
        await self.notifier_service.rebuild()

    def _init_automation(self) -> None:
        self.scheduler = Scheduler(store=self.automation_store, build_deps=self.build_operator_deps)
        self.automation_service = AutomationService(
            store=self.automation_store,
            scheduler=self.scheduler,
            get_notifiers=lambda: self.notifier_service.notifiers if self.notifier_service else {},
        )

    async def _init_mcp(self) -> None:
        if self.config.mcp_servers:
            self.mcp_manager = MCPManager()
            await self.mcp_manager.connect(self.config.mcp_servers)

    def _init_tools(self) -> None:
        self.executor = ToolExecutor(runtime=self)
        self.config_service = ConfigService(runtime=self)

    async def close(self) -> None:
        self._closing = True
        if self.monitor:
            await self.monitor.stop()
        if self.scheduler:
            await self.scheduler.stop()
        if self.mcp_manager:
            await self.mcp_manager.close()
        if self.memory:
            await self.memory.close()
        if self._sessions_conn:
            await self._sessions_conn.close()
        if self.indexer:
            await self.indexer.stop()
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
            config=AgentConfig(
                model=self.config.chat_model,
                explore_model=self.config.explore_model,
                max_depth=self.config.max_depth,
                compression_threshold=self.config.compression_threshold,
                max_messages=self.config.max_messages,
                compression_keep_ratio=self.config.compression_keep_ratio,
                summary_max_tokens=self.config.summary_max_tokens,
            ),
            channel=self.channel,
            source_details=self.source_mgr.get_details(),
            create_session=self.session_service.create,
            notifiers=self.notifier_service.notifiers if self.notifier_service else {},
            notification_log=self.notification_log,
        )

    def start_scheduler(self) -> None:
        self.scheduler.start()
        self._wire_event_triggers()

    def _wire_event_triggers(self) -> None:
        async def on_trigger(event: TriggerEvent) -> None:
            if self.scheduler:
                await self.scheduler.fire_event(event)

        for event_cls in TRIGGER_EVENT_TYPES:
            self.channel.subscribe(event_cls, on_trigger)

    def start_monitor(self) -> None:
        if self.monitor_store is None:
            raise RuntimeError("Monitor state store is not initialized")

        self.monitor = Monitor(self.channel)
        calendar_source = self.source_mgr.sources.get("calendar")
        if calendar_source and isinstance(calendar_source, CalendarSource):
            self.monitor.register(CalendarMonitor(calendar_source, state_store=self.monitor_store))

        self.monitor.start()

    async def restart_monitor(self) -> None:
        if self.monitor_store is None:
            return
        if self.monitor:
            await self.monitor.stop()
        self.start_monitor()

    def start_consolidation(self) -> None:
        if self.memory:
            self.memory.start_consolidation()

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
