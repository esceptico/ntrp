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
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
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
        key = part.strip().lower()
        if key not in DAY_NAMES:
            raise ValueError(f"Invalid day: {key}. Use: mon,tue,wed,thu,fri,sat,sun")
        days.add(DAY_NAMES[key])

    if not days:
        raise ValueError("No days specified")

    return frozenset(days)


def resolve_days(days: str) -> frozenset[int]:
    if days in DAY_KEYWORDS:
        return DAY_KEYWORDS[days]
    return parse_days(days)


def validate_days(days: str) -> str:
    if days in VALID_DAY_SPECS:
        return days
    parse_days(days)  # raises if invalid
    return days


def parse_interval(raw: str) -> timedelta:
    match = _INTERVAL_RE.match(raw.strip().lower())
    if not match or not (match.group(1) or match.group(2)):
        raise ValueError(f"Invalid interval: '{raw}'. Use e.g. '30m', '2h', '1h30m'")

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    if hours == 0 and minutes == 0:
        raise ValueError("Interval must be positive")

    return timedelta(hours=hours, minutes=minutes)


def normalize_lead_minutes(raw: int | str | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    normalized = raw.strip()
    if not normalized:
        return None
    interval = parse_interval(normalized)
    return int(interval.total_seconds() // 60)


def _advance_to_days(candidate: datetime, target_days: frozenset[int]) -> datetime:
    for offset in range(DAYS_IN_WEEK):
        shifted = candidate + timedelta(days=offset)
        if shifted.weekday() in target_days:
            return shifted
    return candidate


def compute_next_schedule(at: str, days: str, after: datetime) -> datetime:
    local_tz = after.astimezone().tzinfo
    after_local = after.astimezone(local_tz)
    schedule_time = time.fromisoformat(at)

    # Build candidate in naive local, then localize to handle DST gaps/overlaps
    candidate_naive = after_local.replace(
        hour=schedule_time.hour,
        minute=schedule_time.minute,
        second=0,
        microsecond=0,
        tzinfo=None,
    )

    if candidate_naive <= after_local.replace(tzinfo=None):
        candidate_naive += timedelta(days=1)

    if days == "weekly":
        target_weekday = after_local.weekday()
        days_ahead = (target_weekday - candidate_naive.weekday()) % DAYS_IN_WEEK
        if days_ahead:
            candidate_naive += timedelta(days=days_ahead)
    else:
        # _advance_to_days works on naive datetimes too
        candidate_tz = candidate_naive.replace(tzinfo=local_tz)
        candidate_tz = _advance_to_days(candidate_tz, resolve_days(days))
        candidate_naive = candidate_tz.replace(tzinfo=None)

    # fold=0 picks the first occurrence during fall-back overlap;
    # for spring-forward gaps, Python adjusts to valid time automatically
    candidate = candidate_naive.replace(tzinfo=local_tz, fold=0)
    return candidate.astimezone(UTC)


def compute_next_interval(
    every: str,
    days: str | None,
    after: datetime,
    start: str | None = None,
    end: str | None = None,
) -> datetime:
    interval = parse_interval(every)
    candidate = after + interval

    if start and end:
        local = candidate.astimezone()
        t_start = time.fromisoformat(start)
        t_end = time.fromisoformat(end)
        local_time = local.time().replace(second=0, microsecond=0)

        if local_time > t_end or local_time < t_start:
            # Jump to start time on the next day.
            candidate = local.replace(
                hour=t_start.hour,
                minute=t_start.minute,
                second=0,
                microsecond=0,
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
        if not self.at and not self.every:
            raise ValueError("Either 'at' or 'every' must be set")
        if self.at and self.every:
            raise ValueError("Cannot set both 'at' and 'every'")

        if self.at:
            self.at = _validate_time(self.at, "at")
        if self.every:
            parse_interval(self.every)
        if self.days:
            validate_days(self.days)

        if (self.start or self.end) and not self.every:
            raise ValueError("'start'/'end' only applies to interval mode")
        if bool(self.start) != bool(self.end):
            raise ValueError("Both 'start' and 'end' must be set together")

        if self.start:
            self.start = _validate_time(self.start, "start")
        if self.end:
            self.end = _validate_time(self.end, "end")

    def params(self) -> dict[str, str | None]:
        return {"at": self.at, "days": self.days, "every": self.every, "start": self.start, "end": self.end}

    @property
    def label(self) -> str:
        base = f"every {self.every}" if self.every else self.at
        if self.start and self.end:
            base += f" ({self.start}–{self.end})"
        if self.days:
            return f"{base} · {self.days}"
        return base

    @property
    def one_shot(self) -> bool:
        return self.at is not None and self.days is None and self.every is None

    def next_run(self, after: datetime) -> datetime | None:
        if self.one_shot:
            return None
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
            if self.lead_minutes <= 0:
                raise ValueError("'lead_minutes' must be positive")
            if self.lead_minutes > MONITOR_EVENT_APPROACHING_HORIZON_MINUTES:
                raise ValueError(
                    f"'lead_minutes' cannot exceed monitor horizon ({MONITOR_EVENT_APPROACHING_HORIZON_MINUTES}m)",
                )
        elif self.lead_minutes is not None:
            raise ValueError("'lead_minutes' is only supported for 'event_approaching'")

    def params(self) -> dict[str, str | int | None]:
        return {"event_type": self.event_type, "lead_minutes": self.lead_minutes}

    @property
    def label(self) -> str:
        if self.event_type == EVENT_APPROACHING and self.lead_minutes:
            return f"on:{self.event_type} ({self.lead_minutes}m)"
        return f"on:{self.event_type}"

    @property
    def one_shot(self) -> bool:
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
    *,
    at: str | None,
    days: str | None,
    every: str | None,
    event_type: str | None,
    lead_minutes: int | str | None,
    start: str | None,
    end: str | None,
) -> tuple[Trigger, datetime | None]:
    trigger = TimeTrigger(at=at, days=days, every=every, start=start, end=end)
    return trigger, _next_run_for_time(trigger, datetime.now(UTC))


def _build_event_trigger(
    *,
    at: str | None,
    days: str | None,
    every: str | None,
    event_type: str | None,
    lead_minutes: int | str | None,
    start: str | None,
    end: str | None,
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
    at: str | None = None,
    days: str | None = None,
    every: str | None = None,
    event_type: str | None = None,
    lead_minutes: int | str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[Trigger, datetime | None]:
    handler = BUILD_DISPATCH.get(trigger_type)
    if handler is None:
        raise ValueError(f"Invalid trigger_type '{trigger_type}'. Use: time, event")

    return handler(
        at=at,
        days=days,
        every=every,
        event_type=event_type,
        lead_minutes=lead_minutes,
        start=start,
        end=end,
    )


ParseHandler = Callable[[dict], Trigger]


def _parse_time_trigger(payload: dict) -> Trigger:
    # New format
    if "at" in payload or "every" in payload:
        return TimeTrigger(
            at=payload.get("at"),
            days=payload.get("days"),
            every=payload.get("every"),
            start=payload.get("start"),
            end=payload.get("end"),
        )

    # Legacy format: time_of_day + recurrence/repeat
    time_of_day = payload["time_of_day"]
    recurrence = payload.get("recurrence") or payload.get("repeat", "once")
    if recurrence == "once":
        return TimeTrigger(at=time_of_day)
    return TimeTrigger(at=time_of_day, days=recurrence)


def _parse_event_trigger(payload: dict) -> Trigger:
    return EventTrigger(
        event_type=payload["event_type"],
        lead_minutes=payload.get("lead_minutes"),
    )


PARSE_DISPATCH: dict[str, ParseHandler] = {
    "time": _parse_time_trigger,
    "event": _parse_event_trigger,
}


def parse_trigger(raw: str) -> Trigger:
    payload = json.loads(raw)
    handler = PARSE_DISPATCH.get(payload["type"])
    if handler is None:
        raise ValueError(f"Unknown trigger type: {payload['type']}")
    return handler(payload)


@dataclass
class Automation:
    task_id: str
    name: str
    description: str
    model: str | None
    trigger: Trigger
    enabled: bool
    created_at: datetime
    next_run_at: datetime | None
    last_run_at: datetime | None
    notifiers: list[str]
    last_result: str | None
    running_since: datetime | None
    writable: bool
