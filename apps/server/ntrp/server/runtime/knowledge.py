from ntrp.config import Config
from ntrp.logging import get_logger
from ntrp.memory.buffers_store import EpisodeBufferRepository
from ntrp.memory.connectors.chat import ChatConnector
from ntrp.memory.connectors.claim_writer import CompletionClaimAdjudicateClient, CompletionClaimExtractClient
from ntrp.memory.connectors.entity_linker import (
    CompletionEntityLinkAdjudicateClient,
    CompletionMentionExtractClient,
)
from ntrp.memory.connectors.episode_close import CompletionDedupClient, CompletionSummaryClient
from ntrp.memory.contradictions import ContradictionWatcher
from ntrp.memory.episodes import EpisodeBoundaryClassifier
from ntrp.memory.items_store import MemoryItemsRepository
from ntrp.memory.learnings import LearningsStore
from ntrp.memory.lens_author import LensAuthor, LensAuthorClient
from ntrp.memory.lens_pass import LensExtractionClient, LensPass
from ntrp.memory.pattern_finder import PatternFinder
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.runtime import MemoryDatabase
from ntrp.memory.search_source import MemorySearchSource
from ntrp.memory.service import MemoryService
from ntrp.memory.skill_inducer import SkillInducer
from ntrp.server.indexer import Indexer
from ntrp.server.stores import Stores

_logger = get_logger(__name__)


class KnowledgeRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.embedding = config.embedding
        self.indexer = Indexer(db_path=config.search_db_path, embedding=self.embedding) if self.embedding else None
        self.search_index = None
        self.memory: MemoryDatabase | None = None
        self.memory_service: MemoryService | None = None
        self.memory_search_source: MemorySearchSource | None = None
        self.memory_retrieval: MemoryRetrieval | None = None
        self.memory_items: MemoryItemsRepository | None = None
        self.pattern_finder: PatternFinder | None = None
        self.lens_pass: LensPass | None = None
        self.lens_author: LensAuthor | None = None
        self.chat_connector: ChatConnector | None = None

    @property
    def memory_ready(self) -> bool:
        return bool(self.config.memory and self.embedding and self.config.memory_model)

    async def connect(self, stores: Stores) -> None:
        await self._init_search()
        await self._init_memory(stores)

    async def reload_config(self, config: Config, stores: Stores | None) -> None:
        had_source = self.memory_search_source is not None
        self.config = config
        await self._sync_embedding()
        if stores is None:
            return
        await self._sync_memory(stores)
        if had_source != (self.memory_search_source is not None):
            self.start_indexing()

    async def stop(self) -> None:
        if self.indexer:
            await self.indexer.stop()

    async def close(self) -> None:
        await self._close_memory()
        if self.indexer:
            await self.indexer.close()

    def tool_services(self) -> dict[str, object]:
        services: dict[str, object] = {}
        if self.memory_service:
            services["memory"] = self.memory_service
        if self.memory_retrieval:
            services["memory_retrieval"] = self.memory_retrieval
        if self.memory_items:
            services["memory_items"] = self.memory_items
        if self.memory and getattr(self.memory, "embedder", None):
            services["embedder"] = self.memory.embedder
        if self.pattern_finder:
            services["pattern_finder"] = self.pattern_finder
        if self.search_index:
            services["search_index"] = self.search_index
        return services

    def start_indexing(self) -> None:
        if self.indexer:
            self.indexer.start(self.memory_search_source)

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
        elif self.config.memory:
            _logger.warning("Memory enabled but no embedding model configured — skipping")

    async def _create_memory(self, stores: Stores) -> None:
        self.memory = await MemoryDatabase.create(
            db_path=self.config.memory_db_path,
            embedding=self.embedding,
            model=self.config.memory_model,
        )
        self.memory_service = MemoryService(self.memory)
        self.memory_search_source = MemorySearchSource(self.memory.db)
        self.memory_retrieval = MemoryRetrieval(self.memory.db.conn, self.memory.embedder)
        memory_items = MemoryItemsRepository(self.memory.db.conn)
        self.memory_items = memory_items
        summary_client = CompletionSummaryClient(self.config.memory_model)
        skill_inducer = SkillInducer(
            repo=memory_items,
            draft_client=summary_client,
            embedder=self.memory.embedder,
        )
        contradiction_watcher = ContradictionWatcher(
            repo=memory_items,
            embedder=self.memory.embedder,
            judge_client=summary_client,
            learnings=LearningsStore(),
        )
        self.pattern_finder = PatternFinder(
            repo=memory_items,
            summary_client=summary_client,
            embedder=self.memory.embedder,
            contradiction_watcher=contradiction_watcher,
        )
        self.pattern_finder.skill_inducer = skill_inducer
        self.lens_pass = LensPass(repo=memory_items, client=LensExtractionClient(self.config.memory_model))
        self.lens_author = LensAuthor(
            repo=memory_items,
            retrieval=self.memory_retrieval,
            lens_pass=self.lens_pass,
            client=LensAuthorClient(self.config.memory_model),
        )
        self.chat_connector = ChatConnector(
            items=MemoryItemsRepository(self.memory.db.conn),
            buffers=EpisodeBufferRepository(self.memory.db.conn),
            embedder=self.memory.embedder,
            llm_client=CompletionSummaryClient(self.config.memory_model),
            boundary_classifier=EpisodeBoundaryClassifier(),
            dedup_client=CompletionDedupClient(self.config.memory_model),
            learnings=LearningsStore(),
            claim_extract_client=CompletionClaimExtractClient(self.config.memory_model),
            claim_adjudicate_client=CompletionClaimAdjudicateClient(self.config.memory_model),
            mention_extract_client=CompletionMentionExtractClient(self.config.memory_model),
            entity_link_client=CompletionEntityLinkAdjudicateClient(self.config.memory_model),
            watcher=contradiction_watcher,
        )
        self.memory_service.chat_connector = self.chat_connector  # type: ignore[attr-defined]
        self.memory_service.register_connector(self.chat_connector)

    async def _close_memory(self) -> None:
        if self.memory:
            await self.memory.close()
        self.memory = None
        self.memory_service = None
        self.memory_search_source = None
        self.memory_retrieval = None
        self.memory_items = None
        self.pattern_finder = None
        self.lens_pass = None
        self.lens_author = None
        self.chat_connector = None

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
                if self.chat_connector:
                    self.chat_connector.llm_client = CompletionSummaryClient(self.config.memory_model)
                    self.chat_connector.dedup_client = CompletionDedupClient(self.config.memory_model)
                    self.chat_connector.claim_extract_client = CompletionClaimExtractClient(self.config.memory_model)
                    self.chat_connector.claim_adjudicate_client = CompletionClaimAdjudicateClient(
                        self.config.memory_model
                    )
                    self.chat_connector.mention_extract_client = CompletionMentionExtractClient(
                        self.config.memory_model
                    )
                    self.chat_connector.entity_link_client = CompletionEntityLinkAdjudicateClient(
                        self.config.memory_model
                    )
                if self.pattern_finder:
                    self.pattern_finder.summary_client = CompletionSummaryClient(self.config.memory_model)
        elif not self.config.memory and self.memory:
            await self._close_memory()

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

        if self.memory:
            self.memory.start_reembed(new_embedding, rebuild=True)
