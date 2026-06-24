"""Memory models: scoped artifacts in one flat pool.

Scopes are default visibility metadata, not a graph hierarchy. Records are
atomic artifacts with sparse metadata and optional source evidence.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SourceRef:
    kind: str
    ref: str
    captured_at: str = field(default_factory=now_iso)
    scope_kind: str | None = None
    scope_key: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "ref": self.ref,
            "captured_at": self.captured_at,
            "scope_kind": self.scope_kind,
            "scope_key": self.scope_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceRef":
        return cls(
            kind=str(data.get("kind") or "unknown"),
            ref=str(data.get("ref") or ""),
            captured_at=str(data.get("captured_at") or now_iso()),
            scope_kind=data.get("scope_kind"),
            scope_key=data.get("scope_key"),
        )


class Kind(StrEnum):
    """Small v1 memory function types.

    Keep this intentionally boring. Preferences are facts about the user;
    project facts are facts with project scope; procedures that should steer
    behavior are directives. Free-form junk-drawer `note` records are avoided
    for new writes.
    """

    DIRECTIVE = "directive"
    FACT = "fact"
    SOURCE = "source"
    CHANGELOG = "changelog"
    OBSERVATION = "observation"  # low-trust raw integration item (gmail/slack/calendar); the dream mines these
    LESSON = "lesson"  # continual-learning playbook item — a working-pattern the agent DISTILLED (vs directive = user-stated)


# Source-trust precedence: a direct user statement outranks a curator-compiled
# fact, which outranks a passively-ingested integration fact, which outranks a
# machine-authored dream insight. Used by synthesis (phrasing/exclusion) so
# low-trust sources aren't laundered into user-confidence claims.
TRUST_LEVEL: dict[str, int] = {"user": 4, "curator": 3, "chat_turn": 3, "dreamer": 1}
TRUST_DEFAULT = 2  # integration:* and unknown


def source_trust(kind: str) -> int:
    return TRUST_LEVEL.get((kind or "").split(":")[0].lower(), TRUST_DEFAULT)


@dataclass
class Record:
    id: str
    text: str
    kind: str = Kind.FACT
    scope_kind: str | None = None
    scope_key: str | None = None
    created_at: str = field(default_factory=now_iso)
    last_confirmed_at: str = field(default_factory=now_iso)
    superseded_by: str | None = None
    pinned: bool = False
    source_ref: SourceRef | None = None
