from collections.abc import Callable, Sequence

from ntrp.memory.models import Fact, Observation
from ntrp.memory.retrieval import SimilarityPairQueue
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository

DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD = 0.98
DEFAULT_DUPLICATE_CANDIDATE_LIMIT = 20
_PREVIEW_LIMIT = 160


def _preview(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= _PREVIEW_LIMIT else f"{compact[: _PREVIEW_LIMIT - 3]}..."


def _active_facts(facts: Sequence[Fact]) -> list[Fact]:
    return [fact for fact in facts if fact.status.value == "active"]


def _candidate_pairs(
    items: Sequence[Fact] | Sequence[Observation],
    *,
    text: Callable[[Fact | Observation], str],
    limit: int,
    threshold: float,
) -> list[dict]:
    queue = SimilarityPairQueue(items, threshold)
    skipped: set[tuple[int, int]] = set()
    candidates: list[dict] = []

    while len(candidates) < limit:
        pair = queue.pop(skipped)
        if pair is None:
            break

        left_id = int(pair.left.id)
        right_id = int(pair.right.id)
        ids = [left_id, right_id] if left_id < right_id else [right_id, left_id]
        skipped.add((ids[0], ids[1]))
        left, right = (pair.left, pair.right) if left_id <= right_id else (pair.right, pair.left)
        candidates.append(
            {
                "ids": ids,
                "score": round(float(pair.score), 4),
                "left": _preview(text(left)),
                "right": _preview(text(right)),
            }
        )

    return candidates


async def duplicate_memory_candidates(
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
    *,
    limit: int = DEFAULT_DUPLICATE_CANDIDATE_LIMIT,
    threshold: float = DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
) -> dict[str, list[dict]]:
    facts = _active_facts(await fact_repo.list_all_with_embeddings())
    observations = await obs_repo.list_all_with_embeddings()

    return {
        "facts": _candidate_pairs(
            facts,
            text=lambda item: item.text,
            limit=limit,
            threshold=threshold,
        ),
        "observations": _candidate_pairs(
            observations,
            text=lambda item: item.summary,
            limit=limit,
            threshold=threshold,
        ),
    }
