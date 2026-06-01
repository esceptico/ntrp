"""WriteSeam — the shared admit->write entry (CONTRACTS.md §10).

`remember()` and any future programmatic writer enter the pipeline here. The
seam is deliberately thin: it owns scope resolution + SourceRef construction +
the `bypass_admit` asymmetry, then hands the single user-authored claim to the
ONE reconcile implementation (Reconciler). There is no second, parallel
reconcile/judge here (CONTRACTS §10 RESOLUTION) — the seam maps Reconcile's
result onto a truthful WriteOutcome and nothing more.

Flow:
  1. Build a one-element ClaimCandidate from the request (no translation layer).
  2. Gate (skipped when bypass_admit): wrap as a forced CaptureUnit, run
     AdmitGate.admit. `forced` units always ADMIT but still carry the recalled
     candidates downstream, so Reconcile reuses Admit's view of memory.
  3. Reconcile the single candidate, seeding prior_candidates from the recall.
  4. Map the single ReconcileResult -> WriteOutcome.

The seam never writes to the store directly — Reconcile is the only claim
writer (CONTRACTS §7). On Reconcile failure with a user assertion
(bypass_admit), we do NOT silently drop: WriteOutcome reports the failure and
the caller surfaces it (the user can retry); we never fabricate a stored id.
"""

from dataclasses import dataclass

from ntrp.logging import get_logger
from ntrp.memory.models import Provenance, Scope, SourceRef, now_iso
from ntrp.memory.pipeline.types import (
    BoundaryKind,
    CaptureUnit,
    ClaimCandidate,
    ExchangeRole,
    Op,
    RawExchange,
    Verdict,
    Watermark,
)

_logger = get_logger(__name__)


@dataclass
class WriteRequest:
    content: str
    scope: Scope
    provenance: Provenance
    source_refs: list[SourceRef]
    valid_from: str | None = None
    bypass_admit: bool = False


@dataclass
class WriteOutcome:
    written: bool
    item_id: str | None
    reason: str


# Human-facing reason strings, keyed by the reconcile op (CONTRACTS §10).
_OUTCOME_REASON = {
    Op.ADD: "Remembered.",
    Op.UPDATE: "Updated — superseded a prior claim.",
    Op.CONTRADICT: "Updated — superseded a prior claim.",
    Op.NOOP: "Already known (corroborated).",
}


class WriteSeam:
    def __init__(self, store, reconciler, admit):
        self.store = store
        self.reconciler = reconciler
        self.admit = admit

    async def admit_and_write(self, request: WriteRequest) -> WriteOutcome:
        if not request.content or not request.content.strip():
            return WriteOutcome(written=False, item_id=None, reason="empty content")

        candidate = ClaimCandidate(
            content=request.content.strip(),
            source_refs=list(request.source_refs),
            provenance=request.provenance,
            canonical_subject=request.content.strip(),
            scope=request.scope,
        )

        prior_candidates: list = []
        if not request.bypass_admit:
            result = await self.admit.admit(self._as_unit(request, forced=False))
            prior_candidates = result.candidates
            if result.verdict is Verdict.REJECT:
                return WriteOutcome(
                    written=False, item_id=None, reason="not admitted: " + result.reason
                )
        else:
            # bypass the worth-gate, but still build a consistent recall view so
            # Reconcile can corroborate/supersede (CONTRACTS §10 asymmetry). A
            # forced unit ADMITs deterministically and carries the candidates.
            forced = await self.admit.admit(self._as_unit(request, forced=True))
            prior_candidates = forced.candidates

        try:
            results = await self.reconciler.reconcile(
                [candidate], request.scope, prior_candidates=prior_candidates
            )
        except Exception as e:
            # Never lose a user assertion silently: report the failure truthfully
            # rather than fabricating a stored id; the caller can retry.
            _logger.warning("write seam reconcile failed: %s", e)
            return WriteOutcome(
                written=False, item_id=None, reason=f"reconcile failed: {e}"
            )

        if not results:
            return WriteOutcome(
                written=False, item_id=None, reason="reconcile produced no result"
            )

        return self._to_outcome(results[0])

    def _as_unit(self, request: WriteRequest, *, forced: bool) -> CaptureUnit:
        """Wrap a single write request as a one-exchange, forced CaptureUnit so
        it can flow through AdmitGate unchanged. `remember()` is always forced
        (user assertion); a non-bypass writer still marks it forced=False so the
        gate actually judges it."""
        ref = request.source_refs[0] if request.source_refs else SourceRef(
            kind="write_seam", ref="local"
        )
        exch = RawExchange(turn_id="w0", text=request.content, source_ref=ref)
        wm = Watermark(source_id="write_seam", cursor="0", swept_at=now_iso())
        return CaptureUnit(
            scope=request.scope,
            role=ExchangeRole.LIVE_CHAT,
            exchanges=[exch],
            source_refs=list(request.source_refs) or [ref],
            boundary=BoundaryKind.EXPLICIT,
            watermark=wm,
            forced=forced,
        )

    def _to_outcome(self, result) -> WriteOutcome:
        reason = _OUTCOME_REASON.get(result.op, "Remembered.")
        if result.op is Op.NOOP:
            return WriteOutcome(
                written=False, item_id=result.target_claim_id, reason=reason
            )
        return WriteOutcome(written=True, item_id=result.written_id, reason=reason)
