from ntrp.config import Config
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
        self.memory = None
        self.memory_service = None
        self.memory_search_source = None
        self.memory_retrieval = None
        self.memory_items = None
        self.pattern_finder = None
        self.lens_pass = None
        self.lens_author = None
        self.chat_connector = None

    @property
    def memory_ready(self) -> bool:
        return False

    async def connect(self, stores: Stores) -> None:
        await self._init_search()

    async def reload_config(self, config: Config, stores: Stores | None) -> None:
        self.config = config
        await self._sync_embedding()

    async def stop(self) -> None:
        if self.indexer:
            await self.indexer.stop()

    async def close(self) -> None:
        if self.indexer:
            await self.indexer.close()

    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = {}
        if self.search_index:
            services["search_index"] = self.search_index
        return services

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(self.memory_search_source)

    async def get_index_status(self) -> dict:
        return await self.indexer.get_status() if self.indexer else {"status": "disabled"}

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
