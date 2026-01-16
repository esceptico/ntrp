from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RerankResult:
    index: int
    score: float


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: list[str], top_k: int | None = None) -> list[RerankResult]:
        pass


class NoopReranker(Reranker):
    """Passthrough reranker that preserves original order."""

    def rerank(self, query: str, documents: list[str], top_k: int | None = None) -> list[RerankResult]:
        limit = top_k if top_k else len(documents)
        return [RerankResult(index=i, score=1.0 - (i / len(documents))) for i in range(min(limit, len(documents)))]
