import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, Protocol, TypeVar

import numpy as np

from ntrp.constants import (
    CONSOLIDATED_FACT_RECALL_WEIGHT,
    ENTITY_EXPANSION_IDF_FLOOR,
    ENTITY_EXPANSION_MAX_FACTS,
    ENTITY_EXPANSION_PER_ENTITY_LIMIT,
    RECALL_OBSERVATION_LIMIT,
    RECALL_STANDALONE_FACT_LIMIT,
    RRF_OVERFETCH_FACTOR,
    TEMPORAL_EXPANSION_BASE_SCORE,
    TEMPORAL_EXPANSION_LIMIT,
)
from ntrp.memory.decay import decay_score, recency_boost
from ntrp.memory.models import Embedding, Fact, FactContext, Observation
from ntrp.memory.reranker import rerank
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.search.retrieval import rrf_merge

PAIR_SEARCH_BLOCK_SIZE = 256


class EmbeddedItem(Protocol):
    id: int
    embedding: Embedding | None


ItemT = TypeVar("ItemT", bound=EmbeddedItem)


@dataclass(frozen=True)
class SimilarityPair(Generic[ItemT]):
    left: ItemT
    right: ItemT
    score: float


def _pair_key(left_id: int, right_id: int) -> tuple[int, int]:
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def _normalized_embedding(embedding: Embedding) -> np.ndarray:
    array = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(array)
    return array / norm if norm > 0 else array.copy()


class SimilarityPairQueue(Generic[ItemT]):
    """Ranked near-duplicate candidates with lazy stale-pair invalidation."""

    def __init__(self, items: Sequence[ItemT], threshold: float):
        self.threshold = threshold
        self._items: dict[int, ItemT] = {}
        self._embeddings: dict[int, np.ndarray] = {}
        self._versions: dict[int, int] = {}
        self._heap: list[tuple[float, int, int, int, int]] = []

        for item in items:
            item_id = int(item.id)
            self._items[item_id] = item
            self._versions[item_id] = 0
            if item.embedding is not None:
                self._embeddings[item_id] = _normalized_embedding(item.embedding)

        self._push_initial_pairs()

    def pop(self, skipped: set[tuple[int, int]]) -> SimilarityPair[ItemT] | None:
        while self._heap:
            negative_score, left_id, right_id, left_version, right_version = heapq.heappop(self._heap)
            if _pair_key(left_id, right_id) in skipped:
                continue
            if left_id not in self._items or right_id not in self._items:
                continue
            if self._versions[left_id] != left_version or self._versions[right_id] != right_version:
                continue
            return SimilarityPair(self._items[left_id], self._items[right_id], -negative_score)
        return None

    def remove(self, item_id: int) -> None:
        item_id = int(item_id)
        self._items.pop(item_id, None)
        self._embeddings.pop(item_id, None)
        self._versions.pop(item_id, None)

    def replace(self, item: ItemT, removed_id: int | None = None) -> None:
        item_id = int(item.id)
        if removed_id is not None and int(removed_id) != item_id:
            self.remove(removed_id)

        self._items[item_id] = item
        self._versions[item_id] = self._versions.get(item_id, 0) + 1

        if item.embedding is None:
            self._embeddings.pop(item_id, None)
            return

        self._embeddings[item_id] = _normalized_embedding(item.embedding)
        self._push_pairs_for(item_id)

    def _push_initial_pairs(self) -> None:
        item_ids = list(self._embeddings)
        if len(item_ids) < 2:
            return

        embeddings = np.stack([self._embeddings[item_id] for item_id in item_ids])
        columns = np.arange(len(item_ids))

        for start in range(0, len(item_ids), PAIR_SEARCH_BLOCK_SIZE):
            end = min(start + PAIR_SEARCH_BLOCK_SIZE, len(item_ids))
            scores = embeddings[start:end] @ embeddings.T
            row_indices = np.arange(start, end)[:, None]
            scores[columns[None, :] <= row_indices] = -np.inf

            rows, cols = np.where(scores >= self.threshold)
            for local_row, col in zip(rows, cols, strict=False):
                row = start + int(local_row)
                self._push_pair(item_ids[row], item_ids[int(col)], float(scores[local_row, col]))

    def _push_pairs_for(self, item_id: int) -> None:
        embedding = self._embeddings.get(item_id)
        if embedding is None:
            return

        other_ids = [other_id for other_id in self._embeddings if other_id != item_id]
        if not other_ids:
            return

        embeddings = np.stack([self._embeddings[other_id] for other_id in other_ids])
        scores = embeddings @ embedding
        for index in np.flatnonzero(scores >= self.threshold):
            self._push_pair(item_id, other_ids[int(index)], float(scores[index]))

    def _push_pair(self, left_id: int, right_id: int, score: float) -> None:
        left_id, right_id = _pair_key(left_id, right_id)
        heapq.heappush(
            self._heap,
            (-score, left_id, right_id, self._versions[left_id], self._versions[right_id]),
        )


