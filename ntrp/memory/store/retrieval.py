import heapq
from collections import defaultdict

from ntrp.constants import (
    BFS_DECAY_FACTOR,
    BFS_MAX_FACTS,
    BFS_SCORE_THRESHOLD,
    RECALL_OBSERVATION_LIMIT,
)
from ntrp.memory.decay import decay_score, recency_boost
from ntrp.memory.models import Embedding, Fact, FactContext, Observation
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository


def rrf_merge(
    rankings: list[list[tuple[int, float]]],
    k: int = 60,
) -> dict[int, float]:
    """Reciprocal Rank Fusion to merge multiple ranked lists."""
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, (item_id, _) in enumerate(ranking):
            scores[item_id] += 1 / (k + rank + 1)
    return dict(scores)


async def hybrid_search(
    repo: FactRepository,
    query_text: str,
    query_embedding: Embedding,
    limit: int,
) -> dict[int, float]:
    """Run vector + FTS search and merge with RRF."""
    vector_results = await repo.search_facts_vector(query_embedding, limit * 2)
    vector_ranking = [(f.id, sim) for f, sim in vector_results]

    fts_results = await repo.search_facts_fts(query_text, limit * 2)
    fts_ranking = [(f.id, 1.0 - i * 0.1) for i, f in enumerate(fts_results)]

    return rrf_merge([vector_ranking, fts_ranking])


async def expand_graph(
    repo: FactRepository,
    seeds: dict[int, float],
    max_facts: int = BFS_MAX_FACTS,
    score_threshold: float = BFS_SCORE_THRESHOLD,
    decay_factor: float = BFS_DECAY_FACTOR,
) -> dict[int, tuple[Fact, float]]:
    """BFS expansion from seed facts, propagating scores through links."""
    collected: dict[int, tuple[Fact, float]] = {}
    scores: dict[int, float] = dict(seeds)
    visited: set[int] = set()

    pq: list[tuple[float, int]] = [(-score, fid) for fid, score in seeds.items()]
    heapq.heapify(pq)

    while pq and len(collected) < max_facts:
        neg_score, fact_id = heapq.heappop(pq)
        score = -neg_score

        if fact_id in visited or score < score_threshold:
            continue
        visited.add(fact_id)

        if fact_id not in collected:
            fact = await repo.get(fact_id)
            if fact:
                collected[fact_id] = (fact, score)

        for link in await repo.get_links(fact_id):
            neighbor_id = link.target_fact_id if link.source_fact_id == fact_id else link.source_fact_id
            if neighbor_id in visited:
                continue

            new_score = score * link.weight * decay_factor
            if new_score >= score_threshold and new_score > scores.get(neighbor_id, 0):
                scores[neighbor_id] = new_score
                heapq.heappush(pq, (-new_score, neighbor_id))

    return collected


def score_fact(fact: Fact, base_score: float) -> float:
    """Combine base relevance with decay and recency."""
    decay = decay_score(fact.last_accessed_at, fact.access_count)
    recency = recency_boost(fact.happened_at or fact.created_at)
    return base_score * decay * recency


async def retrieve_facts(
    repo: FactRepository,
    query_text: str,
    query_embedding: Embedding,
    seed_limit: int = 5,
) -> FactContext:
    """Retrieve facts using hybrid search with graph expansion."""
    rrf_scores = await hybrid_search(repo, query_text, query_embedding, seed_limit)
    if not rrf_scores:
        return FactContext(facts=[])

    seeds = dict(heapq.nlargest(seed_limit, rrf_scores.items(), key=lambda x: x[1]))

    collected = await expand_graph(repo, seeds)
    if not collected:
        return FactContext(facts=[])

    scored = [(fact, score_fact(fact, base)) for fact, base in collected.values()]
    scored.sort(key=lambda x: x[1], reverse=True)

    return FactContext(facts=[f for f, _ in scored[:BFS_MAX_FACTS]])


async def retrieve_with_observations(
    repo: FactRepository,
    obs_repo: ObservationRepository,
    query_text: str,
    query_embedding: Embedding,
    seed_limit: int = 5,
) -> FactContext:
    """Retrieve facts and observations using hybrid search."""
    context = await retrieve_facts(repo, query_text, query_embedding, seed_limit)

    observations = await obs_repo.search_vector(query_embedding, RECALL_OBSERVATION_LIMIT)

    def obs_score(item: tuple[Observation, float]) -> float:
        obs, similarity = item
        decay = decay_score(obs.last_accessed_at, obs.access_count)
        recency = recency_boost(obs.created_at)
        return similarity * decay * recency

    top_obs = heapq.nlargest(RECALL_OBSERVATION_LIMIT, observations, key=obs_score)
    context.observations = [obs for obs, _ in top_obs]

    return context
