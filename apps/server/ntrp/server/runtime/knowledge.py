from ntrp.config import Config
from ntrp.database import connect as db_connect
from ntrp.embedder import Embedder
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Scope, ScopeKind
from ntrp.memory.pipeline.runtime import MemoryPipeline, MemoryPipelineConfig
from ntrp.memory.store import MemoryStore
from ntrp.server.indexer import Indexer
from ntrp.server.stores import Stores

_logger = get_logger(__name__)


class _CaptureSession:
    """Flatten a SessionData into the attribute shape CaptureService reads.

    CaptureService reads `session_id`/`messages`/`last_activity`/`session_type`/
    `origin_automation_id`/`project_id` directly; SessionData keeps the metadata
    on `.state`. This adapter bridges the two without touching either side.
    """

    def __init__(self, data):
        state = data.state
        self.session_id = state.session_id
        self.messages = data.messages
        self.last_activity = state.last_activity
        self.session_type = state.session_type
        self.origin_automation_id = state.origin_automation_id
        self.project_id = state.project_id


class _CaptureSessions:
    def __init__(self, session_store):
        self._store = session_store

    async def load_session(self, session_id: str):
        data = await self._store.load_session(session_id)
        return _CaptureSession(data) if data is not None else None

    async def recent_session_ids(self, limit: int) -> list[str]:
        """Most-recently-active, non-archived session ids — the periodic sweep's
        work-list (the memory pipeline's background ingest of idle/automation sessions)."""
        rows = await self._store.list_sessions(limit=limit)
        return [r["session_id"] for r in rows if r.get("session_id")]


class KnowledgeRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.embedding = config.embedding
        self.indexer = Indexer(db_path=config.search_db_path, embedding=self.embedding) if self.embedding else None
        self.search_index = None
        self.memory = None
        self.memory_service = None
        self.memory_reader = None
        self.memory_search_source = None
        self.memory_retrieval = None
        self.memory_items = None
        self.pattern_finder = None
        self.lens_service = None
        self.lens_pass = None
        self.lens_author = None
        self.chat_connector = None

        self._memory_conn = None
        self._memory_pipeline: MemoryPipeline | None = None

    @property
    def memory_ready(self) -> bool:
        return self._memory_pipeline is not None

    async def connect(self, stores: Stores) -> None:
        await self._init_search()
        await self._init_memory(stores)

    async def reload_config(self, config: Config, stores: Stores | None) -> None:
        self.config = config
        await self._sync_embedding()

    async def stop(self) -> None:
        if self._memory_pipeline:
            await self._memory_pipeline.stop()
        if self.indexer:
            await self.indexer.stop()

    async def close(self) -> None:
        if self.indexer:
            await self.indexer.close()
        if self._memory_conn is not None:
            await self._memory_conn.close()
            self._memory_conn = None

    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = {}
        if self.search_index:
            services["search_index"] = self.search_index
        if self.memory_service is not None:
            from ntrp.tools.memory import MEMORY_WRITE_SERVICE

            services[MEMORY_WRITE_SERVICE] = self.memory_service
        if self.memory_reader is not None:
            from ntrp.tools.memory import MEMORY_READ_SERVICE

            services[MEMORY_READ_SERVICE] = self.memory_reader
        if self.lens_service is not None:
            from ntrp.memory.lens import MEMORY_LENS_SERVICE

            services[MEMORY_LENS_SERVICE] = self.lens_service
        return services

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(self.memory_search_source)

    async def get_index_status(self) -> dict:
        return await self.indexer.get_status() if self.indexer else {"status": "disabled"}

    # --- search index ----------------------------------------------------

    async def _init_search(self) -> None:
        if self.indexer:
            await self.indexer.connect()
            self.search_index = self.indexer.index

    async def _sync_embedding(self) -> None:
        new_embedding = self.config.embedding
        if new_embedding == self.embedding:
            return

        self.embedding = new_embedding

        if new_embedding is None:
            if self.indexer:
                await self.indexer.stop()
                await self.indexer.close()
            self.indexer = None
            self.search_index = None
            return

        if self.indexer:
            await self.indexer.stop()
            await self.indexer.update_embedding(new_embedding)
        else:
            self.indexer = Indexer(db_path=self.config.search_db_path, embedding=new_embedding)
            await self.indexer.connect()
        self.search_index = self.indexer.index

    # --- memory pipeline -------------------------------------------------

    async def _init_memory(self, stores: Stores) -> None:
        if not self.config.memory:
            _logger.info("memory disabled by config")
            return
        if self.embedding is None:
            _logger.warning("memory enabled but no embedding model; pipeline not started")
            return
        if not self.config.memory_model or not self.config.chat_model:
            _logger.warning("memory enabled but model ids missing; pipeline not started")
            return

        conn = await db_connect(self.config.memory_db_path)
        store = MemoryStore(conn)
        await store.init_schema()
        self._memory_conn = conn

        pipeline = MemoryPipeline(
            store=store,
            embed=Embedder(self.embedding),
            cheap_llm=get_completion_client(self.config.memory_model),
            strong_llm=get_completion_client(self.config.chat_model),
            raw_sessions=_CaptureSessions(stores.sessions.store),
            raw_automations=None,
            config=MemoryPipelineConfig(
                cheap_model=self.config.memory_model,
                strong_model=self.config.chat_model,
                consolidation_interval=self.config.consolidation_interval,
            ),
            eligible_scopes=self._eligible_scopes,
        )
        pipeline.start_background()

        self._memory_pipeline = pipeline
        self.memory = store
        self.memory_service = pipeline.write_seam
        self.memory_reader = pipeline.retriever
        self.memory_retrieval = pipeline
        self.lens_service = pipeline.lens_registry
        _logger.info("memory pipeline ready", db=str(self.config.memory_db_path))

    def _eligible_scopes(self) -> list[Scope]:
        """Scopes the background lint sweep visits each tick.

        USER is always present (the principal). Project scopes are discovered
        lazily from the store's active lenses so the sweep stays O(delta).
        """
        return [Scope(kind=ScopeKind.USER)]
