import math
from datetime import timedelta

from ntrp.constants import (
    LINK_SEMANTIC_SEARCH_LIMIT,
    LINK_SEMANTIC_THRESHOLD,
    LINK_TEMPORAL_MIN_WEIGHT,
    LINK_TEMPORAL_SIGMA_HOURS,
)
from ntrp.memory.models import Fact, LinkType
from ntrp.memory.store.facts import FactRepository

# Entity links below this weight are not worth creating
_ENTITY_LINK_MIN_WEIGHT = 0.01

# Query window for temporal links (5x sigma covers 99%+ of weight)
_TEMPORAL_QUERY_WINDOW_HOURS = LINK_TEMPORAL_SIGMA_HOURS * 5

LinkTuple = tuple[int, int, LinkType, float]


async def create_links_for_fact(repo: FactRepository, fact: Fact) -> int:
    links: list[LinkTuple] = []
    links.extend(await _compute_temporal_links(repo, fact))
    links.extend(await _compute_semantic_links(repo, fact))
    links.extend(await _compute_entity_links(repo, fact))
    return await repo.create_links_batch(links)


async def _compute_temporal_links(repo: FactRepository, fact: Fact) -> list[LinkTuple]:
    if not fact.happened_at:
        return []

    window_start = fact.happened_at - timedelta(hours=_TEMPORAL_QUERY_WINDOW_HOURS)
    recent_facts = await repo.list_in_time_window(window_start, fact.happened_at)

    links: list[LinkTuple] = []
    for other in recent_facts:
        if other.id == fact.id:
            continue
        if not other.happened_at:
            continue

        hours_diff = abs((fact.happened_at - other.happened_at).total_seconds()) / 3600
        weight = math.exp(-hours_diff / LINK_TEMPORAL_SIGMA_HOURS)

        if weight < LINK_TEMPORAL_MIN_WEIGHT:
            continue

        links.append((fact.id, other.id, LinkType.TEMPORAL, weight))
    return links


async def _compute_semantic_links(repo: FactRepository, fact: Fact) -> list[LinkTuple]:
    if fact.embedding is None:
        return []

    similar = await repo.search_facts_vector(fact.embedding, LINK_SEMANTIC_SEARCH_LIMIT)

    links: list[LinkTuple] = []
    for other, similarity in similar:
        if other.id == fact.id:
            continue
        if similarity >= LINK_SEMANTIC_THRESHOLD:
            links.append((fact.id, other.id, LinkType.SEMANTIC, similarity))
    return links


async def _compute_entity_links(repo: FactRepository, fact: Fact) -> list[LinkTuple]:
    entity_refs = fact.entity_refs
    if not entity_refs:
        return []

    # IDF-weighted entity links: rare entities create strong links,
    # common entities (like "User") create weak ones.
    # weight = 1 / log2(freq + 1), so freq=1 → 1.0, freq=30 → 0.20, freq=1000 → 0.10
    best_weight: dict[int, float] = {}

    for ref in entity_refs:
        freq = await repo.count_entity_facts(ref.name)
        weight = min(1.0, 1.0 / math.log2(freq + 1))
        if weight < _ENTITY_LINK_MIN_WEIGHT:
            continue

        others = await repo.get_facts_for_entity(ref.name, limit=50)
        for other in others:
            if other.id != fact.id:
                best_weight[other.id] = max(best_weight.get(other.id, 0), weight)

    return [(fact.id, other_id, LinkType.ENTITY, w) for other_id, w in best_weight.items()]
