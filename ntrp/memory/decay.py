import math
from datetime import UTC, datetime

from ntrp.constants import MEMORY_DECAY_RATE, RECENCY_SIGMA_HOURS

_SECONDS_PER_HOUR = 3600


def decay_score(
    last_accessed_at: datetime,
    access_count: int,
    decay_rate: float = MEMORY_DECAY_RATE,
) -> float:
    now = datetime.now(UTC)
    hours = (now - last_accessed_at).total_seconds() / _SECONDS_PER_HOUR
    strength = math.log(access_count + 1) + 1
    return decay_rate ** (hours / strength)


def recency_boost(
    event_time: datetime,
    sigma_hours: float = RECENCY_SIGMA_HOURS,
    reference_time: datetime | None = None,
) -> float:
    ref = reference_time or datetime.now(UTC)
    hours = (ref - event_time).total_seconds() / _SECONDS_PER_HOUR
    if hours < 0:
        hours = 0
    return math.exp(-hours / sigma_hours)
