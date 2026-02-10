import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from ntrp.constants import FRIDAY_WEEKDAY


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
        if isinstance(self.recurrence, str):
            self.recurrence = Recurrence(self.recurrence)
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
        if isinstance(self.next_run_at, str):
            self.next_run_at = datetime.fromisoformat(self.next_run_at)
        if isinstance(self.last_run_at, str):
            self.last_run_at = datetime.fromisoformat(self.last_run_at)
        if isinstance(self.running_since, str):
            self.running_since = datetime.fromisoformat(self.running_since)
        if isinstance(self.notifiers, str):
            self.notifiers = json.loads(self.notifiers) if self.notifiers else []
        elif self.notifiers is None:
            self.notifiers = []
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
