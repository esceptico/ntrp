import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from ntrp.constants import FRIDAY_WEEKDAY


def _to_dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def _to_json_list(v):
    if isinstance(v, str):
        return json.loads(v) if v else []
    return v if v is not None else []


class Recurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"


@dataclass
class ScheduledTask:
    task_id: str
    name: str
    description: str
    time_of_day: str  # "HH:MM" local time
    recurrence: Recurrence
    enabled: bool
    created_at: datetime
    next_run_at: datetime
    last_run_at: datetime | None
    notifiers: list[str]
    last_result: str | None
    running_since: datetime | None
    writable: bool

    def __post_init__(self):
        self.recurrence = Recurrence(self.recurrence) if isinstance(self.recurrence, str) else self.recurrence
        self.created_at = _to_dt(self.created_at)
        self.next_run_at = _to_dt(self.next_run_at)
        self.last_run_at = _to_dt(self.last_run_at)
        self.running_since = _to_dt(self.running_since)
        self.notifiers = _to_json_list(self.notifiers)
        self.enabled = bool(self.enabled)
        self.writable = bool(self.writable)


def compute_next_run(
    time_of_day: str,
    recurrence: Recurrence,
    after: datetime,
) -> datetime:
    """
    Compute next run time in UTC for a given local time-of-day.

    Args:
        time_of_day: "HH:MM" in local time
        recurrence: how often the task repeats
        after: UTC datetime to compute next run after

    Returns:
        UTC datetime for the next run
    """
    # Convert UTC 'after' to local time (system timezone)
    after_local = after.astimezone()

    hour, minute = (int(x) for x in time_of_day.split(":"))

    # Create candidate in local time
    candidate = after_local.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If we've already passed that time today, move to tomorrow
    if candidate <= after_local:
        candidate += timedelta(days=1)

    # Handle recurrence patterns
    if recurrence == Recurrence.WEEKDAYS:
        while candidate.weekday() > FRIDAY_WEEKDAY:
            candidate += timedelta(days=1)
    elif recurrence == Recurrence.WEEKLY:
        target_weekday = after_local.weekday()
        while candidate.weekday() != target_weekday:
            candidate += timedelta(days=1)

    # Convert back to UTC
    return candidate.astimezone(UTC)
