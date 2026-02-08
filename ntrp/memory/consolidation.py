import json
from collections.abc import Callable, Coroutine
from typing import Literal

from pydantic import BaseModel

from ntrp.constants import (
    CONSOLIDATION_SEARCH_LIMIT,
    CONSOLIDATION_TEMPERATURE,
)
from ntrp.llm import acompletion
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Fact, Observation
from ntrp.memory.prompts import CONSOLIDATION_PROMPT
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]


class ConsolidationSchema(BaseModel):
    action: Literal["update", "create", "skip"]
    observation_id: int | None = None
    text: str | None = None
    reason: str | None = None


class ConsolidationResult(BaseModel):
    action: str  # "created", "updated", "skipped"
    observation_id: int | None = None
    reason: str | None = None


class ConsolidationAction(BaseModel):
    type: str  # "update", "create", "skip"
    observation_id: int | None = None
    text: str | None = None
    reason: str | None = None


async def get_consolidation_decision(
    fact: Fact,
    obs_repo: ObservationRepository,
    fact_repo: FactRepository,
    model: str,
) -> ConsolidationAction | None:
    if fact.embedding is None:
        return None

    candidates = await obs_repo.search_vector(fact.embedding, limit=CONSOLIDATION_SEARCH_LIMIT)
    return await _llm_consolidation_decision(fact, candidates, fact_repo, model)


async def apply_consolidation(
    fact: Fact,
    action: ConsolidationAction | None,
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    embed_fn: EmbedFn,
) -> ConsolidationResult:
    if action is None or action.type == "skip":
        await fact_repo.mark_consolidated(fact.id)
        return ConsolidationResult(action="skipped", reason=action.reason if action else "no_durable_knowledge")

    result = await _execute_action(action, fact, obs_repo, embed_fn)
    await fact_repo.mark_consolidated(fact.id)

    if not result:
        return ConsolidationResult(action="skipped", reason="action_failed")

    return result


async def _llm_consolidation_decision(
    fact: Fact,
    candidates: list[tuple[Observation, float]],
    fact_repo: FactRepository,
    model: str,
) -> ConsolidationAction | None:
    observations_json = await _format_observations(candidates, fact_repo)

    prompt = CONSOLIDATION_PROMPT.format(
        fact_text=fact.text,
        observations_json=observations_json,
    )

    try:
        response = await acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=ConsolidationSchema,
            temperature=CONSOLIDATION_TEMPERATURE,
        )
        content = response.choices[0].message.content
        if not content:
            return None

        parsed = ConsolidationSchema.model_validate_json(content)
        return ConsolidationAction(
            type=parsed.action,
            observation_id=parsed.observation_id,
            text=parsed.text,
            reason=parsed.reason,
        )

    except Exception as e:
        _logger.warning("Consolidation LLM failed: %s", e)
        return None


async def _execute_action(
    action: ConsolidationAction,
    fact: Fact,
    obs_repo: ObservationRepository,
    embed_fn: EmbedFn,
) -> ConsolidationResult | None:
    if action.type == "skip":
        return None

    if action.type == "update":
        if not action.observation_id or not action.text:
            _logger.debug("Skipped update: missing observation_id or text")
            return None

        embedding = await embed_fn(action.text)
        obs = await obs_repo.update(
            observation_id=action.observation_id,
            summary=action.text,
            embedding=embedding,
            new_fact_id=fact.id,
            reason=action.reason or "",
        )
        if obs:
            _logger.info("Updated observation %d with fact %d: %s", obs.id, fact.id, action.reason)
            return ConsolidationResult(action="updated", observation_id=obs.id, reason=action.reason)
        else:
            _logger.debug("Observation %s not found for update", action.observation_id)
            return None

    if action.type == "create":
        if not action.text:
            _logger.debug("Skipped create: missing text")
            return None

        embedding = await embed_fn(action.text)
        obs = await obs_repo.create(
            summary=action.text,
            embedding=embedding,
            source_fact_id=fact.id,
        )
        _logger.info("Created observation %d from fact %d", obs.id, fact.id)
        return ConsolidationResult(action="created", observation_id=obs.id)

    return None


async def _format_observations(
    candidates: list[tuple[Observation, float]],
    fact_repo: FactRepository,
) -> str:
    if not candidates:
        return "[]"

    obs_list = []
    for obs, similarity in candidates:
        # Fetch source facts (limit to 3 for token efficiency)
        source_facts = []
        for fid in obs.source_fact_ids[:3]:
            f = await fact_repo.get(fid)
            if f:
                source_facts.append(
                    {
                        "text": f.text,
                        "created_at": f.created_at.isoformat() if f.created_at else None,
                    }
                )

        obs_list.append(
            {
                "id": obs.id,
                "text": obs.summary,
                "evidence_count": obs.evidence_count,
                "similarity": round(similarity, 3),
                "source_facts": source_facts,
                "created_at": obs.created_at.isoformat() if obs.created_at else None,
                "updated_at": obs.updated_at.isoformat() if obs.updated_at else None,
            }
        )

    return json.dumps(obs_list, indent=2)
