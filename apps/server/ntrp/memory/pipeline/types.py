"""Shared transient pipeline shapes (CONTRACTS §2).

The single shared home for every stage's data shapes. These are NOT stored rows
and add NO columns to the store — they reuse the Stage-2 `models.py` types
verbatim. A `ClaimCandidate`'s content/source_refs/provenance map by trivial
field-copy onto a `MemoryItem(kind=CLAIM, …)` at write time.
"""

from dataclasses import dataclass, field
from enum import Enum, StrEnum

from ntrp.memory.models import (
    Feedback,
    Kind,
    LensDetailLevel,
    MemoryItem,
    Provenance,
    Scope,
    SourceRef,
)

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
    "MembershipDecision",
    "MembershipVerdict",
    "BackfillReport",
    "CoverageAdvisory",
    "RenderedClaim",
    "ProjectedPage",
    "PageEditKind",
    "PageEditOp",
    "WriteBackResult",
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


# --- Lens (Stage-4) transient shapes --------------------------------
# LENS_CONTRACTS §1.2. No rows, no columns; reuse the frozen Stage-2 store.
# NOTE (scope boundary): only the shapes the membership scorer
# (pipeline/membership.py LensMembership) produces are defined here —
# MembershipDecision + MembershipVerdict (score/score_into_active_lenses output),
# BackfillReport (backfill_lens result), CoverageAdvisory (coverage result). The
# remaining §1.2 shapes (RenderedClaim, ProjectedPage, PageEditKind, PageEditOp,
# WriteBackResult) belong to the project/writeback/lens components and are added
# by those builds, not here.
class MembershipDecision(StrEnum):
    IN = "in"
    OUT = "out"
    DEFER = "defer"


@dataclass
class MembershipVerdict:
    claim_id: str
    lens_id: str
    decision: MembershipDecision
    rationale: str


@dataclass
class BackfillReport:
    lens_id: str
    scanned: int
    members_added: int
    capped: bool


@dataclass
class CoverageAdvisory:
    lens_id: str
    scope_pool: int  # active claims in scope
    member_count: int  # active member_of members
    ratio: float  # member_count / scope_pool (0.0 if pool == 0)
    generic: bool  # ratio >= GENERIC_RATIO — ADVISORY ONLY, never a gate
    suggestion: str  # "split" | "narrow" prose for the user


# --- Lens page projection + write-back shapes (LENS_CONTRACTS §1.2) --
# Owned by pipeline/project.py (LensProjector) and pipeline/writeback.py
# (LensWriteBack). `RenderedClaim.claim_id` is the load-bearing token: the page
# is human prose, but every editable unit carries its stable id, so write-back is
# structured BY CLAIM ID — never by reparsing prose position (§3).
@dataclass
class RenderedClaim:
    """The structured spine behind the page prose; write-back diffs against this."""

    claim_id: str  # stable anchor — the entire write-back contract
    content: str
    provenance: Provenance
    corroboration: int
    feedback: Feedback
    source_refs: list[SourceRef]


@dataclass
class ProjectedPage:
    lens_id: str
    detail: LensDetailLevel
    markdown: str  # what the user reads / edits
    blocks: list[RenderedClaim]  # served spine; write-back diffs against this
    synthesized: bool  # False = degraded raw-list fallback (never blank)
    coverage: CoverageAdvisory | None


class PageEditKind(StrEnum):
    EDIT = "edit"
    REJECT = "reject"
    ACCEPT = "accept"
    ADD = "add"
    EDIT_CRITERION = "edit_criterion"


@dataclass
class PageEditOp:
    kind: PageEditKind
    claim_id: str | None = None  # required for edit/reject/accept; None for add/criterion
    new_text: str | None = None  # edit: successor; add: new claim; criterion: new criterion


@dataclass
class WriteBackResult:
    applied: list[tuple[PageEditKind, str]]
    rejected: list[tuple[PageEditOp, str]]  # op + reason
    rederive_triggered: bool
