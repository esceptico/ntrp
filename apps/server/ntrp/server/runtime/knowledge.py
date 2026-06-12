from ntrp.config import Config
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.server.indexer import Indexer
from ntrp.server.stores import Stores

_logger = get_logger(__name__)


class KnowledgeRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.embedding = config.embedding
        self.indexer = Indexer(db_path=config.search_db_path, embedding=self.embedding) if self.embedding else None
        self.search_index = None
        self.memory_curator = None
        self.chat_connector = None

        self._record_store = None
        self._lens_store = None
        self._consolidate = None

    @property
    def memory_ready(self) -> bool:
        return self._record_store is not None

    async def connect(self, stores: Stores) -> None:
        await self._init_search()
        await self._init_memory(stores)
        if self.search_index is not None:
            stores.sessions.store.attach_search_index(self.search_index)
        if self.memory_curator is not None:
            self.memory_curator.start_sweep()

    async def reload_config(self, config: Config, stores: Stores | None) -> None:
        self.config = config
        await self._sync_embedding()
        # Re-wire the live transcript store to the (possibly new/None) index so
        # toggling embedding at runtime enables/disables hybrid search + indexing
        # without a restart. attach_search_index is idempotent and clears on None.
        if stores is not None:
            stores.sessions.store.attach_search_index(self.search_index)
        # Same re-wire for the record store (the lens store + curator share it).
        if self._record_store is not None:
            self._record_store.attach_search_index(self.search_index)

    async def stop(self) -> None:
        if self.memory_curator:
            await self.memory_curator.stop()
        if self._consolidate:
            await self._consolidate.close()
        if self._record_store:
            await self._record_store.close()
        if self._lens_store:
            await self._lens_store.close()
        if self.indexer:
            await self.indexer.stop()

    async def close(self) -> None:
        if self._consolidate:
            await self._consolidate.close()
        if self._record_store:
            await self._record_store.close()
        if self._lens_store:
            await self._lens_store.close()
        if self.indexer:
            await self.indexer.close()

    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = {}
        if self.search_index:
            services["search_index"] = self.search_index
        if self._record_store is not None:
            from ntrp.tools.memory import MEMORY_RECORDS_SERVICE

            services[MEMORY_RECORDS_SERVICE] = self._record_store
        # The lens store is NOT a tool service — it's reached only via REST.
        return services

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(None)

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

    # --- flat-records + lenses memory ------------------------------------

    async def _init_memory(self, stores: Stores) -> None:
        if not self.config.memory:
            _logger.info("memory disabled by config")
            return

        from ntrp.memory.consolidate import Consolidate
        from ntrp.memory.curator import Curator
        from ntrp.memory.lenses import LensStore
        from ntrp.memory.records import RecordStore

        # Flat record pool (rows in memory.db, vectors via the shared index).
        self._record_store = RecordStore(
            db_path=self.config.memory_db_path,
            search_index=self.search_index,
        )

        memory_llm = (
            get_completion_client(self.config.memory_model)
            if self.config.memory_model
            else None
        )
        memory_effort = self._memory_reasoning_effort(self.config.memory_model)

        # Lenses: named views over records, membership LLM-scored + cached.
        self._lens_store = LensStore(
            db_path=self.config.memory_db_path,
            records=self._record_store,
            llm=memory_llm,
            model=self.config.memory_model,
            reasoning_effort=memory_effort,
        )

        # CONSOLIDATE/LINT — the background pass that turns the raw record pile
        # into the actual memory (merge/supersede/drop). O(delta), watermark-durable.
        self._consolidate = Consolidate(
            self._record_store,
            memory_llm,
            model=self.config.memory_model,
            db_path=self.config.memory_db_path,
            reasoning_effort=memory_effort,
        )

        if self.config.memory_model:
            self.memory_curator = Curator(
                memory_llm,
                stores.sessions,
                model=self.config.memory_model,
                db_path=self.config.memory_db_path,
                record_store=self._record_store,
                consolidate=self._consolidate,
                reasoning_effort=memory_effort,
            )
        else:
            _logger.warning("memory enabled but no memory_model; curator disabled")

        # Run the record-store schema migration NOW, serially, while it is the
        # only open connection to memory.db. Deferring it to the first lazy
        # _ensure_conn lets the lens/consolidate/curator connections race the
        # one-time DROP/ALTER rebuild (writer-vs-writer lock contention).
        await self._record_store.open()

        _logger.info("memory ready", db_path=str(self.config.memory_db_path))

    def _memory_reasoning_effort(self, model_id: str | None) -> str | None:
        """Effort for memory's structured calls: the user's configured effort if set,
        else 'low' (or the model's lowest) so a reasoning model doesn't run at its slow
        API-default and time out. Returns None for non-reasoning models."""
        if not model_id:
            return None
        configured = self.config.reasoning_effort_for(model_id)
        if configured:
            return configured
        from ntrp.llm.models import get_models

        efforts = get_models()[model_id].reasoning_efforts
        if not efforts:
            return None
        return "low" if "low" in efforts else efforts[0]
