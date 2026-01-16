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

# Query window for temporal links (5x sigma covers 99%+ of weight)
_TEMPORAL_QUERY_WINDOW_HOURS = LINK_TEMPORAL_SIGMA_HOURS * 5


async def create_links_for_fact(repo: FactRepository, fact: Fact) -> int:
    """Create all links for a newly stored fact. Returns count of links created."""
    count = 0
    count += await _create_temporal_links(repo, fact)
    count += await _create_semantic_links(repo, fact)
    count += await _create_entity_links(repo, fact)
    return count


async def _create_temporal_links(repo: FactRepository, fact: Fact) -> int:
    # Only create temporal links for facts with real event times
    if not fact.happened_at:
        return 0

    # Query wider window, exponential decay handles relevance
    window_start = fact.happened_at - timedelta(hours=_TEMPORAL_QUERY_WINDOW_HOURS)
    recent_facts = await repo.list_in_time_window(window_start, fact.happened_at)

    count = 0
    for other in recent_facts:
        if other.id == fact.id:
            continue
        if not other.happened_at:
            continue

        hours_diff = abs((fact.happened_at - other.happened_at).total_seconds()) / 3600
        # Exponential decay: weight = exp(-Δt / σ)
        weight = math.exp(-hours_diff / LINK_TEMPORAL_SIGMA_HOURS)

        if weight < LINK_TEMPORAL_MIN_WEIGHT:
            continue

        await repo.create_link(fact.id, other.id, LinkType.TEMPORAL, weight)
        count += 1
    return count


async def _create_semantic_links(repo: FactRepository, fact: Fact) -> int:
    if fact.embedding is None:
        return 0

    similar = await repo.search_facts_vector(fact.embedding, LINK_SEMANTIC_SEARCH_LIMIT)

    count = 0
    for other, similarity in similar:
        if other.id == fact.id:
            continue
        if similarity >= LINK_SEMANTIC_THRESHOLD:
            await repo.create_link(fact.id, other.id, LinkType.SEMANTIC, similarity)
            count += 1
    return count


async def _create_entity_links(repo: FactRepository, fact: Fact) -> int:
    entity_refs = await repo.get_entity_refs(fact.id)
    if not entity_refs:
        return 0

    sharing = await repo.get_facts_sharing_entities(fact.id)
    if not sharing:
        return 0

    # Binary weight (Hindsight approach): any entity overlap = full connection
    count = 0
    for other, _ in sharing:
        await repo.create_link(fact.id, other.id, LinkType.ENTITY, 1.0)
        count += 1
    return count