async def hybrid_search(
    repo: FactRepository,
    query_text: str,
    query_embedding: Embedding,
    limit: int,
) -> dict[int, float]:
    vector_results = await repo.search_facts_vector(query_embedding, limit * RRF_OVERFETCH_FACTOR)
    vector_ranking = [(f.id, sim) for f, sim in vector_results]

    fts_results = await repo.search_facts_fts(query_text, limit * RRF_OVERFETCH_FACTOR)
    fts_ranking = [(f.id, 1.0 - i * 0.1) for i, f in enumerate(fts_results)]

    return rrf_merge([vector_ranking, fts_ranking])


async def entity_expand(
    repo: FactRepository,
    seed_fact_ids: list[int],
    max_facts: int = ENTITY_EXPANSION_MAX_FACTS,
    per_entity_limit: int = ENTITY_EXPANSION_PER_ENTITY_LIMIT,
) -> dict[int, float]:
    """One-hop entity expansion: get entities from seeds, get other facts sharing those entities.

    Returns {fact_id: idf_weight} for expansion facts (excludes seeds).
    IDF weighting: rare entities create stronger connections than common ones.
    weight = 1 / log2(freq + 1)
    """
    entity_ids = await repo.get_entity_ids_for_facts(seed_fact_ids)
    if not entity_ids:
        return {}

    # Batch count to avoid N+1
    freq_map = await repo.count_entity_facts_batch(entity_ids)

    expansion_scores: dict[int, float] = {}
    seed_set = set(seed_fact_ids)

    for entity_id in entity_ids:
        freq = freq_map.get(entity_id, 0)
        idf_weight = 1.0 / math.log2(freq + 1) if freq > 0 else 1.0

        # Skip high-frequency entities — they connect too many unrelated facts
        if idf_weight < ENTITY_EXPANSION_IDF_FLOOR:
            continue

        facts = await repo.get_facts_for_entity_id(entity_id, limit=per_entity_limit)
        for fact in facts:
            if fact.id not in seed_set:
                expansion_scores[fact.id] = max(expansion_scores.get(fact.id, 0.0), idf_weight)

    if len(expansion_scores) > max_facts:
        top = heapq.nlargest(max_facts, expansion_scores.items(), key=lambda x: x[1])
        expansion_scores = dict(top)

    return expansion_scores


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


def find_top_pair(
    items: list,
    skipped: set[tuple[int, int]],
    threshold: float,
) -> tuple[int, int, float] | None:
    """Find the highest-similarity pair of items above threshold, skipping known pairs.

    Items must have `.id` (int) and `.embedding` (ndarray | None) attributes.
    """
    item_indices = {int(item.id): i for i, item in enumerate(items)}
    candidates = SimilarityPairQueue(items, threshold)
    pair = candidates.pop(skipped)
    if pair is None:
        return None
    return (item_indices[int(pair.left.id)], item_indices[int(pair.right.id)], pair.score)


