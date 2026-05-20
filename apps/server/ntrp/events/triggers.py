from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from jinja2 import Environment

_env = Environment(trim_blocks=True, lstrip_blocks=True)

# Event type constants — used in EventTrigger.event_type and tool descriptions
EVENT_APPROACHING = "event_approaching"
KNOWLEDGE_OBJECT_CHANGED = "knowledge_object_changed"
_EVENT_APPROACHING_CONTEXT = _env.from_string("""Event: {{ summary }}
Starts in: {{ minutes_until }} minutes
Start time: {{ start.isoformat() }}
{% if location %}
Location: {{ location }}
{% endif %}
{% if attendees %}
Attendees: {{ attendees | join(', ') }}
{% endif %}""")
_KNOWLEDGE_OBJECT_CHANGED_CONTEXT = _env.from_string("""Knowledge object {{ action }}: {{ object_type }}#{{ object_id }}
Status: {{ status }}
Title: {{ title }}
{% if scope %}
Scope: {{ scope }}
{% endif %}
{% if source_ids %}
Sources: {{ source_ids | join(', ') }}
{% endif %}""")


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
class KnowledgeObjectChanged:
    action: str
    object_id: int
    object_type: str
    status: str
    title: str
    scope: str | None
    source_ids: tuple[str, ...]
    updated_at: str

    @property
    def event_type(self) -> str:
        return KNOWLEDGE_OBJECT_CHANGED

    @property
    def event_key(self) -> str:
        return f"knowledge:{self.action}:{self.object_id}:{self.status}:{self.updated_at}"

    def format_context(self) -> str:
        return _KNOWLEDGE_OBJECT_CHANGED_CONTEXT.render(
            action=self.action,
            object_id=self.object_id,
            object_type=self.object_type,
            status=self.status,
            title=self.title,
            scope=self.scope,
            source_ids=self.source_ids,
        )


TRIGGER_EVENT_TYPES: tuple[type[TriggerEvent], ...] = (EventApproaching, KnowledgeObjectChanged)
