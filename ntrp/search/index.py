from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from ntrp.constants import RRF_K
from ntrp.database import serialize_embedding
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.search.retrieval import HybridRetriever
from ntrp.search.store import SearchStore
from ntrp.search.types import SearchResult
from ntrp.sources.models import RawItem

_logger = get_logger(__name__)


class SyncResult(NamedTuple):
    updated: int
    deleted: int


type ProgressCallback = Callable[[int, int], None]


class SearchIndex:
    EMBED_SOURCES = {"notes", "memory"}

    def __init__(
        self,
        db_path: Path,
        embedding: EmbeddingConfig,
        rrf_k: int = RRF_K,
        vector_weight: float = 0.5,
        fts_weight: float = 0.5,
        store: SearchStore | None = None,
        embedder: Embedder | None = None,
    ):
        self.store = store or SearchStore(db_path, embedding.dim)
        self.embedder = embedder or Embedder(embedding)
        self.retriever = HybridRetriever(
            store=self.store,
            embedder=self.embedder,
            rrf_k=rrf_k,
            vector_weight=vector_weight,
            fts_weight=fts_weight,
        )

    async def connect(self) -> None:
        await self.store.connect()

    async def close(self) -> None:
        await self.store.close()

    def should_embed(self, source: str) -> bool:
        return source in self.EMBED_SOURCES

    async def upsert(
        self,
        source: str,
        source_id: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> bool:
        content_hash = SearchStore.hash_content(content)

        if await self.store.exists_with_hash(source, source_id, content_hash):
            return False

        embedding = await self.embedder.embed_one(f"{title}\n{content}")
        embedding_bytes = serialize_embedding(embedding)

        return await self.store.upsert(source, source_id, title, content, embedding_bytes, metadata)

    async def delete(self, source: str, source_id: str) -> bool:
        return await self.store.delete(source, source_id)

    async def sync(
        self,
        source_name: str,
        items: list[RawItem],
        progress_callback: ProgressCallback | None = None,
        batch_size: int = 50,
    ) -> SyncResult:
        if not self.should_embed(source_name):
            return SyncResult(0, 0)

        indexed = await self.store.get_indexed_hashes(source_name)
        current_ids = {item.source_id for item in items}

        deleted = 0
        for source_id in set(indexed.keys()) - current_ids:
            await self.store.delete(source_name, source_id)
            deleted += 1

        items_to_embed: list[RawItem] = []
        total = len(items)

        for i, item in enumerate(items):
            if progress_callback:
                progress_callback(i + 1, total)

            content_hash = SearchStore.hash_content(item.content)
            if item.source_id in indexed and indexed[item.source_id][1] == content_hash:
                continue

            items_to_embed.append(item)

        updated = 0
        for batch_start in range(0, len(items_to_embed), batch_size):
            batch = items_to_embed[batch_start : batch_start + batch_size]

            texts = [f"{item.title}\n{item.content}" for item in batch]
            embeddings = await self.embedder.embed(texts)

            for item, embedding in zip(batch, embeddings):
                embedding_bytes = serialize_embedding(embedding)
                await self.store.upsert(source_name, item.source_id, item.title, item.content, embedding_bytes)
                updated += 1

        return SyncResult(updated, deleted)

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        results = await self.retriever.search(query, sources, limit)

        search_results: list[SearchResult] = []
        for r in results:
            item = await self.store.get_by_id(r.row_id)
            if item:
                search_results.append(
                    SearchResult(
                        source=item.source,
                        source_id=item.source_id,
                        title=item.title,
                        snippet=item.snippet,
                        metadata=item.metadata,
                        vector_score=r.vector_score,
                        vector_rank=r.vector_rank,
                        fts_score=r.fts_score,
                        fts_rank=r.fts_rank,
                        rrf_score=r.rrf_score,
                    )
                )

        return search_results

    async def get_stats(self) -> dict[str, int]:
        return await self.store.get_stats()

    async def clear_source(self, source: str) -> int:
        return await self.store.clear_source(source)

    async def clear(self) -> int:
        return await self.store.clear_all()
