"""Shared transient pipeline shapes (CONTRACTS §2).

The single shared home for every stage's data shapes. These are NOT stored rows
and add NO columns to the store — they reuse the Stage-2 `models.py` types
verbatim. A `ClaimCandidate`'s content/source_refs/provenance map by trivial
field-copy onto a `MemoryItem(kind=CLAIM, …)` at write time.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from ntrp.memory.models import (
    Feedback,
    LensDetailLevel,
    MembershipDecision,
    MembershipVerdict,
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
    "ProjectedGroup",
    "ProjectedPage",
    "PageEditKind",
    "PageEditOp",
    "WriteBackResult",
    "LensGenStage",
    "ProgressFn",
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
    valid_from: str | None = None  # caller-supplied event time (remember); claims inherit it


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
    valid_from: str | None = None  # caller-supplied event/validity time; None -> now at write


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
    canonical_subject: str
    written_id: str | None = None
    target_claim_id: str | None = None
    subject_is_new: bool = False
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
# A lens is a VIEW: membership is a COMPUTED PROJECTION cached in
# lens_membership_cache (a cache, not graph truth). MembershipDecision +
# MembershipVerdict are the cache-row shapes, defined in models.py and re-exported
# here for the pipeline. BackfillReport (cache-refresh result) + CoverageAdvisory
# (a pure COUNT advisory) describe the projection.


@dataclass
class BackfillReport:
    lens_id: str
    scanned: int
    members_added: int  # `in` verdicts written to the cache
    capped: bool


@dataclass
class CoverageAdvisory:
    lens_id: str
    scope_pool: int  # active claims in scope
    member_count: int  # `in`-decision claims in the membership cache
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
class ProjectedGroup:
    """One profile row of a projected lens page (presentation only).

    For grouped-by-subject rendering, this is a canonical_subject bucket. For
    directory-style flat lenses, this is a generated `## Name` section. Grouping
    is post-membership presentation.
    """

    subject: str  # display label for this profile row
    markdown: str  # synthesized profile body
    blocks: list[RenderedClaim]  # row claims; write-back diffs by id
    synthesized: bool  # False = degraded raw-list fallback for this bucket


@dataclass
class ProjectedPage:
    lens_id: str
    detail: LensDetailLevel
    markdown: str  # what the user reads / edits
    blocks: list[RenderedClaim]  # served spine; write-back diffs against this
    synthesized: bool  # False = degraded raw-list fallback (never blank)
    coverage: CoverageAdvisory | None
    groups: list[ProjectedGroup] | None = None  # profile rows when the page is row-shaped


class PageEditKind(StrEnum):
    EDIT = "edit"
    REJECT = "reject"
    ACCEPT = "accept"
    EDIT_CRITERION = "edit_criterion"


@dataclass
class PageEditOp:
    kind: PageEditKind
    claim_id: str | None = None  # required for edit/reject/accept; None for criterion
    new_text: str | None = None  # edit: successor; criterion: new criterion


@dataclass
class WriteBackResult:
    applied: list[tuple[PageEditKind, str]]
    rejected: list[tuple[PageEditOp, str]]  # op + reason
    rederive_triggered: bool


# --- Lens page generation status (async, non-blocking GET) ----------
# Generating a page is many sequential LLM calls; the GET must not block on it.
# LensGenStage is the milestone the projector reports through a progress callback
# while a background task drives generation (pipeline/lens_generation.py). It is
# presentation/orchestration only — it gates no membership and no synthesis.
class LensGenStage(StrEnum):
    CREATING = "creating"  # task accepted, nothing run yet
    SCORING = "scoring"  # membership refresh / re-validate
    SYNTHESIZING = "synthesizing"  # per-subject / page synthesis
    READY = "ready"  # page materialized + cached
    ERROR = "error"  # generation raised


# A progress callback the projector calls as it advances; kwargs carry the current
# subject + "i/n" while synthesizing grouped buckets.
ProgressFn = Callable[..., None]
