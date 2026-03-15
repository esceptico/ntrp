import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal

from ntrp.constants import (
    AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES,
    DAYS_IN_WEEK,
    MONITOR_EVENT_APPROACHING_HORIZON_MINUTES,
)
from ntrp.events.triggers import EVENT_APPROACHING

DAY_NAMES: dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}
WEEKDAY_SET = frozenset(range(5))
ALL_DAYS = frozenset(range(7))

DAY_KEYWORDS: dict[str, frozenset[int]] = {
    "daily": ALL_DAYS,
    "weekdays": WEEKDAY_SET,
}
VALID_DAY_SPECS = frozenset((*DAY_KEYWORDS.keys(), "weekly"))

_INTERVAL_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m?)?$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_days(raw: str) -> frozenset[int]:
    days: set[int] = set()

    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue

        if token in DAY_KEYWORDS:
            days.update(DAY_KEYWORDS[token])
        elif token in DAY_NAMES:
            days.add(DAY_NAMES[token])
        else:
            raise ValueError(f"Invalid day: '{token}'. Use: {', '.join(DAY_NAMES)} / daily / weekdays")

    return frozenset(days) if days else ALL_DAYS


def resolve_days(days: str) -> frozenset[int]:
    return parse_days(days)


def validate_days(days: str) -> str:
    parse_days(days)
    return days.strip().lower()


def parse_interval(raw: str) -> timedelta:
    if not (match := _INTERVAL_RE.match(raw.strip().lower())) or not (match.group(1) or match.group(2)):
        raise ValueError(f"Invalid interval: '{raw}'. Use e.g. '30m', '2h', '1h30m'")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    total = timedelta(hours=hours, minutes=minutes)
    if total < timedelta(minutes=1):
        raise ValueError("Interval must be at least 1 minute")
    return total


def normalize_lead_minutes(raw: int | str | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        td = parse_interval(raw)
        return int(td.total_seconds() / 60)
    return int(raw)


def _advance_to_days(candidate: datetime, target_days: frozenset[int]) -> datetime:
    for _ in range(DAYS_IN_WEEK):
        if candidate.weekday() in target_days:
            return candidate
        candidate += timedelta(days=1)
    return candidate


def compute_next_schedule(at: str, days: str, after: datetime) -> datetime:
    local_now = after.astimezone()
    hour, minute = (int(x) for x in at.split(":"))
    target_days = resolve_days(days)

    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)

    candidate = _advance_to_days(candidate, target_days)
    return candidate.astimezone(UTC)


def compute_next_interval(
    every: str,
    days: str | None,
    after: datetime,
    start: str | None = None,
    end: str | None = None,
) -> datetime:
    delta = parse_interval(every)
    local_now = after.astimezone()
    candidate = local_now + delta

    if start:
        h, m = (int(x) for x in start.split(":"))
        window_start = time(h, m)
    else:
        window_start = None

    if end:
        h, m = (int(x) for x in end.split(":"))
        window_end = time(h, m)
    else:
        window_end = None

    if window_start and candidate.time() < window_start:
        candidate = candidate.replace(hour=window_start.hour, minute=window_start.minute, second=0, microsecond=0)

    if window_end and candidate.time() >= window_end:
        candidate = (candidate + timedelta(days=1)).replace(
            hour=window_start.hour if window_start else 0,
            minute=window_start.minute if window_start else 0,
            second=0, microsecond=0,
        ) + timedelta(days=1)

    if days:
        candidate = _advance_to_days(candidate, resolve_days(days))

    return candidate.astimezone(UTC)


@dataclass
class TimeTrigger:
    type: Literal["time"] = "time"
    at: str | None = None
    days: str | None = None
    every: str | None = None
    start: str | None = None
    end: str | None = None

    def __post_init__(self) -> None:
        if self.at:
            self.at = _validate_time(self.at, "at")
        if self.days:
            self.days = validate_days(self.days)
        if self.start:
            self.start = _validate_time(self.start, "start")
        if self.end:
            self.end = _validate_time(self.end, "end")
        if self.every:
            parse_interval(self.every)

        if not self.at and not self.every:
            raise ValueError("Either 'at' (specific time) or 'every' (interval) is required")
        if self.at and self.every:
            raise ValueError("'at' and 'every' are mutually exclusive")
        if self.every and not self.days and not self.start and not self.end:
            pass  # Pure interval, runs continuously
        if (self.start or self.end) and not self.every:
            raise ValueError("'start'/'end' time windows require 'every' (interval mode)")
        if self.start and self.end and self.start >= self.end:
            raise ValueError(f"'start' ({self.start}) must be before 'end' ({self.end})")

    def params(self) -> dict:
        d: dict = {}
        if self.at:
            d["at"] = self.at
        if self.days:
            d["days"] = self.days
        if self.every:
            d["every"] = self.every
        if self.start:
            d["start"] = self.start
        if self.end:
            d["end"] = self.end
        return d

    def next_run(self, after: datetime) -> datetime:
        if self.every:
            return compute_next_interval(self.every, self.days, after, self.start, self.end)
        return compute_next_schedule(self.at, self.days, after)


