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


class Provenance(StrEnum):
    """Epistemic class — the load-bearing distinction of the derivation spec."""

    GROUND = "ground"     # extracted from experience by the curator
    DERIVED = "derived"   # inferred by the dreamer from other records


class Standing(StrEnum):
    """Derivation lifecycle (CUPMem tri-state). `unresolved` = a premise died and
    the derivation awaits re-judgment — excluded from agent recall, visible in UI."""

    ACTIVE = "active"
    UNRESOLVED = "unresolved"
    RETIRED = "retired"


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
    provenance: str = Provenance.GROUND
    standing: str = Standing.ACTIVE
    depth: int = 0                  # longest premise chain to ground (0 = ground)


@dataclass(frozen=True)
class Justification:
    """Why a derived record exists: the premise set that produced it. A derived
    record may hold SEVERAL justifications (JTMS) — it survives premise death
    while any justification's premises all live."""

    id: str
    derived_id: str
    premise_ids: tuple[str, ...]
    mode: str                       # deduction | induction | abduction
    question: str                   # the salient question this derivation answered
    created_at: str = field(default_factory=now_iso)
