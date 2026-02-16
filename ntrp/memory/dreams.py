"""Dream pipeline: cluster cross-pollination + comparative evaluator.

Clusters facts by embedding similarity, cross-pollinates cluster pairs via LLM
to find structural patterns between unrelated domains, filters through a
comparative evaluator, and stores survivors.
"""

import math
import random
from collections import defaultdict
from collections.abc import Callable, Coroutine

import numpy as np
from pydantic import BaseModel

from ntrp.constants import (
    DREAM_CLUSTER_FACTOR,
    DREAM_EVAL_TEMPERATURE,
    DREAM_MIN_FACTS,
    DREAM_TEMPERATURE,
)
from ntrp.llm.router import get_completion_client
from ntrp.logging import get_logger
from ntrp.memory.models import Embedding, Fact
from ntrp.memory.prompts import DREAM_EVALUATOR_PROMPT, DREAM_PROMPT
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository

_logger = get_logger(__name__)

type EmbedFn = Callable[[str], Coroutine[None, None, Embedding]]


# --- Pydantic models for structured output ---


class DreamGeneration(BaseModel):
    bridge: str | None
    insight: str | None


class DreamEvaluation(BaseModel):
    selected: list[int]
    reasoning: str


# --- Internal data ---


class _DreamCandidate:
    __slots__ = ("bridge", "insight", "source_fact_ids")

    def __init__(self, bridge: str, insight: str, source_fact_ids: list[int]):
        self.bridge = bridge
        self.insight = insight
        self.source_fact_ids = source_fact_ids


# --- Clustering ---


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    return float(dot / (na * nb)) if na and nb else 0.0


def _kmeans(
    facts: dict[int, tuple[str, np.ndarray]],
    k: int,
    iterations: int = 20,
) -> dict[int, list[int]]:
    fids = list(facts.keys())
    if len(fids) < k:
        return {0: fids}

    dim = facts[fids[0]][1].shape[0]
    rng = random.Random(42)

    # k-means++ init
    centroids = [facts[rng.choice(fids)][1].copy()]
    for _ in range(k - 1):
        dists = []
        for fid in fids:
            emb = facts[fid][1]
            min_d = min(1.0 - _cosine(emb, c) for c in centroids)
            dists.append(min_d**2)
        total = sum(dists)
        r = rng.random() * total
        cumulative = 0.0
        for i, d in enumerate(dists):
            cumulative += d
            if cumulative >= r:
                centroids.append(facts[fids[i]][1].copy())
                break

    clusters: dict[int, list[int]] = defaultdict(list)
    for _ in range(iterations):
        clusters = defaultdict(list)
        for fid in fids:
            emb = facts[fid][1]
            best = max(range(k), key=lambda ki: _cosine(emb, centroids[ki]))
            clusters[best].append(fid)
        for ki in range(k):
            if not clusters[ki]:
                continue
            new_c = np.zeros(dim)
            for fid in clusters[ki]:
                new_c += facts[fid][1]
            centroids[ki] = new_c / len(clusters[ki])

    return dict(clusters)


def _centroid_nearest(facts: dict[int, tuple[str, np.ndarray]], cluster_fids: list[int]) -> int:
    dim = facts[cluster_fids[0]][1].shape[0]
    centroid = np.zeros(dim)
    for fid in cluster_fids:
        centroid += facts[fid][1]
    centroid /= len(cluster_fids)
    return max(cluster_fids, key=lambda fid: _cosine(facts[fid][1], centroid))


def _get_supporters(
    facts: dict[int, tuple[str, np.ndarray]],
    seed_fid: int,
    cluster_fids: list[int],
    n: int = 2,
) -> list[int]:
    scored = []
    seed_emb = facts[seed_fid][1]
    for fid in cluster_fids:
        if fid == seed_fid:
            continue
        sim = _cosine(seed_emb, facts[fid][1])
        scored.append((fid, sim))
    scored.sort(key=lambda x: -x[1])
    return [fid for fid, _ in scored[:n]]


# --- LLM calls ---


