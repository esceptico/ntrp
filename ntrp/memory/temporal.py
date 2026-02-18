import json
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager, nullcontext
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from ntrp.constants import CONSOLIDATION_TEMPERATURE, OBSERVATION_MERGE_SIMILARITY_THRESHOLD
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding
from ntrp.memory.prompts import TEMPORAL_PATTERN_PROMPT
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]
type AtomicFn = Callable[[], AbstractAsyncContextManager[None]]


class TemporalAction(BaseModel):
    action: Literal["create", "skip"]
    text: str | None = None
    reason: str | None = None
    source_fact_ids: list[int] = []


class TemporalResponse(BaseModel):
    actions: list[TemporalAction]


async def temporal_consolidation_pass(
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    model: str,
    embed_fn: EmbedFn,
    atomic: AtomicFn | None = None,
    days: int = 30,
    min_facts: int = 3,
) -> int:
    entities = await fact_repo.get_entities_with_fact_count(days=days, min_count=min_facts)
    if not entities:
        return 0

    now = datetime.now(UTC)
    window_end = now.date().isoformat()
    created = 0

    for entity_id, entity_name, _ in entities:
        if await fact_repo.has_temporal_checkpoint(entity_id, window_end):
            continue

        facts = await fact_repo.get_facts_for_entity_temporal(entity_id, days=days, limit=50)
        if len(facts) < min_facts:
            continue

        facts_json = json.dumps(
            [
                {
                    "id": f.id,
                    "text": f.text,
                    "happened_at": f.happened_at.isoformat() if f.happened_at else None,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in facts
            ],
            indent=2,
        )

        actions = await _llm_temporal_patterns(entity_name, facts_json, model)
        if not actions:
            continue  # LLM failed or returned empty — don't set checkpoint, retry next pass

        # Pre-compute embeddings + dedup checks outside atomic block
        to_create: list[tuple[TemporalAction, Embedding]] = []
        to_reinforce: list[tuple[int, list[int]]] = []  # (obs_id, fact_ids)
        for action in actions:
            if action.action != "create" or not action.text:
                continue
            embedding = await embed_fn(action.text)
            similar = await obs_repo.search_vector(embedding, limit=1)
            if similar and similar[0][1] >= OBSERVATION_MERGE_SIMILARITY_THRESHOLD:
                existing_obs, sim = similar[0]
                if action.source_fact_ids:
                    to_reinforce.append((existing_obs.id, action.source_fact_ids))
                _logger.info(
                    "Temporal: skipped duplicate for %s (sim=%.2f with obs %d)",
                    entity_name,
                    sim,
                    existing_obs.id,
                )
            else:
                to_create.append((action, embedding))

        # All DB writes inside atomic block
        async with atomic() if atomic else nullcontext():
            for obs_id, fact_ids in to_reinforce:
                await obs_repo.add_source_facts(obs_id, fact_ids)

            for action, embedding in to_create:
                source_fact_id = action.source_fact_ids[0] if action.source_fact_ids else None
                obs = await obs_repo.create(
                    summary=action.text,
                    embedding=embedding,
                    source_fact_id=source_fact_id,
                )
                if len(action.source_fact_ids) > 1:
                    await obs_repo.add_source_facts(obs.id, action.source_fact_ids[1:])
                _logger.info(
                    "Temporal observation created for %s: %s",
                    entity_name,
                    action.text[:80],
                )
                created += 1

            await fact_repo.set_temporal_checkpoint(entity_id, window_end)

    _logger.info("Temporal pass: %d observations created from %d entities", created, len(entities))
    return created


async def _llm_temporal_patterns(
    entity_name: str,
    facts_json: str,
    model: str,
) -> list[TemporalAction]:
    prompt = TEMPORAL_PATTERN_PROMPT.format(
        entity_name=entity_name,
        facts_json=facts_json,
    )

    try:
        client = get_completion_client(model)
        response = await client.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=TemporalResponse,
            temperature=CONSOLIDATION_TEMPERATURE,
        )
        content = response.choices[0].message.content
        if not content:
            return []

        parsed = TemporalResponse.model_validate_json(content)
        return parsed.actions

    except Exception as e:
        _logger.warning("Temporal pattern LLM failed: %s", e)
        return []
