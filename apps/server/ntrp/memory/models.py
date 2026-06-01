"""Stage-2 memory schema models.

Storage layer only. `memory_items` is claims-only: every row is a claim, an
atomic self-contained proposition. Subject coreference is the `canonical_subject`
attribute on the claim — there are no entity rows. Relationships are role-typed
claim->claim edges in `memory_item_parents` (evidence / supersedes / contradicts),
forming a walkable provenance DAG.

Lenses are NOT memory. A lens is a view (a named, criterion-defined projection
over claims). Lenses live in a separate `lenses` registry table (`LensRow`),
never in `memory_items`, never as a graph node, never edge-linked. Membership is
a computed projection (cached, not authoritative).

No pipeline, no retrieval ranking, no LLM judgment lives here.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now_iso() -> str:
    """Canonical ISO-8601 UTC timestamp. The store relies on every timestamp
    being UTC + same offset so TEXT comparison equals chronological order."""
    return datetime.now(UTC).isoformat()


class Status(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ScopeKind(StrEnum):
    USER = "user"
    PROJECT = "project"
    SESSION = "session"


class Provenance(StrEnum):
    """Ordinal trust source for a claim, most-trusted first."""

    USER_AUTHORED = "user_authored"
    RECORDED = "recorded"
    INFERRED = "inferred"
    EXTERNAL = "external"


class Feedback(StrEnum):
    NONE = "none"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


class EdgeRole(StrEnum):
    """Claim->claim edge roles. There is no membership edge; lenses are views."""

    EVIDENCE = "evidence"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"


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
    """A claim row.

    Every row is a claim: an atomic, self-contained proposition. Subject
    coreference is the `canonical_subject` attribute — the merge key reconcile
    resolves; there are no entity rows. Claims carry validity + source_refs +
    transparent trust signals.
    """

    id: str
    content: str
    canonical_subject: str
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

    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class MemoryEdge:
    """A role-typed claim->claim edge: child --role--> parent.

    Forms the walkable provenance/contradiction DAG (evidence / supersedes /
    contradicts). `position` orders multi-parent edges. Lenses are never edge
    participants.
    """

    child_id: str
    parent_id: str
    role: EdgeRole
    position: int = 0
    created_at: str = field(default_factory=now_iso)


# --- Lens registry (views over claims; NOT memory) ---


class LensDetailLevel(StrEnum):
    GIST = "gist"
    STRUCTURED = "structured"
    DOSSIER = "dossier"


class LensRenderMode(StrEnum):
    """How a lens page is laid out. A presentation dial, never a membership gate.

    FLAT renders all `in`-claims as one synthesized page; GROUPED_BY_SUBJECT
    buckets them by the `canonical_subject` claim attribute into per-subject
    profiles (e.g. a "persons" lens → a profile per person). Grouping reads only
    the claim attribute — no entity rows, no new query.
    """

    FLAT = "flat"
    GROUPED_BY_SUBJECT = "grouped_by_subject"


class LensProvenance(StrEnum):
    USER_AUTHORED = "user_authored"
    INDUCED = "induced"


class LensStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class LensRow:
    """A lens DEFINITION — a view, not a memory item.

    A lens is a named, criterion-defined projection over claims. It owns no
    claims, is never a graph node, and is never edge-linked. The definition lives
    as an editable markdown FILE at ``NTRP_DIR/memory/lenses/<slug>.md`` (NOT a DB
    row): `id` is the file slug, `name` is the frontmatter `directory`, and
    `criterion` is the file body (a ``## Belongs`` section + optional ``## Profile
    shape`` list — the membership judge reads Belongs, the projector shapes profiles
    from Profile shape). `page` is the cached synthesized markdown projection (None
    until first computed). Membership is a computed projection cached in
    `lens_membership_cache` keyed by the slug, never an edge.
    """

    id: str
    name: str
    criterion: str
    scope: Scope

    entity_type: str = "thing"
    detail_level: LensDetailLevel = LensDetailLevel.STRUCTURED
    render_mode: LensRenderMode = LensRenderMode.FLAT
    provenance: LensProvenance = LensProvenance.USER_AUTHORED
    status: LensStatus = LensStatus.ACTIVE
    page: str | None = None

    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


class MembershipDecision(StrEnum):
    IN = "in"
    OUT = "out"
    DEFER = "defer"


@dataclass
class MembershipVerdict:
    """A cached membership decision for (lens, claim). A cache, not graph truth:
    drop the whole cache and nothing breaks except projection latency."""

    lens_id: str
    claim_id: str
    decision: MembershipDecision
    rationale: str | None = None
    scored_at: str = field(default_factory=now_iso)
