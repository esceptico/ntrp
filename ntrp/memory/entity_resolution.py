import math
from datetime import datetime
from difflib import SequenceMatcher

from ntrp.constants import (
    ENTITY_SCORE_COOCCURRENCE_WEIGHT,
    ENTITY_SCORE_NAME_WEIGHT,
    ENTITY_SCORE_TEMPORAL_WEIGHT,
    ENTITY_TEMPORAL_NEUTRAL,
    ENTITY_TEMPORAL_SIGMA_HOURS,
)

_PREFIX_BASE = 0.7
_PREFIX_RANGE = 0.3
_COOCCURRENCE_THRESHOLD = 0.8
_COOCCURRENCE_BASE = 0.7
_COOCCURRENCE_NAME_RANGE = 0.3
_HIGH_NAME_SIM_THRESHOLD = 0.95
_HIGH_NAME_SIM_BASE = 0.5
_SECONDS_PER_HOUR = 3600


def name_similarity(a: str, b: str) -> float:
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()

    if a_lower == b_lower:
        return 1.0

    if a_lower.startswith(b_lower) or b_lower.startswith(a_lower):
        ratio = min(len(a_lower), len(b_lower)) / max(len(a_lower), len(b_lower))
        return _PREFIX_BASE + _PREFIX_RANGE * ratio

    return SequenceMatcher(None, a_lower, b_lower).ratio()


def temporal_proximity_score(
    t1: datetime | None,
    t2: datetime | None,
    sigma_hours: float = ENTITY_TEMPORAL_SIGMA_HOURS,
) -> float:
    if t1 is None or t2 is None:
        return ENTITY_TEMPORAL_NEUTRAL

    hours = abs((t1 - t2).total_seconds()) / _SECONDS_PER_HOUR
    return math.exp(-hours / sigma_hours)


def compute_resolution_score(
    name_sim: float,
    co_occurrence: float,
    temporal: float,
) -> float:
    if co_occurrence >= _COOCCURRENCE_THRESHOLD:
        return _COOCCURRENCE_BASE + _COOCCURRENCE_NAME_RANGE * name_sim

    if co_occurrence == 0:
        if name_sim >= _HIGH_NAME_SIM_THRESHOLD:
            return _HIGH_NAME_SIM_BASE + ENTITY_SCORE_TEMPORAL_WEIGHT * temporal
        return name_sim * ENTITY_SCORE_NAME_WEIGHT

    return (
        co_occurrence * ENTITY_SCORE_COOCCURRENCE_WEIGHT
        + name_sim * ENTITY_SCORE_NAME_WEIGHT
        + temporal * ENTITY_SCORE_TEMPORAL_WEIGHT
    )
