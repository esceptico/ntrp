"""Fact merge pass: find and merge near-duplicate facts.

Similar to observation_merge but for atomic facts. Uses embedding similarity
to find candidates, LLM to decide merge vs skip, then transfers entity refs
and updates observation source_fact_ids.
"""

import json
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Literal

from pydantic import BaseModel

from ntrp.agent import Role
from ntrp.constants import FACT_MERGE_SIMILARITY_THRESHOLD, FACT_MERGE_TEMPERATURE
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Fact
from ntrp.memory.prompts import FACT_MERGE_PROMPT
from ntrp.memory.retrieval import find_top_pair
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]
type AtomicFn = Callable[[], AbstractAsyncContextManager[None]]


class FactMergeAction(BaseModel):
    action: Literal["same", "different"]
    text: str | None = None
    reason: str | None = None


async def _llm_merge_decision(
    fact_a: Fact,
    fact_b: Fact,
    model: str,
) -> FactMergeAction:
    prompt = FACT_MERGE_PROMPT.render(
        id_a=fact_a.id,
        text_a=fact_a.text,
        id_b=fact_b.id,
        text_b=fact_b.text,
    )

    try:
        client = get_completion_client(model)
        resp = await client.completion(
            model=model,
            messages=[{"role": Role.USER, "content": prompt}],
            response_format=FactMergeAction,
            temperature=FACT_MERGE_TEMPERATURE,
        )
        content = resp.choices[0].message.content
        if not content:
            return FactMergeAction(action="different", reason="empty response")
        return FactMergeAction.model_validate_json(content)
    except Exception as e:
        _logger.warning("Fact merge LLM failed: %s", e)
        return FactMergeAction(action="different", reason=f"llm error: {e}")


def _pick_keeper(a: Fact, b: Fact) -> tuple[Fact, Fact]:
    """Pick the better fact to keep. Prefer: more entity refs > higher access > newer."""
    a_refs = len(a.entity_refs)
    b_refs = len(b.entity_refs)
    if a_refs != b_refs:
        return (a, b) if a_refs >= b_refs else (b, a)
    if a.access_count != b.access_count:
        return (a, b) if a.access_count >= b.access_count else (b, a)
    return (a, b) if a.created_at >= b.created_at else (b, a)


async def _replace_source_fact_id(
    conn, table: Literal["observations", "dreams"], removed_id: int, keeper_id: int
) -> None:
    """Replace removed_id with keeper_id in source_fact_ids column, deduplicating."""
    rows = await conn.execute_fetchall(
        f"SELECT id, source_fact_ids FROM {table} WHERE source_fact_ids LIKE ?",
        (f"%{removed_id}%",),
    )
    for row in rows:
        raw_ids = json.loads(row["source_fact_ids"]) if row["source_fact_ids"] else []
        if removed_id not in raw_ids:
            continue  # LIKE matched a substring (e.g., id=5 matching id=15)
        new_ids = [keeper_id if fid == removed_id else fid for fid in raw_ids]
        seen = set()
        deduped = [fid for fid in new_ids if not (fid in seen or seen.add(fid))]
        await conn.execute(
            f"UPDATE {table} SET source_fact_ids = ? WHERE id = ?",
            (json.dumps(deduped), row["id"]),
        )


async def _merge_facts(
    keeper: Fact,
    removed: Fact,
    merged_text: str,
    embedding: Embedding,
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    dream_repo: DreamRepository | None = None,
) -> None:
    # Update keeper text + embedding
    await fact_repo.update_text(keeper.id, merged_text, embedding)

    # Transfer entity refs from removed to keeper (skip duplicates)
    keeper_refs = await fact_repo.get_entity_refs(keeper.id)
    keeper_entity_ids = {r.entity_id for r in keeper_refs if r.entity_id}
    keeper_names = {r.name.lower() for r in keeper_refs}
    removed_refs = await fact_repo.get_entity_refs(removed.id)
    for ref in removed_refs:
        if ref.entity_id and ref.entity_id not in keeper_entity_ids:
            await fact_repo.add_entity_ref(keeper.id, ref.name, ref.entity_id)
            keeper_entity_ids.add(ref.entity_id)
        elif not ref.entity_id and ref.name.lower() not in keeper_names:
            await fact_repo.add_entity_ref(keeper.id, ref.name, None)
            keeper_names.add(ref.name.lower())

    # Transfer access count (additive) — direct SQL, not reinforce() which deduplicates
    if removed.access_count > 0:
        await fact_repo.conn.execute(
            "UPDATE facts SET access_count = access_count + ? WHERE id = ?",
            (removed.access_count, keeper.id),
        )

    # Update source_fact_ids in observations and dreams: replace removed.id with keeper.id
    await _replace_source_fact_id(obs_repo.conn, "observations", removed.id, keeper.id)
    if dream_repo:
        await _replace_source_fact_id(dream_repo.conn, "dreams", removed.id, keeper.id)

    # Delete the removed fact
    await fact_repo.delete(removed.id)


async def fact_merge_pass(
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    model: str,
    embed_fn: EmbedFn,
    atomic: AtomicFn | None = None,
    threshold: float = FACT_MERGE_SIMILARITY_THRESHOLD,
    dream_repo: DreamRepository | None = None,
) -> int:
    facts = await fact_repo.list_all_with_embeddings()
    if len(facts) < 2:
        return 0

    skipped_pairs: set[tuple[int, int]] = set()
    merges = 0

    while True:
        pair = find_top_pair(facts, skipped_pairs, threshold)
        if pair is None:
            break

        i, j, sim = pair
        fact_a, fact_b = facts[i], facts[j]

        decision = await _llm_merge_decision(fact_a, fact_b, model)

        if decision.action == "different":
            _logger.debug(
                "Fact merge skip: %d + %d (sim=%.3f): %s",
                fact_a.id,
                fact_b.id,
                sim,
                decision.reason,
            )
            skipped_pairs.add((min(fact_a.id, fact_b.id), max(fact_a.id, fact_b.id)))
            continue

        keeper, removed = _pick_keeper(fact_a, fact_b)
        merged_text = decision.text or keeper.text

        # Embedding outside atomic (network call)
        embedding = await embed_fn(merged_text)

        # DB writes inside atomic
        async with atomic() if atomic else nullcontext():
            await _merge_facts(keeper, removed, merged_text, embedding, fact_repo, obs_repo, dream_repo)

        _logger.info(
            "Merged fact %d + %d → %d (sim=%.3f): %s",
            fact_a.id,
            fact_b.id,
            keeper.id,
            sim,
            merged_text[:80],
        )
        merges += 1

        # Update in-memory list
        updated_keeper = await fact_repo.get(keeper.id)
        if updated_keeper:
            facts = [updated_keeper if f.id == keeper.id else f for f in facts if f.id != removed.id]
        else:
            facts = [f for f in facts if f.id != removed.id and f.id != keeper.id]

    if merges > 0:
        _logger.info("Fact merge pass: %d merges", merges)
        async with atomic() if atomic else nullcontext():
            await fact_repo.cleanup_orphaned_entities()

    return merges
