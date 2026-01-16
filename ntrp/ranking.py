from collections import defaultdict


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> list[int]:
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            scores[item_id] += 1 / (k + rank + 1)

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [item_id for item_id, _ in sorted_items]
