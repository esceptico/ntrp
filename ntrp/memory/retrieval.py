import heapq
import math
from datetime import datetime

import numpy as np

from ntrp.constants import (
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

    expansion_scores: dict[int, float] = {}
    seed_set = set(seed_fact_ids)

    for entity_id in entity_ids:
        freq = await repo.count_entity_facts_by_id(entity_id)
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


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


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
            sim = _cosine_similarity(query_embedding, fact.embedding)
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
    return base_score * decay * recency


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

    # Fetch all candidate facts in one query
    facts_by_id = await repo.get_batch(list(candidate_ids))

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
                sim = _cosine_similarity(query_embedding, fact.embedding) if fact.embedding is not None else 0.0
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
            source_facts = [display_facts[fid] for fid in display_ids_per_obs[obs.id] if fid in display_facts]
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
