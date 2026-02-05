import asyncio
from datetime import datetime
from typing import Any

from ntrp.config import Config
from ntrp.constants import AGENT_DEFAULT_ITERATIONS, AGENT_MAX_DEPTH
from ntrp.context.compression import SessionManager
from ntrp.context.models import SessionData, SessionState
from ntrp.context.store import SessionStore
from ntrp.embedder import EmbeddingConfig
from ntrp.memory.facts import FactMemory
from ntrp.server.indexer import Indexer
from ntrp.sources.browser import BrowserHistorySource
from ntrp.sources.exa import WebSource
from ntrp.sources.google.calendar import MultiCalendarSource
from ntrp.sources.google.gmail import MultiGmailSource
from ntrp.sources.memory import MemoryIndexSource
from ntrp.sources.obsidian import ObsidianSource
from ntrp.tools.executor import ToolExecutor


class Runtime:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()

        self._source_errors: dict[str, str] = {}
        self._sources: dict[str, Any] = {}
        self._init_sources()

        self.embedding = EmbeddingConfig(
            model=self.config.embedding_model,
            dim=self.config.embedding_dim,
            prefix=self.config.embedding_prefix,
        )
        self.indexer = Indexer(db_path=self.config.search_db_path, embedding=self.embedding)

        self.session_store = SessionStore(self.config.sessions_db_path)
        self.session_manager = SessionManager(model=self.config.chat_model)

        self.memory: FactMemory | None = None
        self.executor: ToolExecutor | None = None
        self.tools: list[dict] = []

        self.gmail: MultiGmailSource | None = self._sources.get("email")
        self.browser: BrowserHistorySource | None = self._sources.get("browser")

        self.max_depth = AGENT_MAX_DEPTH
        self.max_iterations = AGENT_DEFAULT_ITERATIONS

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
            except Exception:
                pass

    async def connect(self) -> None:
        if self._connected:
            return

        await self.session_store.connect()
        await self.indexer.connect()

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

    def create_session(self, user_id: str | None = None) -> SessionState:
        return SessionState(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now(),
            user_id=user_id or self.config.user_id,
        )

    async def restore_session(self, user_id: str | None = None) -> SessionData | None:
        try:
            data = await self.session_store.get_latest_session(user_id=user_id or self.config.user_id)
        except Exception:
            return None

        if not data:
            return None

        age_hours = (datetime.now() - data.state.last_activity).total_seconds() / 3600
        if age_hours > 24:
            return None

        if not data.messages or len(data.messages) < 2:
            return None

        return data

    async def save_session(self, session_state: SessionState, messages: list[dict]) -> None:
        try:
            session_state.last_activity = datetime.now()
            await self.session_store.save_session(session_state, messages)
        except Exception:
            pass

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
