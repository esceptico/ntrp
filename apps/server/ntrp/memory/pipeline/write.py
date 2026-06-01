"""WriteSeam — the shared admit->write entry (CONTRACTS.md §10).

`remember()` and any future programmatic writer enter the pipeline here. The
seam is deliberately thin: it owns scope resolution + SourceRef construction +
the `bypass_admit` asymmetry, then runs the SAME admit->extract->reconcile path
as every other ingest (vision §1.7: `remember()` "carries no special pipeline;
it enters the same admit->write path as everything else"). There is no parallel
reconcile/judge here — the seam maps Reconcile's results onto a truthful
WriteOutcome and nothing more.

Flow:
  1. Wrap the request as a forced (remember) / judged (programmatic) CaptureUnit.
  2. Admit: `forced` units always ADMIT but still carry the recalled candidates
     downstream, so Extract+Reconcile reuse Admit's view of memory.
  3. Extract: atomize the admitted text into self-contained claims, each with a
     model-RESOLVED `canonical_subject` (§4.3). This is the step the old shortcut
     skipped — without it the subject was just the raw sentence and coreference
     never merged.
  4. Reconcile the extracted candidates, seeding prior_candidates from the recall.
  5. Map the ReconcileResults -> WriteOutcome (primary = first written/target).

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
    def __init__(self, store, reconciler, admit, extractor, *, model: str):
        self.store = store
        self.reconciler = reconciler
        self.admit = admit
        self.extractor = extractor
        self.model = model

    async def admit_and_write(self, request: WriteRequest) -> WriteOutcome:
        if not request.content or not request.content.strip():
            return WriteOutcome(written=False, item_id=None, reason="empty content")

        # 1+2. Admit. remember()/programmatic writers are `forced` (a user
        # assertion is maximal-novelty) but still run the gate so the recalled
        # candidates flow downstream; a non-bypass writer is actually judged.
        forced = request.bypass_admit
        admitted = await self.admit.admit(self._as_unit(request, forced=forced))
        if admitted.verdict is Verdict.REJECT:
            return WriteOutcome(
                written=False, item_id=None, reason="not admitted: " + admitted.reason
            )

        # 3. Extract — atomize + resolve canonical_subject (the step the old
        # shortcut skipped). No subject is fabricated from raw content here.
        extracted = await self.extractor.extract(admitted, model=self.model)
        if not extracted.candidates:
            return WriteOutcome(
                written=False, item_id=None, reason="nothing durable to extract"
            )

        # 4. Reconcile the extracted claims against the recalled view.
        try:
            results = await self.reconciler.reconcile(
                extracted.candidates, request.scope, prior_candidates=admitted.candidates
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

        # 5. Primary outcome = first claim that wrote a row, else the first NOOP.
        return self._to_outcome(self._primary(results))

    @staticmethod
    def _primary(results):
        for r in results:
            if r.written_id:
                return r
        return results[0]

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
