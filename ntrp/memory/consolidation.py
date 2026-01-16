"""Per-fact consolidation using LLM decisions (Hindsight approach).

Each fact is processed independently:
1. Find related observations via vector search
2. Single LLM call returns ONE action (update/create/skip)
3. Execute the action
4. Mark fact as consolidated

Observations are HIGHER-LEVEL than facts — they synthesize patterns,
preferences, and learnings. Each fact typically results in one action
(update existing or create new), not multiple decomposed atoms.
"""

import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass

from litellm import acompletion

from ntrp.constants import (
    CONSOLIDATION_SEARCH_LIMIT,
    CONSOLIDATION_TEMPERATURE,
)
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Fact, Observation
from ntrp.memory.prompts import CONSOLIDATION_PROMPT
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]


@dataclass
class ConsolidationResult:
    action: str  # "created", "updated", "multiple", "skipped"
    observation_id: int | None = None
    reason: str | None = None
    created: int = 0
    updated: int = 0


@dataclass
class ConsolidationAction:
    type: str  # "update", "create", "skip"
    observation_id: int | None = None
    text: str | None = None
    reason: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> "ConsolidationAction":
        return cls(
            type=data.get("action", "skip"),
            observation_id=data.get("observation_id"),
            text=data.get("text"),
            reason=data.get("reason"),
        )


async def consolidate_fact(
    fact: Fact,
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    model: str,
    embed_fn: EmbedFn,
) -> ConsolidationResult:
    """
    Consolidate a single fact into an observation.

    Hindsight approach:
    1. Find related observations via vector search
    2. LLM returns ONE action (update/create/skip)
    3. Execute the action
    4. Mark fact as consolidated

    Observations are higher-level than facts — they synthesize patterns.
    """
    if fact.embedding is None:
        await fact_repo.mark_consolidated(fact.id)
        return ConsolidationResult(action="skipped", reason="no_embedding")

    # Find related observations
    candidates = await obs_repo.search_vector(fact.embedding, limit=CONSOLIDATION_SEARCH_LIMIT)

    # Single LLM call - returns ONE action
    action = await _llm_consolidation_decision(fact, candidates, fact_repo, model)

    if action is None or action.type == "skip":
        await fact_repo.mark_consolidated(fact.id)
        return ConsolidationResult(action="skipped", reason=action.reason if action else "no_durable_knowledge")

    # Execute the action
    result = await _execute_action(action, fact, obs_repo, embed_fn)

    # Mark fact as consolidated
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
    """
    Single LLM call to decide consolidation action.

    Returns ONE action:
    - {"action": "update", "observation_id": N, "text": "...", "reason": "..."}
    - {"action": "create", "text": "...", "reason": "..."}
    - {"action": "skip", "reason": "..."} if fact is ephemeral
    """
    observations_json = await _format_observations(candidates, fact_repo)

    prompt = CONSOLIDATION_PROMPT.format(
        fact_text=fact.text,
        observations_json=observations_json,
    )

    try:
        response = await acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=CONSOLIDATION_TEMPERATURE,
        )
        content = response.choices[0].message.content
        if not content:
            return None

        clean = _strip_markdown(content)
        data = json.loads(clean)

        # Handle single action (expected)
        if isinstance(data, dict):
            return ConsolidationAction.from_json(data)

        # Handle array response (legacy - take first action)
        if isinstance(data, list) and data:
            return ConsolidationAction.from_json(data[0])

        return None

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON from consolidation LLM: {e}")
        return None
    except Exception as e:
        logger.warning(f"Consolidation LLM failed: {e}")
        return None


async def _execute_action(
    action: ConsolidationAction,
    fact: Fact,
    obs_repo: ObservationRepository,
    embed_fn: EmbedFn,
) -> ConsolidationResult | None:
    """Execute a single action (update or create)."""
    if action.type == "skip":
        return None

    if action.type == "update":
        if not action.observation_id or not action.text:
            logger.debug("Skipped update: missing observation_id or text")
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
            logger.info(f"Updated observation {obs.id} with fact {fact.id}: {action.reason}")
            return ConsolidationResult(action="updated", observation_id=obs.id, reason=action.reason)
        else:
            logger.debug(f"Observation {action.observation_id} not found for update")
            return None

    if action.type == "create":
        if not action.text:
            logger.debug("Skipped create: missing text")
            return None

        embedding = await embed_fn(action.text)
        obs = await obs_repo.create(
            summary=action.text,
            embedding=embedding,
            source_fact_id=fact.id,
        )
        logger.info(f"Created observation {obs.id} from fact {fact.id}")
        return ConsolidationResult(action="created", observation_id=obs.id)

    return None


async def _format_observations(
    candidates: list[tuple[Observation, float]],
    fact_repo: FactRepository,
) -> str:
    """Format observations with source facts for the LLM prompt."""
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


def _strip_markdown(content: str) -> str:
    """Strip markdown code fences if present."""
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
    return clean
