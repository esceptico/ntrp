"""Shared transient pipeline shapes (CONTRACTS §2).

The single shared home for every stage's data shapes. These are NOT stored rows
and add NO columns to the store — they reuse the Stage-2 `models.py` types
verbatim. A `ClaimCandidate`'s content/source_refs/provenance map by trivial
field-copy onto a `MemoryItem(kind=CLAIM, …)` at write time.
"""

from dataclasses import dataclass, field
from enum import Enum

from ntrp.memory.models import Kind, MemoryItem, Provenance, Scope, SourceRef

__all__ = [
    "Scope",
    "SourceRef",
    "BoundaryKind",
    "ExchangeRole",
    "RawExchange",
    "Watermark",
    "CaptureUnit",
    "Verdict",
    "AdmitResult",
    "ClaimCandidate",
    "DroppedSpan",
    "ExtractResult",
    "Op",
    "ReconcileResult",
    "LintOpKind",
    "LintReport",
    "Retrieval",
    "RankedItem",
    "RetrievedContext",
]


# --- Capture output -------------------------------------------------
class BoundaryKind(Enum):
    EXPLICIT = "explicit"  # /close or remember()
    SESSION = "session"  # chat session / automation run finished
    IDLE = "idle"  # no activity within idle window
    SEMANTIC = "semantic"  # background topic-shift cut
    CAP = "cap"  # max-window force-cut (runaway stream)


class ExchangeRole(Enum):
    LIVE_CHAT = "live_chat"
    AUTOMATION = "automation"
    SCHEDULED = "scheduled"


@dataclass
class RawExchange:
    turn_id: str  # stable id within the unit, used as the grounding token
    text: str
    source_ref: SourceRef  # pointer back into the immutable raw layer


@dataclass
class Watermark:
    source_id: str
    cursor: str  # raw store's own monotonic position
    swept_at: str  # ISO instant work began (advance-after-success)


@dataclass
class CaptureUnit:
    scope: Scope
    role: ExchangeRole
    exchanges: list[RawExchange]
    source_refs: list[SourceRef]  # one per exchange; == the refs claims inherit
    boundary: BoundaryKind
    watermark: Watermark
    forced: bool = False  # explicit (/close, remember) → pin ADMIT in Admit


# --- Admit output ---------------------------------------------------
class Verdict(Enum):
    ADMIT = "admit"
    REJECT = "reject"


@dataclass
class AdmitResult:
    verdict: Verdict
    unit: CaptureUnit
    residual: str | None  # part memory could NOT predict; None on REJECT
    reason: str  # one line, for trace + eval audit
    candidates: list[MemoryItem]  # recalled set the judgment was made against
    forced: bool  # correction/remember short-circuit fired


# --- Extract output -------------------------------------------------
@dataclass
class ClaimCandidate:
    content: str  # atomic, self-contained, coref resolved inline
    source_refs: list[SourceRef]  # the SUBSET grounding THIS claim
    provenance: Provenance  # coarse rule (CONTRACTS §6)
    canonical_subject: str  # model-canonicalized referent; the recall key
    scope: Scope
    subject_surfaces: list[str] = field(default_factory=list)  # observed surfaces; recall+alias fuel


@dataclass
class DroppedSpan:
    turn_id: str | None
    attempted_content: str
    reason: str  # grounded_false | subject_unresolved | evidence_missing


@dataclass
class ExtractResult:
    candidates: list[ClaimCandidate]
    dropped: list[DroppedSpan]


# --- Reconcile output -----------------------------------------------
class Op(Enum):
    ADD = "add"
    UPDATE = "update"
    NOOP = "noop"
    CONTRADICT = "contradict"


@dataclass
class ReconcileResult:
    claim_index: int
    op: Op
    subject_lens_id: str | None
    written_id: str | None = None
    target_claim_id: str | None = None
    subject_created: bool = False
    escalated: bool = False


# --- Lint output ----------------------------------------------------
class LintOpKind(Enum):
    MERGE = "merge"
    INVALIDATE = "invalidate"
    DROP_ORPHAN = "drop_orphan"
    NOOP = "noop"


@dataclass
class LintReport:
    scope: Scope
    merged: int
    invalidated: int
    dropped: int
    contradictions_flagged: int
    degraded: bool  # FTS unavailable → neighborhood collapsed


# --- Retrieve I/O ---------------------------------------------------
@dataclass
class Retrieval:  # input config object (>5 fields per CLAUDE.md)
    goal: str
    scope: Scope
    also_scopes: list[Scope] = field(default_factory=list)
    valid_at: str | None = None
    token_budget: int = 2000
    kinds: tuple[Kind, ...] = (Kind.CLAIM,)
    lens_hint: str | None = None


@dataclass
class RankedItem:
    item: MemoryItem
    fts_rank: float | None
    vector_rank: float | None
    rrf: float
    freshness: float
    provenance_ord: int
    corroboration: int
    order_score: float  # transparent scalar; ORDERS, never gates


@dataclass
class RetrievedContext:
    rendered: str
    items: list[RankedItem]
    degraded: bool
    diagnostics: dict