@dataclass
class EventTrigger:
    event_type: str
    lead_minutes: int | None = None
    type: Literal["event"] = "event"

    def __post_init__(self) -> None:
        self.lead_minutes = normalize_lead_minutes(self.lead_minutes)

        if self.event_type == EVENT_APPROACHING:
            if self.lead_minutes is None:
                self.lead_minutes = AUTOMATION_EVENT_APPROACHING_DEFAULT_LEAD_MINUTES
            max_lead = MONITOR_EVENT_APPROACHING_HORIZON_MINUTES
            if self.lead_minutes > max_lead:
                raise ValueError(
                    f"lead_minutes={self.lead_minutes} exceeds the monitor horizon ({max_lead}m). "
                    f"Use {max_lead} or less."
                )

    def params(self) -> dict:
        d: dict = {"event_type": self.event_type}
        if self.lead_minutes is not None:
            d["lead_minutes"] = self.lead_minutes
        return d

    @property
    def is_one_shot(self) -> bool:
        return False

    def next_run(self, after: datetime) -> datetime | None:
        return None


Trigger = TimeTrigger | EventTrigger


def _validate_time(value: str, label: str) -> str:
    match = _TIME_RE.match(value.strip())
    if not match or not (0 <= int(match.group(1)) <= 23 and 0 <= int(match.group(2)) <= 59):
        raise ValueError(f"Invalid {label} format '{value}'. Use HH:MM (24h)")
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"


def _next_run_for_time(trigger: TimeTrigger, now: datetime) -> datetime:
    if trigger.every:
        return compute_next_interval(trigger.every, trigger.days, now, trigger.start, trigger.end)
    if trigger.days:
        return compute_next_schedule(trigger.at, trigger.days, now)
    return compute_next_schedule(trigger.at, "daily", now)


BuildHandler = Callable[..., tuple[Trigger, datetime | None]]


def _build_time_trigger(
    *, at: str | None, days: str | None, every: str | None,
    event_type: str | None, lead_minutes: int | str | None, start: str | None, end: str | None,
) -> tuple[Trigger, datetime | None]:
    trigger = TimeTrigger(at=at, days=days, every=every, start=start, end=end)
    return trigger, _next_run_for_time(trigger, datetime.now(UTC))


def _build_event_trigger(
    *, at: str | None, days: str | None, every: str | None,
    event_type: str | None, lead_minutes: int | str | None, start: str | None, end: str | None,
) -> tuple[Trigger, datetime | None]:
    if not event_type:
        raise ValueError("'event_type' is required for event trigger")
    return EventTrigger(event_type=event_type, lead_minutes=lead_minutes), None


BUILD_DISPATCH: dict[str, BuildHandler] = {
    "time": _build_time_trigger,
    "event": _build_event_trigger,
}


def build_trigger(
    trigger_type: str,
    at: str | None = None, days: str | None = None, every: str | None = None,
    event_type: str | None = None, lead_minutes: int | str | None = None,
    start: str | None = None, end: str | None = None,
) -> tuple[Trigger, datetime | None]:
    if (handler := BUILD_DISPATCH.get(trigger_type)) is None:
        raise ValueError(f"Invalid trigger_type '{trigger_type}'. Use: time, event")
    return handler(at=at, days=days, every=every, event_type=event_type, lead_minutes=lead_minutes, start=start, end=end)


ParseHandler = Callable[[dict], Trigger]


def _parse_time_trigger(payload: dict) -> Trigger:
    if "at" in payload or "every" in payload:
        return TimeTrigger(
            at=payload.get("at"), days=payload.get("days"), every=payload.get("every"),
            start=payload.get("start"), end=payload.get("end"),
        )
    # Legacy format
    time_of_day = payload["time_of_day"]
    recurrence = payload.get("recurrence") or payload.get("repeat", "once")
    if recurrence == "once":
        return TimeTrigger(at=time_of_day)
    return TimeTrigger(at=time_of_day, days=recurrence)


def _parse_event_trigger(payload: dict) -> Trigger:
    return EventTrigger(event_type=payload["event_type"], lead_minutes=payload.get("lead_minutes"))


PARSE_DISPATCH: dict[str, ParseHandler] = {
    "time": _parse_time_trigger,
    "event": _parse_event_trigger,
}


def parse_trigger(raw: str) -> Trigger:
    payload = json.loads(raw)
    if (handler := PARSE_DISPATCH.get(payload["type"])) is None:
        raise ValueError(f"Unknown trigger type: {payload['type']}")
    return handler(payload)
