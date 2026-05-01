import json
import logging
from typing import Literal

from pydantic import BaseModel
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from ntrp.agent import Role
from ntrp.constants import (
    CONSOLIDATION_SEARCH_LIMIT,
    CONSOLIDATION_TEMPERATURE,
)
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Fact, FactKind, FactLifetime, Observation, SourceType
from ntrp.memory.prompts import CONSOLIDATION_PROMPT
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

PATTERN_POLICY_VERSION = "memory.pattern.v2"


class ConsolidationAction(BaseModel):
    action: Literal["update", "create", "skip"]
    observation_id: int | None = None
    text: str | None = None
    reason: str | None = None


class ConsolidationResponse(BaseModel):
    actions: list[ConsolidationAction]


class ConsolidationResult(BaseModel):
    action: str  # "created", "updated", "skipped"
    observation_id: int | None = None
    reason: str | None = None


async def get_consolidation_decisions(
    fact: Fact,
    obs_repo: ObservationRepository,
    fact_repo: FactRepository,
    model: str,
) -> list[ConsolidationAction]:
    if fact.lifetime == FactLifetime.TEMPORARY:
        return []
    if fact.embedding is None:
        return []

    candidates = await obs_repo.search_vector(fact.embedding, limit=CONSOLIDATION_SEARCH_LIMIT)
    return await _llm_consolidation_decisions(fact, candidates, fact_repo, model)


async def apply_consolidation(
    fact: Fact,
    action: ConsolidationAction,
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    embedding: Embedding | None,
) -> ConsolidationResult:
    if action.action == "skip":
        return ConsolidationResult(action="skipped", reason=action.reason)

    if action.action == "create":
        allowed, reason = _can_create_observation_from_fact(fact)
        if not allowed:
            return ConsolidationResult(action="skipped", reason=f"create_gate:{reason}")

    result = await _execute_action(action, fact, fact_repo, obs_repo, embedding)
    if not result:
        return ConsolidationResult(action="skipped", reason="action_failed")

    return result


def _can_create_observation_from_fact(fact: Fact) -> tuple[bool, str]:
    if fact.lifetime == FactLifetime.TEMPORARY:
        return False, "temporary_fact"
    if fact.source_type == SourceType.CHAT and fact.kind == FactKind.NOTE and fact.salience <= 0:
        return False, "chat_note_low_salience"
    return False, "single_fact_pattern"


async def _llm_consolidation_decisions(
    fact: Fact,
    candidates: list[tuple[Observation, float]],
    fact_repo: FactRepository,
    model: str,
) -> list[ConsolidationAction]:
    observations_json = await _format_observations(candidates, fact_repo)

    prompt = CONSOLIDATION_PROMPT.render(
        fact_json=json.dumps(_format_fact(fact), indent=2),
        observations_json=observations_json,
    )

    try:
        return await _call_consolidation_llm(prompt, model)
    except Exception as e:
        _logger.warning("Consolidation LLM failed after retries: %s", e)
        return []


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=3, min=3, max=15),
    before_sleep=before_sleep_log(_logger, logging.WARNING),
    reraise=True,
)
async def _call_consolidation_llm(prompt: str, model: str) -> list[ConsolidationAction]:
    client = get_completion_client(model)
    response = await client.completion(
        model=model,
        messages=[{"role": Role.USER, "content": prompt}],
        response_format=ConsolidationResponse,
        temperature=CONSOLIDATION_TEMPERATURE,
    )
    content = response.choices[0].message.content
    if not content:
        return []
    return ConsolidationResponse.model_validate_json(content).actions


async def _execute_action(
    action: ConsolidationAction,
    fact: Fact,
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    embedding: Embedding | None,
) -> ConsolidationResult | None:
    if action.action == "skip":
        return None

    # Get entity IDs from the source fact for inheritance
    fact_entity_ids = await fact_repo.get_entity_ids_for_facts([fact.id])

    if action.action == "update":
        if not action.observation_id or not action.text or embedding is None:
            _logger.debug("Skipped update: missing observation_id, text, or embedding")
            return None

        obs = await obs_repo.update(
            observation_id=action.observation_id,
            summary=action.text,
            embedding=embedding,
            new_fact_id=fact.id,
            reason=action.reason or "",
            policy_version=PATTERN_POLICY_VERSION,
        )
        if obs:
            if fact_entity_ids:
                await obs_repo.link_entities(obs.id, fact_entity_ids)
            _logger.info("Updated observation %d with fact %d: %s", obs.id, fact.id, action.reason)
            return ConsolidationResult(action="updated", observation_id=obs.id, reason=action.reason)
        else:
            _logger.debug("Observation %s not found for update", action.observation_id)
            return None

    if action.action == "create":
        if not action.text or embedding is None:
            _logger.debug("Skipped create: missing text or embedding")
            return None

        obs = await obs_repo.create(
            summary=action.text,
            embedding=embedding,
            source_fact_id=fact.id,
            created_by="consolidation",
            policy_version=PATTERN_POLICY_VERSION,
        )
        if fact_entity_ids:
            await obs_repo.link_entities(obs.id, fact_entity_ids)
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
        # Fetch source facts (limit to 5 for token efficiency)
        source_facts = []
        for fid in obs.source_fact_ids[:5]:
            fact = await fact_repo.get(fid)
            if fact:
                source_facts.append(
                    {
                        "text": fact.text,
                        "source_type": fact.source_type.value,
                        "source_ref": fact.source_ref,
                        "happened_at": fact.happened_at.isoformat() if fact.happened_at else None,
                        "created_at": fact.created_at.isoformat() if fact.created_at else None,
                    }
                )

        # Sort source facts chronologically (happened_at, fallback created_at)
        source_facts.sort(key=lambda f: f["happened_at"] or f["created_at"] or "")

        # Include observation change history
        history = [
            {
                "previous_text": h.previous_text,
                "changed_at": h.changed_at.isoformat(),
                "reason": h.reason,
            }
            for h in obs.history[-3:]  # last 3 entries max
        ]

        entry: dict = {
            "id": obs.id,
            "text": obs.summary,
            "evidence_count": obs.evidence_count,
            "similarity": round(similarity, 3),
            "source_facts": source_facts,
            "created_at": obs.created_at.isoformat() if obs.created_at else None,
            "updated_at": obs.updated_at.isoformat() if obs.updated_at else None,
        }
        if history:
            entry["history"] = history

        obs_list.append(entry)

    return json.dumps(obs_list, indent=2)


def _format_fact(fact: Fact) -> dict:
    return {
        "id": fact.id,
        "text": fact.text,
        "kind": fact.kind.value,
        "lifetime": fact.lifetime.value,
        "source_type": fact.source_type.value,
        "source_ref": fact.source_ref,
        "happened_at": fact.happened_at.isoformat() if fact.happened_at else None,
        "created_at": fact.created_at.isoformat() if fact.created_at else None,
    }