async def _temporal_vector_expand(
    repo: FactRepository,
    query_embedding: Embedding,
    query_time: datetime,
    limit: int,
    overfetch: int = 100,
) -> dict[int, float]:
    """Fetch temporally proximate facts, rank by vector similarity, return top-K."""
    candidates = await repo.search_facts_temporal(query_time, overfetch)
    if not candidates:
        return {}

    scored = []
    for fact in candidates:
        if fact.embedding is not None:
            sim = cosine_similarity(query_embedding, fact.embedding)
            scored.append((fact.id, sim * TEMPORAL_EXPANSION_BASE_SCORE))

    top = heapq.nlargest(limit, scored, key=lambda x: x[1])
    return dict(top)


def score_fact(
    fact: Fact,
    base_score: float,
    query_time: datetime | None = None,
) -> float:
    decay = decay_score(fact.last_accessed_at, fact.access_count)
    recency = recency_boost(
        fact.happened_at or fact.created_at,
        reference_time=query_time,
    )
    score = base_score * decay * recency
    if fact.consolidated_at is not None:
        score *= CONSOLIDATED_FACT_RECALL_WEIGHT
    return score


def _is_recallable_fact(fact: Fact, now: datetime | None = None) -> bool:
    if fact.archived_at is not None or fact.superseded_by_fact_id is not None:
        return False
    if fact.expires_at is None:
        return True
    return fact.expires_at > (now or datetime.now(UTC))


