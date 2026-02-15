"""Observation merge pass: recursive pairwise deduplication.

Finds the most similar observation pair above threshold, asks LLM to merge
or skip, re-embeds, repeats until no pairs remain above threshold.
"""

from collections.abc import Callable, Coroutine
from typing import Literal

import numpy as np
from pydantic import BaseModel

from ntrp.constants import (
    OBSERVATION_MERGE_SIMILARITY_THRESHOLD,
    OBSERVATION_MERGE_TEMPERATURE,
)
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Observation
from ntrp.memory.prompts import OBSERVATION_MERGE_PROMPT
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]


class MergeAction(BaseModel):
    action: Literal["merge", "skip"]
    text: str | None = None
    reason: str | None = None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    return float(dot / (na * nb)) if na and nb else 0.0


def _find_top_pair(
    observations: list[Observation],
    skipped: set[tuple[int, int]],
    threshold: float,
) -> tuple[int, int, float] | None:
    best = None
    for i in range(len(observations)):
        if observations[i].embedding is None:
            continue
        for j in range(i + 1, len(observations)):
            if observations[j].embedding is None:
                continue
            pair_key = (
                min(observations[i].id, observations[j].id),
                max(observations[i].id, observations[j].id),
            )
            if pair_key in skipped:
                continue
            sim = _cosine(observations[i].embedding, observations[j].embedding)
            if sim >= threshold and (best is None or sim > best[2]):
                best = (i, j, sim)
    return best


async def _llm_merge_decision(
    obs_a: Observation,
    obs_b: Observation,
    model: str,
) -> MergeAction:
    prompt = OBSERVATION_MERGE_PROMPT.format(
        id_a=obs_a.id,
        evidence_a=obs_a.evidence_count,
        text_a=obs_a.summary,
        id_b=obs_b.id,
        evidence_b=obs_b.evidence_count,
        text_b=obs_b.summary,
    )

    try:
        client = get_completion_client(model)
        resp = await client.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=MergeAction,
            temperature=OBSERVATION_MERGE_TEMPERATURE,
        )
        content = resp.choices[0].message.content
        if not content:
            return MergeAction(action="skip", reason="empty response")

        return MergeAction.model_validate_json(content)

    except Exception as e:
        _logger.warning("Observation merge LLM failed: %s", e)
        return MergeAction(action="skip", reason=f"llm error: {e}")


async def observation_merge_pass(
    obs_repo: ObservationRepository,
    model: str,
    embed_fn: EmbedFn,
    threshold: float = OBSERVATION_MERGE_SIMILARITY_THRESHOLD,
) -> int:
    observations = await obs_repo.list_all_with_embeddings()
    if len(observations) < 2:
        return 0

    skipped_pairs: set[tuple[int, int]] = set()
    merges = 0

    while True:
        pair = _find_top_pair(observations, skipped_pairs, threshold)
        if pair is None:
            break

        i, j, sim = pair
        obs_a, obs_b = observations[i], observations[j]

        decision = await _llm_merge_decision(obs_a, obs_b, model)

        if decision.action == "skip":
            _logger.debug(
                "Merge skip: obs %d + %d (sim=%.3f): %s",
                obs_a.id, obs_b.id, sim, decision.reason,
            )
            skipped_pairs.add((min(obs_a.id, obs_b.id), max(obs_a.id, obs_b.id)))
            continue

        if not decision.text:
            skipped_pairs.add((min(obs_a.id, obs_b.id), max(obs_a.id, obs_b.id)))
            continue

        # Determine keeper (higher evidence count)
        if obs_a.evidence_count >= obs_b.evidence_count:
            keeper, removed = obs_a, obs_b
        else:
            keeper, removed = obs_b, obs_a

        new_embedding = await embed_fn(decision.text)
        merged = await obs_repo.merge(
            keeper_id=keeper.id,
            removed_id=removed.id,
            merged_text=decision.text,
            embedding=new_embedding,
            reason=f"merged with obs {removed.id} (sim={sim:.3f})",
        )

        if merged:
            _logger.info(
                "Merged obs %d + %d → %d: %s",
                obs_a.id, obs_b.id, keeper.id, decision.text[:80],
            )
            merges += 1
            # Update in-memory list: replace keeper, remove removed
            observations = [
                merged if o.id == keeper.id else o
                for o in observations
                if o.id != removed.id
            ]

    if merges > 0:
        _logger.info("Observation merge pass: %d merges", merges)

    return merges
