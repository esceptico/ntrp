from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum

from ntrp.constants import DAYS_IN_WEEK, FRIDAY_WEEKDAY


class Repeat(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"


@dataclass
class ScheduledTask:
    task_id: str
    name: str
    description: str
    time_of_day: str
    repeat: Repeat
    enabled: bool
    created_at: datetime
    next_run_at: datetime
    last_run_at: datetime | None
    notifiers: list[str]
    last_result: str | None
    running_since: datetime | None
    writable: bool

    @property
    def is_one_shot(self) -> bool:
        return self.repeat == Repeat.ONCE


def compute_next_run(time_of_day: str, repeat: Repeat, after: datetime) -> datetime:
    after_local = after.astimezone()
    t = time.fromisoformat(time_of_day)
    candidate = after_local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)

    if candidate <= after_local:
        candidate += timedelta(days=1)

    match repeat:
        case Repeat.WEEKDAYS if candidate.weekday() > FRIDAY_WEEKDAY:
            candidate += timedelta(days=DAYS_IN_WEEK - candidate.weekday())
        case Repeat.WEEKLY:
            target = after_local.weekday()
            days_ahead = (target - candidate.weekday()) % DAYS_IN_WEEK
            if days_ahead:
                candidate += timedelta(days=days_ahead)

    return candidate.astimezone(UTC)
