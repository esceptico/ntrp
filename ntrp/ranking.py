from collections import defaultdict


def rrf_merge(
    rankings: list[list[tuple[int, float]]],
    k: int = 60,
) -> dict[int, float]:
    """Reciprocal Rank Fusion to merge multiple ranked lists.

    Each ranking is a list of (item_id, score) tuples ordered by relevance.
    Returns a dict of item_id -> fused RRF score.
    """
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, (item_id, _) in enumerate(ranking):
            scores[item_id] += 1 / (k + rank + 1)
    return dict(scores)
