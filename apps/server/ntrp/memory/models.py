"""Stage-2 memory schema models.

Storage layer only. One object table (`memory_items`) holds every durable
knowledge unit (claims) and the editable lens objects, discriminated by `kind`.
Relationships are role-typed edges in `memory_item_parents`, forming a walkable
provenance DAG.

No pipeline, no retrieval ranking, no LLM judgment lives here.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now_iso() -> str:
    """Canonical ISO-8601 UTC timestamp. The store relies on every timestamp
    being UTC + same offset so TEXT comparison equals chronological order."""
    return datetime.now(UTC).isoformat()


class Kind(StrEnum):
    CLAIM = "claim"
    LENS = "lens"


class Status(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ScopeKind(StrEnum):
    USER = "user"
    PROJECT = "project"
    SESSION = "session"


class Provenance(StrEnum):
    """Ordinal trust source, most-trusted first.

    For claims: user_authored > recorded > inferred > external.
    For lenses only `induced` / `user_authored` are meaningful, but the column
    is shared; the schema does not branch on the distinction.
    """

    USER_AUTHORED = "user_authored"
    RECORDED = "recorded"
    INFERRED = "inferred"
    EXTERNAL = "external"
    INDUCED = "induced"


class Feedback(StrEnum):
    NONE = "none"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


class EdgeRole(StrEnum):
    EVIDENCE = "evidence"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    MEMBER_OF = "member_of"


class LensDetailLevel(StrEnum):
    GIST = "gist"
    STRUCTURED = "structured"
    DOSSIER = "dossier"


@dataclass(frozen=True)
class SourceRef:
    """A typed pointer into the immutable raw layer.

    Raw is never stored as memory; this only points at it. `kind` names the raw
    store (chat_turn, tool_run, email, file, dex_log, ...), `ref` is its opaque
    id/uri within that store.
    """

    kind: str
    ref: str
    captured_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "ref": self.ref, "captured_at": self.captured_at}

    @staticmethod
    def from_dict(d: dict) -> "SourceRef":
        return SourceRef(kind=d["kind"], ref=d["ref"], captured_at=d["captured_at"])


@dataclass
class Scope:
    """Mandatory scoping. No global implicit scope.

    `key` is the scoping id for project/session; None only for user scope.
    """

    kind: ScopeKind
    key: str | None = None

    def __post_init__(self):
        if isinstance(self.kind, str):
            self.kind = ScopeKind(self.kind)
        if self.kind is ScopeKind.USER:
            self.key = None
        elif not self.key:
            raise ValueError(f"scope {self.kind} requires a key")


@dataclass
class MemoryItem:
    """A row in the single object table.

    Claims carry validity + source_refs + trust signals. Lenses carry
    criterion/page/detail_level. Shared columns (id, kind, content, scope,
    provenance, timestamps) apply to both. Lens-only and claim-only columns are
    nullable (fork F1 resolved to a polymorphic table — see SCHEMA.md).
    """

    id: str
    kind: Kind
    content: str
    scope: Scope
    provenance: Provenance

    status: Status = Status.ACTIVE
    valid_from: str | None = None
    invalid_at: str | None = None

    source_refs: list[SourceRef] = field(default_factory=list)

    # Transparent trust signals — stored separately, never multiplied into one float.
    corroboration: int = 0
    last_relevant_at: str | None = None
    feedback: Feedback = Feedback.NONE

    # Lens-only fields (NULL for claims).
    lens_name: str | None = None
    lens_criterion: str | None = None
    lens_kind: str | None = None
    lens_page: str | None = None
    lens_detail_level: LensDetailLevel | None = None
    lens_exclusive: bool = False

    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class MemoryEdge:
    """A role-typed edge: child --role--> parent.

    Forms the walkable provenance DAG. `position` orders multi-parent edges.
    """

    child_id: str
    parent_id: str
    role: EdgeRole
    position: int = 0
    created_at: str = field(default_factory=now_iso)
