"""Flat memory schema. A Record is one atomic memory unit in a single flat pool —
no scope/project partition. The old scope_kind/scope_key survive only as
provenance metadata carried by SourceRef (never a query key)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SourceRef:
    """A typed pointer into the raw layer (chat_turn, curator, ...). `scope_kind`/
    `scope_key` are pure provenance (e.g. the project a record came from); they are
    never a query partition."""

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

    @staticmethod
    def from_dict(d: dict) -> "SourceRef":
        return SourceRef(
            kind=d["kind"],
            ref=d["ref"],
            captured_at=d["captured_at"],
            scope_kind=d.get("scope_kind"),
            scope_key=d.get("scope_key"),
        )


class Kind(StrEnum):
    FACT = "fact"
    ACTION = "action"
    PREFERENCE = "preference"
    NOTE = "note"


@dataclass
class Record:
    id: str
    text: str                       # self-contained; survives retrieval alone
    kind: str = Kind.NOTE           # open set — plain str, unseen kinds don't crash
    created_at: str = field(default_factory=now_iso)
    last_confirmed_at: str = field(default_factory=now_iso)
    superseded_by: str | None = None
    pinned: bool = False
    source_ref: SourceRef | None = None
