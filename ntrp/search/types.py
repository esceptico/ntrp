from dataclasses import dataclass


@dataclass
class SearchResult:
    """Search result with full scoring breakdown."""

    source: str
    source_id: str
    title: str
    snippet: str | None
    metadata: dict | None = None

    # Individual scores for debugging/tuning
    vector_score: float | None = None
    vector_rank: int | None = None
    fts_score: float | None = None
    fts_rank: int | None = None

    # Final combined score
    rrf_score: float = 0.0


@dataclass
class ScoredRow:
    """Internal result from vector/FTS search before hydration."""

    row_id: int
    score: float
    rank: int = 0


@dataclass
class RankedResult:
    """Merged result with RRF score and individual rankings."""

    row_id: int
    rrf_score: float
    vector_rank: int | None = None
    vector_score: float | None = None
    fts_rank: int | None = None
    fts_score: float | None = None