async def _generate_dream(
    facts: dict[int, tuple[str, np.ndarray]],
    core_a: int,
    supporters_a: list[int],
    core_b: int,
    supporters_b: list[int],
    model: str,
) -> DreamGeneration | None:
    sup_a = "\n".join(f'    - "{facts[f][0][:120]}"' for f in supporters_a)
    sup_b = "\n".join(f'    - "{facts[f][0][:120]}"' for f in supporters_b)

    prompt = DREAM_PROMPT.format(
        core_a=facts[core_a][0],
        supporters_a=sup_a or "    (none)",
        core_b=facts[core_b][0],
        supporters_b=sup_b or "    (none)",
    )

    try:
        client = get_completion_client(model)
        resp = await client.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=DreamGeneration,
            temperature=DREAM_TEMPERATURE,
        )
        content = resp.choices[0].message.content
        if not content:
            return None

        result = DreamGeneration.model_validate_json(content)
        if not result.bridge or not result.insight:
            return None
        return result

    except Exception as e:
        _logger.warning("Dream generation failed: %s", e)
        return None


async def _evaluate_batch(
    candidates: list[_DreamCandidate],
    model: str,
) -> list[int]:
    if not candidates:
        return []

    formatted = "\n".join(f"[{i}] BRIDGE: {c.bridge}\n    DREAM: {c.insight}" for i, c in enumerate(candidates))

    prompt = DREAM_EVALUATOR_PROMPT.format(n=len(candidates), candidates=formatted)

    try:
        client = get_completion_client(model)
        resp = await client.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=DreamEvaluation,
            temperature=DREAM_EVAL_TEMPERATURE,
        )
        content = resp.choices[0].message.content
        if not content:
            return []

        result = DreamEvaluation.model_validate_json(content)
        return [i for i in result.selected if 0 <= i < len(candidates)]

    except Exception as e:
        _logger.warning("Dream evaluation failed: %s", e)
        return []


# --- Pipeline ---


def _load_fact_embeddings(facts: list[Fact]) -> dict[int, tuple[str, np.ndarray]]:
    result = {}
    for f in facts:
        if f.embedding is not None and f.embedding.size > 0:
            result[f.id] = (f.text, f.embedding)
    return result


async def run_dream_pass(
    fact_repo: FactRepository,
    dream_repo: DreamRepository,
    model: str,
) -> int:
    all_facts = await fact_repo.list_all_with_embeddings()
    if len(all_facts) < DREAM_MIN_FACTS:
        _logger.debug("Dream pass skipped: %d facts < %d minimum", len(all_facts), DREAM_MIN_FACTS)
        return 0

    facts = _load_fact_embeddings(all_facts)
    if len(facts) < DREAM_MIN_FACTS:
        return 0

    k = max(4, int(math.sqrt(len(facts) / DREAM_CLUSTER_FACTOR)))
    clusters = _kmeans(facts, k)

    valid_clusters = [ki for ki in clusters if len(clusters[ki]) >= 2]
    if len(valid_clusters) < 2:
        _logger.debug("Dream pass skipped: fewer than 2 valid clusters")
        return 0

    # Generate dreams for all cluster pairs
    candidates: list[_DreamCandidate] = []

    for i in range(len(valid_clusters)):
        for j in range(i + 1, len(valid_clusters)):
            ki, kj = valid_clusters[i], valid_clusters[j]
            core_a = _centroid_nearest(facts, clusters[ki])
            core_b = _centroid_nearest(facts, clusters[kj])
            sups_a = _get_supporters(facts, core_a, clusters[ki], n=2)
            sups_b = _get_supporters(facts, core_b, clusters[kj], n=2)

            result = await _generate_dream(facts, core_a, sups_a, core_b, sups_b, model)
            if result and result.bridge and result.insight:
                source_fids = [core_a, core_b] + sups_a + sups_b
                candidates.append(
                    _DreamCandidate(
                        bridge=result.bridge,
                        insight=result.insight,
                        source_fact_ids=source_fids,
                    )
                )

    _logger.info(
        "Dream generation: %d candidates from %d cluster pairs",
        len(candidates),
        len(valid_clusters) * (len(valid_clusters) - 1) // 2,
    )

    if not candidates:
        return 0

    # Evaluate batch
    selected_indices = await _evaluate_batch(candidates, model)
    survivors = [candidates[i] for i in selected_indices]

    _logger.info("Dream evaluation: %d/%d survived", len(survivors), len(candidates))

    # Store survivors
    stored = 0
    for candidate in survivors:
        await dream_repo.create(
            bridge=candidate.bridge,
            insight=candidate.insight,
            source_fact_ids=candidate.source_fact_ids,
        )
        stored += 1

    return stored
