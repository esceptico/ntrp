import math
from datetime import UTC, datetime, timedelta

from ntrp.constants import (
    ARCHIVE_DECAY_THRESHOLD,
    ARCHIVE_FACT_MIN_AGE_DAYS,
    ARCHIVE_OBSERVATION_MIN_AGE_DAYS,
    ARCHIVE_OBSERVATION_STALENESS_DAYS,
    MEMORY_DECAY_RATE,
    RECENCY_SIGMA_HOURS,
)

_SECONDS_PER_HOUR = 3600


def decay_score(
    last_accessed_at: datetime,
    access_count: int,
    decay_rate: float = MEMORY_DECAY_RATE,
) -> float:
    now = datetime.now(UTC)
    hours = (now - last_accessed_at).total_seconds() / _SECONDS_PER_HOUR
    time_decay = decay_rate**hours
    access_boost = 1 + math.log1p(access_count) * 0.5
    return time_decay * access_boost


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


def should_archive_fact(
    consolidated_at: datetime | None,
    created_at: datetime,
    last_accessed_at: datetime,
    access_count: int,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    if consolidated_at is None:
        return False
    age = now - created_at
    if age < timedelta(days=ARCHIVE_FACT_MIN_AGE_DAYS):
        return False
    return decay_score(last_accessed_at, access_count) < ARCHIVE_DECAY_THRESHOLD


def should_archive_observation(
    created_at: datetime,
    updated_at: datetime,
    last_accessed_at: datetime,
    access_count: int,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    age = now - created_at
    if age < timedelta(days=ARCHIVE_OBSERVATION_MIN_AGE_DAYS):
        return False
    staleness = now - updated_at
    if staleness < timedelta(days=ARCHIVE_OBSERVATION_STALENESS_DAYS):
        return False
    return decay_score(last_accessed_at, access_count) < ARCHIVE_DECAY_THRESHOLD
