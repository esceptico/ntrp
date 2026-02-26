from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from jinja2 import Environment

_env = Environment(trim_blocks=True, lstrip_blocks=True)

# Event type constants — used in EventTrigger.event_type and tool descriptions
EVENT_APPROACHING = "event_approaching"
NEW_EMAIL = "new_email"

_EVENT_APPROACHING_CONTEXT = _env.from_string("""Event: {{ summary }}
Starts in: {{ minutes_until }} minutes
Start time: {{ start.isoformat() }}
{% if location %}
Location: {{ location }}
{% endif %}
{% if attendees %}
Attendees: {{ attendees | join(', ') }}
{% endif %}""")

_NEW_EMAIL_CONTEXT = _env.from_string("""From: {{ sender }}
Subject: {{ subject }}
Received: {{ received_at.isoformat() }}

{{ snippet }}""")


@runtime_checkable
class TriggerEvent(Protocol):
    @property
    def event_type(self) -> str: ...

    @property
    def event_key(self) -> str: ...

    def format_context(self) -> str: ...


@dataclass(frozen=True)
class EventApproaching:
    event_id: str
    summary: str
    start: datetime
    minutes_until: int
    location: str | None
    attendees: tuple[str, ...]

    @property
    def event_type(self) -> str:
        return EVENT_APPROACHING

    @property
    def event_key(self) -> str:
        return self.event_id

    def format_context(self) -> str:
        return _EVENT_APPROACHING_CONTEXT.render(
            summary=self.summary,
            minutes_until=self.minutes_until,
            start=self.start,
            location=self.location,
            attendees=self.attendees,
        )


@dataclass(frozen=True)
class NewEmail:
    email_id: str
    subject: str
    sender: str
    snippet: str
    received_at: datetime

    @property
    def event_type(self) -> str:
        return NEW_EMAIL

    @property
    def event_key(self) -> str:
        return self.email_id

    def format_context(self) -> str:
        return _NEW_EMAIL_CONTEXT.render(
            sender=self.sender,
            subject=self.subject,
            received_at=self.received_at,
            snippet=self.snippet,
        )


TRIGGER_EVENT_TYPES: tuple[type[TriggerEvent], ...] = (EventApproaching, NewEmail)
