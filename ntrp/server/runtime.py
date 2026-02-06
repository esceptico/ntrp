import asyncio
from datetime import datetime
from typing import Any

from ntrp.config import Config, get_config
from ntrp.constants import AGENT_MAX_DEPTH, SESSION_EXPIRY_HOURS
from ntrp.logging import get_logger
from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.memory.facts import FactMemory
from ntrp.schedule.scheduler import Scheduler
from ntrp.schedule.store import ScheduleStore
from ntrp.server.indexer import Indexer
from ntrp.sources.browser import BrowserHistorySource
from ntrp.sources.exa import WebSource
from ntrp.sources.google.calendar import MultiCalendarSource
from ntrp.sources.google.gmail import MultiGmailSource
from ntrp.sources.memory import MemoryIndexSource
from ntrp.sources.obsidian import ObsidianSource
from ntrp.tools.executor import ToolExecutor
from ntrp.tools.schedule import CancelScheduleTool, GetScheduleResultTool, ListSchedulesTool, ScheduleTaskTool

logger = get_logger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()

        self._source_errors: dict[str, str] = {}
        self._sources: dict[str, Any] = {}
        self._init_sources()

        self.embedding = self.config.embedding
        self.indexer = Indexer(db_path=self.config.search_db_path, embedding=self.embedding)

        self.session_store = SessionStore(self.config.sessions_db_path)

        self.memory: FactMemory | None = None
        self.executor: ToolExecutor | None = None
        self.tools: list[dict] = []

        self.gmail: MultiGmailSource | None = self._sources.get("email")
        self.browser: BrowserHistorySource | None = self._sources.get("browser")

        self.max_depth = AGENT_MAX_DEPTH
        self.schedule_store: ScheduleStore | None = None
        self.scheduler: Scheduler | None = None

        self._connected = False

    def _init_sources(self) -> None:
        source_classes = [
            ObsidianSource,
            BrowserHistorySource,
            MultiGmailSource,
            MultiCalendarSource,
            WebSource,
        ]

        for cls in source_classes:
            try:
                source = cls()
                if source.errors:
                    self._source_errors[source.name] = "; ".join(f"{k}: {v}" for k, v in source.errors.items())
                self._sources[source.name] = source
            except Exception as e:
                logger.warning("Failed to init source %s: %s", cls.__name__, e)

    async def connect(self) -> None:
        if self._connected:
            return

        self.config.db_dir.mkdir(exist_ok=True)
        await self.session_store.connect()
        await self.indexer.connect()

        # Schedule store shares sessions DB connection
        self.schedule_store = ScheduleStore(self.session_store.conn)
        await self.schedule_store.init_schema()

        if self.config.memory:
            self.memory = await FactMemory.create(
                db_path=self.config.memory_db_path,
                embedding=self.embedding,
                extraction_model=self.config.memory_model,
            )

        self.executor = ToolExecutor(
            sources=self._sources,
            memory=self.memory,
            model=self.config.chat_model,
            search_index=self.indexer.index,
        )

        # Register schedule tools
        default_email = self.config.schedule_email
        if not default_email and self.gmail:
            accounts = self.gmail.list_accounts()
            default_email = accounts[0] if accounts else None

        self.executor.registry.register(ScheduleTaskTool(self.schedule_store, default_email))
        self.executor.registry.register(ListSchedulesTool(self.schedule_store))
        self.executor.registry.register(CancelScheduleTool(self.schedule_store))
        self.executor.registry.register(GetScheduleResultTool(self.schedule_store))

        self.tools = self.executor.get_tools()
        self._connected = True

    def get_source_details(self) -> dict[str, dict]:
        return {name: source.details for name, source in self._sources.items()}

    def get_source_errors(self) -> dict[str, str]:
        errors = dict(self._source_errors)
        if self.indexer.error:
            errors["index"] = self.indexer.error
        return errors

    def get_available_sources(self) -> list[str]:
        sources = list(self._sources.keys())
        if self.memory:
            sources.append("memory")
        return sources

    def create_session(self) -> SessionState:
        return SessionState(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now(),
        )

    async def restore_session(self) -> SessionData | None:
        try:
            data = await self.session_store.get_latest_session()
        except Exception as e:
            logger.warning("Failed to restore session: %s", e)
            return None

        if not data:
            return None

        age_hours = (datetime.now() - data.state.last_activity).total_seconds() / 3600
        if age_hours > SESSION_EXPIRY_HOURS:
            return None

        if not data.messages or len(data.messages) < 2:
            return None

        return data

    async def save_session(self, session_state: SessionState, messages: list[dict]) -> None:
        try:
            session_state.last_activity = datetime.now()
            await self.session_store.save_session(session_state, messages)
        except Exception as e:
            logger.warning("Failed to save session: %s", e)

    def start_scheduler(self) -> None:
        if self.schedule_store:
            self.scheduler = Scheduler(self, self.schedule_store)
            self.scheduler.start()

    def start_consolidation(self) -> None:
        if self.memory:
            self.memory.start_consolidation()

    def start_indexing(self) -> None:
        sources = []
        if notes := self._sources.get("notes"):
            sources.append(notes)
        if self.memory:
            sources.append(MemoryIndexSource(self.memory.db))
        self.indexer.start(sources)

    async def get_index_status(self) -> dict:
        return await self.indexer.get_status()

    async def close(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        if self.memory:
            await self.memory.close()
        await self.session_store.close()
        await self.indexer.close()


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


async def reset_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.close()
        _runtime = None