async def retrieve_facts(
    repo: FactRepository,
    query_text: str,
    query_embedding: Embedding,
    seed_limit: int = 5,
    query_time: datetime | None = None,
) -> FactContext:
    rrf_scores = await hybrid_search(repo, query_text, query_embedding, seed_limit)
    if not rrf_scores:
        return FactContext(facts=[])

    # Top-K seeds
    seeds = dict(heapq.nlargest(seed_limit, rrf_scores.items(), key=lambda x: x[1]))
    seed_ids = list(seeds.keys())

    # Entity expansion
    expansion = await entity_expand(repo, seed_ids)

    # Temporal+vector expansion: get temporally close facts, filter by vector similarity
    if query_time:
        temporal_ids = await _temporal_vector_expand(
            repo,
            query_embedding,
            query_time,
            TEMPORAL_EXPANSION_LIMIT,
        )
    else:
        temporal_ids = {}

    # Collect all candidate fact IDs
    candidate_ids: set[int] = set(seeds.keys())
    candidate_ids.update(expansion.keys())
    candidate_ids.update(temporal_ids.keys())

    # Fetch all candidate facts in one query. consolidated_at means "processed", not "hide from recall".
    facts_by_id = await repo.get_batch(list(candidate_ids))
    facts_by_id = {fid: f for fid, f in facts_by_id.items() if _is_recallable_fact(f)}

    if not facts_by_id:
        return FactContext(facts=[])

    # Try cross-encoder reranking
    ordered_ids = list(facts_by_id.keys())
    documents = [facts_by_id[fid].text for fid in ordered_ids]
    rerank_results = await rerank(query_text, documents)

    if rerank_results:
        # Use reranker scores as base scores
        base_scores: dict[int, float] = {}
        for idx, score in rerank_results:
            base_scores[ordered_ids[idx]] = score
    else:
        # Fallback: multi-signal scoring
        base_scores = dict(seeds)
        for fid, idf_w in expansion.items():
            if fid not in base_scores and fid in facts_by_id:
                fact = facts_by_id[fid]
                sim = cosine_similarity(query_embedding, fact.embedding) if fact.embedding is not None else 0.0
                base_scores[fid] = idf_w * 0.5 * max(sim, 0.0)
        for fid, base in temporal_ids.items():
            if fid not in base_scores:
                base_scores[fid] = base

    # Apply decay/recency on top of base scores
    scored: list[tuple[Fact, float]] = []
    for fid, base in base_scores.items():
        if fid in facts_by_id:
            scored.append((facts_by_id[fid], score_fact(facts_by_id[fid], base, query_time)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return FactContext(facts=[f for f, _ in scored[:ENTITY_EXPANSION_MAX_FACTS]])


async def _observation_hybrid_search(
    obs_repo: ObservationRepository,
    query_text: str,
    query_embedding: Embedding,
    limit: int,
) -> dict[int, float]:
    """Hybrid search over observations: vector + FTS, merged via RRF."""
    vector_results = await obs_repo.search_vector(query_embedding, limit * RRF_OVERFETCH_FACTOR)
    vector_ranking = [(obs.id, sim) for obs, sim in vector_results]

    fts_results = await obs_repo.search_fts(query_text, limit * RRF_OVERFETCH_FACTOR)
    fts_ranking = [(obs.id, 1.0 - i * 0.1) for i, obs in enumerate(fts_results)]

    return rrf_merge([vector_ranking, fts_ranking])


def _score_observation(
    obs: Observation,
    base_score: float,
    query_time: datetime | None = None,
) -> float:
    d = decay_score(obs.last_accessed_at, obs.access_count)
    r = recency_boost(obs.updated_at, reference_time=query_time)
    return base_score * d * r


BUNDLED_DISPLAY_LIMIT = 5  # max source facts fetched per observation for display


async def retrieve_with_observations(
    repo: FactRepository,
    obs_repo: ObservationRepository,
    query_text: str,
    query_embedding: Embedding,
    seed_limit: int = 5,
    query_time: datetime | None = None,
) -> FactContext:
    # --- Phase 1: Observation retrieval via hybrid search (vector + FTS) ---
    obs_rrf = await _observation_hybrid_search(obs_repo, query_text, query_embedding, RECALL_OBSERVATION_LIMIT)

    obs_by_id = await obs_repo.get_batch(list(obs_rrf.keys()))
    obs_by_id = {oid: o for oid, o in obs_by_id.items() if o.archived_at is None}

    obs_scores: dict[int, float] = {}
    for oid, base in obs_rrf.items():
        if oid not in obs_by_id:
            continue
        obs_scores[oid] = _score_observation(obs_by_id[oid], base, query_time)

    top_obs_ids = [oid for oid, _ in heapq.nlargest(RECALL_OBSERVATION_LIMIT, obs_scores.items(), key=lambda x: x[1])]
    observations = [obs_by_id[oid] for oid in top_obs_ids]

    # --- Phase 2: Bundle source facts ---
    # Exclusion set: ALL source fact IDs (prevents duplicates in standalone facts)
    bundled_fact_ids: set[int] = set()
    for obs in observations:
        bundled_fact_ids.update(obs.source_fact_ids)

    # Display: fetch only the most recent N source facts per observation
    all_display_ids: set[int] = set()
    display_ids_per_obs: dict[int, list[int]] = {}
    for obs in observations:
        if not obs.source_fact_ids:
            continue
        recent_ids = obs.source_fact_ids[-BUNDLED_DISPLAY_LIMIT:]
        display_ids_per_obs[obs.id] = recent_ids
        all_display_ids.update(recent_ids)

    display_facts = await repo.get_batch(list(all_display_ids)) if all_display_ids else {}

    bundled_sources: dict[int, list[Fact]] = {}
    for obs in observations:
        if obs.id in display_ids_per_obs:
            source_facts = [
                display_facts[fid]
                for fid in display_ids_per_obs[obs.id]
                if fid in display_facts and display_facts[fid].archived_at is None
            ]
            if source_facts:
                bundled_sources[obs.id] = source_facts

    # --- Phase 3: Standalone facts (unconsolidated/skipped, not already bundled) ---
    fact_context = await retrieve_facts(repo, query_text, query_embedding, seed_limit, query_time)
    standalone_facts = [f for f in fact_context.facts if f.id not in bundled_fact_ids][:RECALL_STANDALONE_FACT_LIMIT]

    return FactContext(
        facts=standalone_facts,
        observations=observations,
        bundled_sources=bundled_sources,
    )
