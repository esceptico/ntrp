import asyncio
from datetime import UTC, datetime
from pathlib import Path

import ntrp.database as database
from ntrp.channel import Channel
from ntrp.config import NTRP_DIR, Config, get_config
from ntrp.constants import AGENT_MAX_DEPTH, SESSION_EXPIRY_HOURS
from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.events import SourceChanged
from ntrp.llm.router import close as llm_close, init as llm_init
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.service import MemoryService
from ntrp.notifiers import Notifier, create_notifier
from ntrp.notifiers.service import NotifierService
from ntrp.notifiers.store import NotifierStore
from ntrp.schedule.scheduler import Scheduler, SchedulerDeps
from ntrp.schedule.store import ScheduleStore
from ntrp.server.dashboard import DashboardCollector
from ntrp.server.indexer import Indexer
from ntrp.server.sources import SourceManager
from ntrp.server.state import RunRegistry
from ntrp.services.config import ConfigService
from ntrp.services.lifecycle import wire_events
from ntrp.skills.registry import SkillRegistry
from ntrp.sources.browser import BrowserHistorySource
from ntrp.sources.google.gmail import MultiGmailSource
from ntrp.sources.memory import MemoryIndexSource
from ntrp.tools.executor import ToolExecutor

_logger = get_logger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.channel = Channel()

        self.source_mgr = SourceManager(self.config, self.channel)

        self.embedding = self.config.embedding
        self.indexer = Indexer(db_path=self.config.search_db_path, embedding=self.embedding, channel=self.channel)

        self.session_store: SessionStore | None = None
        self._sessions_conn = None

        self.memory: FactMemory | None = None
        self.memory_service: MemoryService | None = None
        self.executor: ToolExecutor | None = None
        self.tools: list[dict] = []

        self.max_depth = AGENT_MAX_DEPTH
        self.schedule_store: ScheduleStore | None = None
        self.notifier_store: NotifierStore | None = None
        self.scheduler: Scheduler | None = None
        self.run_registry = RunRegistry()

        self.skill_registry = SkillRegistry()
        self.notifiers: dict[str, Notifier] = {}
        self.notifier_service: NotifierService | None = None
        self.dashboard = DashboardCollector()
        self.config_service: ConfigService | None = None
        self._connected = False
        self._config_lock = asyncio.Lock()

    # --- Source accessors ---

    def get_gmail(self) -> MultiGmailSource | None:
        return self.source_mgr.sources.get("email")

    def get_browser(self) -> BrowserHistorySource | None:
        return self.source_mgr.sources.get("browser")

    # --- Subsystem lifecycle ---

    async def reinit_memory(self, enabled: bool) -> None:
        if enabled and not self.memory:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
            self.memory_service = MemoryService(self.memory, self.channel)
        elif not enabled and self.memory:
            await self.memory.close()
            self.memory = None
            self.memory_service = None
        self.channel.publish(SourceChanged(source_name="memory"))

    def rebuild_executor(self) -> None:
        self.executor = ToolExecutor(
            sources=self.source_mgr.sources,
            memory=self.memory,
            model=self.config.chat_model,
            search_index=self.indexer.index,
            schedule_store=self.schedule_store,
            default_notifiers=list(self.notifiers.keys()) or None,
            skill_registry=self.skill_registry if self.skill_registry else None,
        )
        self.tools = self.executor.get_tools()

    async def rebuild_notifiers(self) -> None:
        self.notifiers.clear()
        if self.notifier_store:
            for cfg in await self.notifier_store.list_all():
                try:
                    self.notifiers[cfg.name] = create_notifier(
                        cfg,
                        config=self.config,
                        gmail=self.get_gmail,
                    )
                except Exception:
                    _logger.exception("Failed to create notifier %r", cfg.name)
        self.rebuild_executor()

    # --- Connect / close ---

    async def connect(self) -> None:
        if self._connected:
            return

        llm_init(self.config)
        self.config.db_dir.mkdir(exist_ok=True)

        self._sessions_conn = await database.connect(self.config.sessions_db_path)
        self.session_store = SessionStore(self._sessions_conn)
        await self.session_store.init_schema()

        self.schedule_store = ScheduleStore(self._sessions_conn)
        await self.schedule_store.init_schema()

        self.notifier_store = NotifierStore(self._sessions_conn)
        await self.notifier_store.init_schema()

        await self.indexer.connect()

        wire_events(self)

        if self.config.memory:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
            self.memory_service = MemoryService(self.memory, self.channel)

        self.skill_registry.load(
            [
                (Path.cwd() / ".skills", "project"),
                (NTRP_DIR / "skills", "global"),
            ]
        )

        await self.rebuild_notifiers()

        self.notifier_service = NotifierService(
            store=self.notifier_store,
            schedule_store=self.schedule_store,
            notifiers=self.notifiers,
            rebuild_fn=self.rebuild_notifiers,
            get_gmail=self.get_gmail,
        )

        self.config_service = ConfigService(
            config=self.config,
            source_mgr=self.source_mgr,
            indexer=self.indexer,
            reinit_memory_fn=self.reinit_memory,
            rebuild_executor_fn=self.rebuild_executor,
            start_indexing_fn=self.start_indexing,
            start_reembed_fn=lambda emb: self.memory.start_reembed(emb, rebuild=True) if self.memory else None,
            config_lock=self._config_lock,
            get_max_depth=lambda: self.max_depth,
            set_max_depth=lambda v: setattr(self, "max_depth", v),
        )

        self._connected = True

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

    def get_source_details(self) -> dict[str, dict]:
        return self.source_mgr.get_details()

    def get_source_errors(self) -> dict[str, str]:
        errors = dict(self.source_mgr.errors)
        if self.indexer.error:
            errors["index"] = self.indexer.error
        return errors

    def get_available_sources(self) -> list[str]:
        sources = self.source_mgr.get_available()
        if self.memory:
            sources.append("memory")
        return sources

    # --- Session ---

    def create_session(self) -> SessionState:
        now = datetime.now(UTC)
        return SessionState(
            session_id=now.strftime("%Y%m%d_%H%M%S"),
            started_at=now,
        )

    async def restore_session(self) -> SessionData | None:
        try:
            data = await self.session_store.get_latest_session()
        except Exception as e:
            _logger.warning("Failed to restore session: %s", e)
            return None

        if not data:
            return None

        age_hours = (datetime.now(UTC) - data.state.last_activity).total_seconds() / 3600
        if age_hours > SESSION_EXPIRY_HOURS:
            return None

        if not data.messages or len(data.messages) < 2:
            return None

        return data

    async def save_session(
        self,
        session_state: SessionState,
        messages: list[dict],
        metadata: dict | None = None,
    ) -> None:
        try:
            session_state.last_activity = datetime.now(UTC)
            await self.session_store.save_session(session_state, messages, metadata=metadata)
        except Exception as e:
            _logger.warning("Failed to save session: %s", e)

    # --- Background tasks ---

    def start_scheduler(self) -> None:
        if self.schedule_store and self.executor:
            deps = SchedulerDeps(
                executor=self.executor,
                memory=lambda: self.memory,
                model=self.config.chat_model,
                max_depth=self.max_depth,
                channel=self.channel,
                source_details=self.get_source_details,
                create_session=self.create_session,
                explore_model=self.config.explore_model,
            )
            self.scheduler = Scheduler(deps, self.schedule_store)
            self.scheduler.start()

    def start_consolidation(self) -> None:
        if self.memory:
            self.memory.start_consolidation()

    def start_indexing(self) -> None:
        sources = []
        if notes := self.source_mgr.sources.get("notes"):
            sources.append(notes)
        if self.memory:
            sources.append(MemoryIndexSource(self.memory.db))
        self.indexer.start(sources)

    async def get_index_status(self) -> dict:
        status = await self.indexer.get_status()
        if self.memory:
            status["reembedding"] = self.memory.reembed_running
            status["reembed_progress"] = self.memory._reembed_progress
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
    if not _runtime._connected:
        raise RuntimeError("Runtime not connected. Call await runtime.connect() first.")
    return _runtime


def get_run_registry() -> RunRegistry:
    return get_runtime().run_registry


async def reset_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.close()
        _runtime = None
