"""Observation merge pass: recursive pairwise deduplication.

Finds the most similar observation pair above threshold, asks LLM to merge
or skip, re-embeds, repeats until no pairs remain above threshold.
"""

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Literal

from pydantic import BaseModel

from ntrp.agent import Role
from ntrp.constants import (
    OBSERVATION_MERGE_SIMILARITY_THRESHOLD,
    OBSERVATION_MERGE_TEMPERATURE,
)
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Observation
from ntrp.memory.prompts import OBSERVATION_MERGE_PROMPT
from ntrp.memory.retrieval import SimilarityPairQueue
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]
type AtomicFn = Callable[[], AbstractAsyncContextManager[None]]


class MergeAction(BaseModel):
    action: Literal["merge", "skip"]
    text: str | None = None
    reason: str | None = None


async def _llm_merge_decision(
    obs_a: Observation,
    obs_b: Observation,
    model: str,
) -> MergeAction:
    prompt = OBSERVATION_MERGE_PROMPT.render(
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
            messages=[{"role": Role.USER, "content": prompt}],
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
    atomic: AtomicFn | None = None,
    threshold: float = OBSERVATION_MERGE_SIMILARITY_THRESHOLD,
) -> int:
    observations = await obs_repo.list_all_with_embeddings()
    if len(observations) < 2:
        return 0

    candidates = await asyncio.to_thread(SimilarityPairQueue, observations, threshold)
    skipped_pairs: set[tuple[int, int]] = set()
    merges = 0

    while True:
        pair = await asyncio.to_thread(candidates.pop, skipped_pairs)
        if pair is None:
            break

        obs_a, obs_b, sim = pair.left, pair.right, pair.score

        decision = await _llm_merge_decision(obs_a, obs_b, model)

        if decision.action == "skip":
            _logger.debug(
                "Merge skip: obs %d + %d (sim=%.3f): %s",
                obs_a.id,
                obs_b.id,
                sim,
                decision.reason,
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

        # Embedding outside atomic (network call)
        new_embedding = await embed_fn(decision.text)

        # DB writes inside atomic
        async with atomic() if atomic else nullcontext():
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
                obs_a.id,
                obs_b.id,
                keeper.id,
                decision.text[:80],
            )
            merges += 1
            await asyncio.to_thread(candidates.replace, merged, removed.id)
        else:
            skipped_pairs.add((min(obs_a.id, obs_b.id), max(obs_a.id, obs_b.id)))

    if merges > 0:
        _logger.info("Observation merge pass: %d merges", merges)

    return merges
