import asyncio
from datetime import UTC, datetime
from pathlib import Path

import litellm.llms.custom_httpx.async_client_cleanup as litellm_cleanup
import litellm.main as litellm_main

import ntrp.database as database
from ntrp.channel import Channel
from ntrp.config import Config, NTRP_DIR, get_config
from ntrp.constants import AGENT_MAX_DEPTH, INDEXABLE_SOURCES, SESSION_EXPIRY_HOURS
from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.core.events import ConsolidationCompleted, RunCompleted, RunStarted, ScheduleCompleted, ToolExecuted
from ntrp.logging import get_logger
from ntrp.memory.events import FactCreated, FactDeleted, FactUpdated, MemoryCleared
from ntrp.memory.facts import FactMemory
from ntrp.notifiers import Notifier, create_notifier, make_schedule_dispatcher
from ntrp.notifiers.store import NotifierStore
from ntrp.schedule.scheduler import Scheduler, SchedulerDeps
from ntrp.schedule.store import ScheduleStore
from ntrp.server.dashboard import DashboardCollector
from ntrp.server.indexer import Indexer
from ntrp.server.sources import SourceManager
from ntrp.server.state import RunRegistry
from ntrp.sources.browser import BrowserHistorySource
from ntrp.sources.events import SourceChanged
from ntrp.skills.registry import SkillRegistry
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
        self.executor: ToolExecutor | None = None
        self.tools: list[dict] = []

        self.max_depth = AGENT_MAX_DEPTH
        self.schedule_store: ScheduleStore | None = None
        self.notifier_store: NotifierStore | None = None
        self.scheduler: Scheduler | None = None
        self.run_registry = RunRegistry()

        self.skill_registry = SkillRegistry()
        self.notifiers: dict[str, Notifier] = {}
        self.dashboard = DashboardCollector()
        self._connected = False
        self._config_lock = asyncio.Lock()

    def get_gmail(self) -> MultiGmailSource | None:
        return self.source_mgr.sources.get("email")

    def get_browser(self) -> BrowserHistorySource | None:
        return self.source_mgr.sources.get("browser")

    async def reinit_source(self, name: str) -> None:
        await self.source_mgr.reinit(name, self.config)

    async def remove_source(self, name: str) -> None:
        await self.source_mgr.remove(name)

    async def reinit_memory(self, enabled: bool) -> None:
        if enabled and not self.memory:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )
        elif not enabled and self.memory:
            await self.memory.close()
            self.memory = None
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
                        cfg, config=self.config, gmail=self.get_gmail,
                    )
                except Exception:
                    _logger.exception("Failed to create notifier %r", cfg.name)
        self.rebuild_executor()

    async def connect(self) -> None:
        if self._connected:
            return

        self.config.db_dir.mkdir(exist_ok=True)

        self._sessions_conn = await database.connect(self.config.sessions_db_path)
        self.session_store = SessionStore(self._sessions_conn)
        await self.session_store.init_schema()

        self.schedule_store = ScheduleStore(self._sessions_conn)
        await self.schedule_store.init_schema()

        self.notifier_store = NotifierStore(self._sessions_conn)
        await self.notifier_store.init_schema()

        await self.indexer.connect()

        self.channel.subscribe(ToolExecuted, self.dashboard.on_tool_executed)
        self.channel.subscribe(RunStarted, self.dashboard.on_run_started)
        self.channel.subscribe(RunCompleted, self.dashboard.on_run_completed)
        self.channel.subscribe(FactCreated, self.dashboard.on_fact_created)
        self.channel.subscribe(ConsolidationCompleted, self.dashboard.on_consolidation_completed)
        self.channel.subscribe(FactCreated, self._on_fact_created)
        self.channel.subscribe(FactUpdated, self._on_fact_updated)
        self.channel.subscribe(FactDeleted, self._on_fact_deleted)
        self.channel.subscribe(MemoryCleared, self._on_memory_cleared)
        self.channel.subscribe(SourceChanged, self._on_source_changed)
        self.channel.subscribe(ScheduleCompleted, make_schedule_dispatcher(lambda: self.notifiers))

        if self.config.memory:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
                channel=self.channel,
            )

        self.skill_registry.load([
            (Path.cwd() / ".skills", "project"),
            (NTRP_DIR / "skills", "global"),
        ])

        await self.rebuild_notifiers()
        self._connected = True

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
        self, session_state: SessionState, messages: list[dict], metadata: dict | None = None,
    ) -> None:
        try:
            session_state.last_activity = datetime.now(UTC)
            await self.session_store.save_session(session_state, messages, metadata=metadata)
        except Exception as e:
            _logger.warning("Failed to save session: %s", e)

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
        return await self.indexer.get_status()

    async def _on_fact_created(self, event: FactCreated) -> None:
        await self.indexer.index.upsert(
            source="memory",
            source_id=f"fact:{event.fact_id}",
            title=event.text[:50],
            content=event.text,
        )

    async def _on_fact_updated(self, event: FactUpdated) -> None:
        await self.indexer.index.upsert(
            source="memory",
            source_id=f"fact:{event.fact_id}",
            title=event.text[:50],
            content=event.text,
        )

    async def _on_fact_deleted(self, event: FactDeleted) -> None:
        await self.indexer.index.delete("memory", f"fact:{event.fact_id}")

    async def _on_memory_cleared(self, _event: MemoryCleared) -> None:
        await self.indexer.index.clear_source("memory")

    async def _on_source_changed(self, event: SourceChanged) -> None:
        async with self._config_lock:
            self.rebuild_executor()
        name = event.source_name
        if name not in INDEXABLE_SOURCES:
            return
        source_active = (name == "notes" and "notes" in self.source_mgr.sources) or (
            name == "memory" and self.memory is not None
        )
        if source_active:
            self.start_indexing()
        else:
            await self.indexer.index.clear_source(name)

    async def close(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        if self.memory:
            await self.memory.close()
        if self._sessions_conn:
            await self._sessions_conn.close()
        await self.indexer.stop()
        await self.indexer.close()

        await litellm_main.base_llm_aiohttp_handler.close()
        await litellm_cleanup.close_litellm_async_clients()


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
