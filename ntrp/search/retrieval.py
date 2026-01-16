from ntrp.database import serialize_embedding
from ntrp.embedder import Embedder
from ntrp.logging import get_logger
from ntrp.search.store import SearchStore
from ntrp.search.types import RankedResult, ScoredRow

logger = get_logger(__name__)


class HybridRetriever:
    def __init__(
        self,
        store: SearchStore,
        embedder: Embedder,
        rrf_k: int = 60,
        vector_weight: float = 0.5,
        fts_weight: float = 0.5,
    ):
        self.store = store
        self.embedder = embedder
        self.rrf_k = rrf_k
        self.vector_weight = vector_weight
        self.fts_weight = fts_weight

    async def _vector_search(
        self,
        query_embedding: bytes,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[ScoredRow]:
        results = await self.store.vector_search(query_embedding, sources, limit * 2)
        scored = [ScoredRow(row_id=row_id, score=score) for row_id, score in results]
        for i, row in enumerate(scored):
            row.rank = i + 1
        return scored

    async def _fts_search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[ScoredRow]:
        results = await self.store.fts_search(query, sources, limit * 2)
        scored = [ScoredRow(row_id=row_id, score=score) for row_id, score in results]
        for i, row in enumerate(scored):
            row.rank = i + 1
        return scored

    def _rrf_merge(
        self,
        vector_results: list[ScoredRow],
        fts_results: list[ScoredRow],
    ) -> list[RankedResult]:
        vector_lookup = {r.row_id: (r.rank, r.score) for r in vector_results}
        fts_lookup = {r.row_id: (r.rank, r.score) for r in fts_results}

        all_ids = set(vector_lookup.keys()) | set(fts_lookup.keys())
        results: list[RankedResult] = []

        for row_id in all_ids:
            rrf_score = 0.0
            vector_rank, vector_score = vector_lookup.get(row_id, (None, None))
            fts_rank, fts_score = fts_lookup.get(row_id, (None, None))

            if vector_rank is not None:
                rrf_score += self.vector_weight * (1 / (self.rrf_k + vector_rank))
            if fts_rank is not None:
                rrf_score += self.fts_weight * (1 / (self.rrf_k + fts_rank))

            results.append(
                RankedResult(
                    row_id=row_id,
                    rrf_score=rrf_score,
                    vector_rank=vector_rank,
                    vector_score=vector_score,
                    fts_rank=fts_rank,
                    fts_score=fts_score,
                )
            )

        return results

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[RankedResult]:
        vector_results: list[ScoredRow] = []
        try:
            query_embedding = await self.embedder.embed_one(query)
            query_bytes = serialize_embedding(query_embedding)
            vector_results = await self._vector_search(query_bytes, sources, limit)
        except Exception as e:
            logger.warning("Vector search failed, using FTS only: %s", e)

        fts_results = await self._fts_search(query, sources, limit)

        if not vector_results and not fts_results:
            return []

        merged = self._rrf_merge(vector_results, fts_results)
        merged.sort(key=lambda r: r.rrf_score, reverse=True)

        return merged[:limit]
