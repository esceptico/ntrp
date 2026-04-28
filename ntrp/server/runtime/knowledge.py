from ntrp.config import Config
from ntrp.integrations import IntegrationRegistry
from ntrp.integrations.types import Indexable
from ntrp.logging import get_logger
from ntrp.memory.facts import FactMemory
from ntrp.memory.indexable import MemoryIndexable
from ntrp.memory.service import MemoryService
from ntrp.server.indexer import Indexer
from ntrp.server.stores import Stores

_logger = get_logger(__name__)


class KnowledgeRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.embedding = config.embedding
        self.indexer = Indexer(db_path=config.search_db_path, embedding=self.embedding) if self.embedding else None
        self.search_index = None
        self.memory: FactMemory | None = None
        self.memory_service: MemoryService | None = None
        self.indexables: dict[str, Indexable] = {}

    @property
    def memory_ready(self) -> bool:
        return bool(self.config.memory and self.embedding and self.config.memory_model)

    async def connect(self, stores: Stores, integrations: IntegrationRegistry) -> None:
        await self._init_search()
        self.sync_indexables(integrations, start_if_changed=False)
        await self._init_memory(stores)

    async def reload_config(self, config: Config, stores: Stores, integrations: IntegrationRegistry) -> None:
        self.config = config
        await self._sync_embedding()
        await self._sync_memory(stores)
        self.sync_indexables(integrations)

    async def stop(self) -> None:
        if self.indexer:
            await self.indexer.stop()

    async def close(self) -> None:
        await self._close_memory()
        if self.indexer:
            await self.indexer.close()

    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = {}
        if self.memory:
            services["memory"] = self.memory
        if self.search_index:
            services["search_index"] = self.search_index
        return services

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(list(self.indexables.values()))

    async def get_index_status(self) -> dict:
        status = await self.indexer.get_status() if self.indexer else {"status": "disabled"}
        if self.memory:
            status["reembedding"] = self.memory.reembed_running
            status["reembed_progress"] = self.memory.reembed_progress
        return status

    async def _init_search(self) -> None:
        if self.indexer:
            await self.indexer.connect()
            self.search_index = self.indexer.index

    async def _init_memory(self, stores: Stores) -> None:
        if self.memory_ready:
            await self._create_memory(stores)
            self.indexables["memory"] = MemoryIndexable(self.memory.db)
        elif self.config.memory:
            _logger.warning("Memory enabled but no embedding model configured — skipping")

    async def _create_memory(self, stores: Stores) -> None:
        self.memory = await FactMemory.create(
            db_path=self.config.memory_db_path,
            embedding=self.embedding,
            model=self.config.memory_model,
            enqueue_fact_index_upsert=stores.outbox.enqueue_fact_index_upsert,
            enqueue_fact_index_delete=stores.outbox.enqueue_fact_index_delete,
        )
        self.memory.dreams_enabled = self.config.dreams
        self.memory_service = MemoryService(
            self.memory,
            enqueue_fact_index_upsert=stores.outbox.enqueue_fact_index_upsert,
            enqueue_fact_index_delete=stores.outbox.enqueue_fact_index_delete,
            enqueue_memory_index_clear=stores.outbox.enqueue_memory_index_clear,
        )

    async def _close_memory(self) -> None:
        if self.memory:
            await self.memory.close()
        self.memory = None
        self.memory_service = None

    async def _sync_memory(self, stores: Stores) -> None:
        if self.memory_ready and not self.memory:
            await self._create_memory(stores)
        elif self.config.memory and self.memory:
            if not self.memory_ready:
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

    def sync_indexables(self, integrations: IntegrationRegistry, *, start_if_changed: bool = True) -> None:
        prev = set(self.indexables.keys())
        self.indexables.clear()
        for name, client in integrations.clients.items():
            if isinstance(client, Indexable):
                self.indexables[name] = client
        if self.memory:
            self.indexables["memory"] = MemoryIndexable(self.memory.db)
        if start_if_changed and set(self.indexables.keys()) != prev:
            self.start_indexing()
