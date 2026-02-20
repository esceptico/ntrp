import asyncio

import ntrp.database as database
from ntrp.channel import Channel
from ntrp.config import Config, get_config
from ntrp.context.store import SessionStore
from ntrp.core.factory import AgentConfig
from ntrp.llm.router import close as llm_close
from ntrp.llm.router import init as llm_init
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.indexable import MemoryIndexable
from ntrp.memory.service import MemoryService
from ntrp.notifiers.log_store import NotificationLogStore
from ntrp.notifiers.service import NotifierService
from ntrp.notifiers.store import NotifierStore
from ntrp.operator.runner import OperatorDeps
from ntrp.schedule.scheduler import Scheduler
from ntrp.schedule.service import ScheduleService
from ntrp.schedule.store import ScheduleStore
from ntrp.server.dashboard import DashboardCollector
from ntrp.server.indexer import Indexer
from ntrp.server.sources import SourceManager
from ntrp.server.state import RunRegistry
from ntrp.services.config import ConfigService
from ntrp.services.lifecycle import wire_events
from ntrp.services.session import SessionService
from ntrp.skills.registry import SkillRegistry
from ntrp.skills.service import SKILLS_DIRS, SkillService
from ntrp.sources.base import Indexable
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.channel = Channel()

        self.source_mgr = SourceManager(self.config, self.channel)

        self.embedding = self.config.embedding
        self.indexer = Indexer(db_path=self.config.search_db_path, embedding=self.embedding, channel=self.channel)

        self.session_service: SessionService | None = None
        self._sessions_conn = None

        self.memory: FactMemory | None = None
        self.memory_service: MemoryService | None = None
        self.indexables: dict[str, Indexable] = {}
        self.executor: ToolExecutor | None = None

        self.schedule_store: ScheduleStore | None = None
        self.notifier_store: NotifierStore | None = None
        self.scheduler: Scheduler | None = None
        self.schedule_service: ScheduleService | None = None
        self.run_registry = RunRegistry()

        self.skill_registry = SkillRegistry()
        self.skill_service: SkillService | None = None
        self.notifier_service: NotifierService | None = None
        self.notification_log: NotificationLogStore | None = None
        self.dashboard = DashboardCollector()
        self.config_service: ConfigService | None = None
        self._connected = False
        self._config_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    # --- Subsystem lifecycle ---

    async def reload_config(self) -> None:
        async with self._config_lock:
            self.config = get_config()
            self.source_mgr.sync(self.config)
            await self._sync_memory()
            await self._sync_embedding()
            self._sync_indexables()

    async def _sync_memory(self) -> None:
        if self.config.memory and not self.memory:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
            self.memory_service = MemoryService(self.memory, self.channel)
        elif self.config.memory and self.memory:
            if self.memory.extraction_model != self.config.memory_model:
                self.memory.update_extraction_model(self.config.memory_model)
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
            await self.indexer.update_embedding(new_embedding)
            if self.memory:
                self.memory.start_reembed(new_embedding, rebuild=True)

    def _sync_indexables(self) -> None:
        self.indexables.clear()
        for name, source in self.source_mgr.sources.items():
            if isinstance(source, Indexable):
                self.indexables[name] = source
        if self.memory:
            self.indexables["memory"] = MemoryIndexable(self.memory.db)
        self.start_indexing()

    # --- Connect / close ---

    async def connect(self) -> None:
        if self._connected:
            return

        _logger.info("Initializing LLM providers")
        llm_init(self.config)
        self.config.db_dir.mkdir(exist_ok=True)

        _logger.info("Opening database")
        self._sessions_conn = await database.connect(self.config.sessions_db_path)
        session_store = SessionStore(self._sessions_conn)
        await session_store.init_schema()
        self.session_service = SessionService(session_store)

        self.schedule_store = ScheduleStore(self._sessions_conn)
        await self.schedule_store.init_schema()

        self.notifier_store = NotifierStore(self._sessions_conn)
        await self.notifier_store.init_schema()

        self.notification_log = NotificationLogStore(self._sessions_conn)
        await self.notification_log.init_schema()

        _logger.info("Connecting search index")
        await self.indexer.connect()

        wire_events(self)

        if notes := self.source_mgr.sources.get("notes"):
            self.indexables["notes"] = notes

        if self.config.memory:
            _logger.info("Initializing memory")
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
            self.memory_service = MemoryService(self.memory, self.channel)
            self.indexables["memory"] = MemoryIndexable(self.memory.db)

        self.skill_registry.load(SKILLS_DIRS)
        self.skill_service = SkillService(self.skill_registry)

        self.notifier_service = NotifierService(
            store=self.notifier_store,
            runtime=self,
        )
        await self.notifier_service.seed_defaults()
        await self.notifier_service.rebuild()

        _logger.info("Registering tools")
        self.executor = ToolExecutor(runtime=self)

        self.schedule_service = ScheduleService(store=self.schedule_store, runtime=self)
        self.config_service = ConfigService(runtime=self)

        self._connected = True
        _logger.info(
            "Runtime ready",
            sources=len(self.source_mgr.sources),
            tools=len(self.executor.registry),
        )

    async def close(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        if self.memory:
            await self.memory.close()
        if self._sessions_conn:
            await self._sessions_conn.close()
        await self.indexer.stop()
        await self.indexer.close()
        await llm_close()

    # --- Queries ---

    def get_available_sources(self) -> list[str]:
        sources = self.source_mgr.get_available()
        if self.memory:
            sources.append("memory")
        return sources

    def get_source_errors(self) -> dict[str, str]:
        errors = dict(self.source_mgr.errors)
        if self.indexer.error:
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
            ),
            channel=self.channel,
            source_details=self.source_mgr.get_details(),
            create_session=self.session_service.create,
            notifiers=self.notifier_service.notifiers if self.notifier_service else {},
            notification_log=self.notification_log,
        )

    def start_scheduler(self) -> None:
        if self.schedule_store and self.executor and self.notification_log:
            self.scheduler = Scheduler(runtime=self, store=self.schedule_store)
            self.scheduler.start()

    def start_consolidation(self) -> None:
        if self.memory:
            self.memory.start_consolidation()

    def start_indexing(self) -> None:
        self.indexer.start(list(self.indexables.values()))

    async def get_index_status(self) -> dict:
        status = await self.indexer.get_status()
        if self.memory:
            status["reembedding"] = self.memory.reembed_running
            status["reembed_progress"] = self.memory.reembed_progress
        return status


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


async def get_runtime_async() -> Runtime:
    global _runtime
    async with _runtime_lock:
        if _runtime is None:
            _runtime = Runtime()
            await _runtime.connect()
            _runtime.start_indexing()
            _runtime.start_scheduler()
            _runtime.start_consolidation()
    return _runtime


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        raise RuntimeError("Runtime not initialized. Call get_runtime_async() first.")
    if not _runtime.connected:
        raise RuntimeError("Runtime not connected. Call await runtime.connect() first.")
    return _runtime


def get_run_registry() -> RunRegistry:
    return get_runtime().run_registry


async def reset_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.close()
        _runtime = None
