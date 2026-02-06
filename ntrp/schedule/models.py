from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class Recurrence(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"


@dataclass
class ScheduledTask:
    task_id: str
    description: str
    time_of_day: str  # "HH:MM" local time
    recurrence: Recurrence
    enabled: bool
    created_at: datetime
    next_run_at: datetime
    last_run_at: datetime | None
    notify_email: str | None
    last_result: str | None
    running_since: datetime | None

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
        self.enabled = bool(self.enabled)


def compute_next_run(
    time_of_day: str,
    recurrence: Recurrence,
    after: datetime,
) -> datetime:
    hour, minute = int(time_of_day[:2]), int(time_of_day[3:5])

    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if candidate <= after:
        candidate += timedelta(days=1)

    if recurrence == Recurrence.WEEKDAYS:
        while candidate.weekday() > 4:
            candidate += timedelta(days=1)
    elif recurrence == Recurrence.WEEKLY:
        target_weekday = after.weekday()
        while candidate.weekday() != target_weekday:
            candidate += timedelta(days=1)

    return candidate
