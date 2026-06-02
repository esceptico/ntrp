"""MemoryPipeline — the integration seam that assembles the Stage-3 pipeline.

This is the ONE place the pipeline components are wired together over a live
MemoryStore. The server's KnowledgeRuntime constructs a MemoryPipeline once
memory is enabled and an embedder is present; everything downstream (chat
injection, the remember() tool, the background sweeps) talks to this object.

Composition (CONTRACTS §3):
  Capture -> Admit -> Extract -> Reconcile  (the admit->write ingest path)
  Retrieve                                  (the read path)
  Consolidate/Lint                          (the background maintenance loop)

No heuristics live here — this module only wires constructed components and owns
the background loops + per-exchange ingest. Subject identity, recall channels,
and worth gating all live inside the components per their contracts.
"""

import asyncio
from dataclasses import dataclass

from ntrp.embedder import Embedder
from ntrp.llm.base import CompletionClient
from ntrp.logging import get_logger
from ntrp.memory.lens.expand import LensExpander
from ntrp.memory.lens.registry import LensRegistry
from ntrp.memory.models import Scope, SourceRef
from ntrp.memory.pipeline.admit import AdmitGate
from ntrp.memory.pipeline.capture import CaptureConfig, CaptureService
from ntrp.memory.pipeline.consolidate import ConsolidateConfig, ConsolidateLint
from ntrp.memory.pipeline.extract import Extractor
from ntrp.memory.pipeline.membership import LensMembership
from ntrp.memory.pipeline.lens_generation import LensPageGenerator
from ntrp.memory.pipeline.project import LensProjector
from ntrp.memory.pipeline.prompts_capture import SemanticBoundary
from ntrp.memory.pipeline.reconcile import Reconciler
from ntrp.memory.pipeline.retrieve import Retriever
from ntrp.memory.pipeline.types import (
    BoundaryKind,
    CaptureUnit,
    ReconcileResult,
    Retrieval,
    RetrievedContext,
    Verdict,
)
from ntrp.memory.pipeline.write import WriteSeam
from ntrp.memory.pipeline.writeback import LensWriteBack
from ntrp.memory.store import MemoryStore

_logger = get_logger(__name__)


class _BoundaryJudge:
    """Thin adapter from a CompletionClient to capture's BoundaryJudge Protocol.

    Capture only needs a structured SemanticBoundary; the concrete completion
    call is the LLM client's contract. Binding it here keeps capture.py free of
    the client API and lets its unit tests run with a trivial fake.
    """

    def __init__(self, cheap_llm: CompletionClient):
        self._llm = cheap_llm

    async def detect_boundary(
        self, *, system: str, user: str, model: str | None
    ) -> SemanticBoundary:
        if model is None:
            raise ValueError("semantic boundary check requires a model")
        response = await self._llm.completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model,
            response_format=SemanticBoundary,
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            return SemanticBoundary(shift=False, cut_after_index=None, reason="empty response")
        return SemanticBoundary.model_validate_json(content)


@dataclass
class MemoryPipelineConfig:
    cheap_model: str  # memory_model — the cheap gate/extract/reconcile model
    strong_model: str  # chat_model — the escalation/lint judge
    consolidation_interval: int  # minutes between background lint sweeps
    idle_seconds: int = 30 * 60
    sweep_interval_seconds: int = 600  # periodic capture sweep cadence (spec §4.1 primary)
    sweep_session_limit: int = 50  # most-recent sessions scanned per sweep tick
    # Reasoning effort for memory's structured calls. Memory is the CHEAP path
    # (admit/extract/reconcile are classification/extraction, not deep reasoning), so
    # without an explicit low effort a reasoning model (e.g. gpt-5.5) runs at its slow
    # API-default and the call times out. Resolved by the server from config.
    cheap_reasoning_effort: str | None = None
    strong_reasoning_effort: str | None = None


class _EffortClient:
    """Wraps a CompletionClient to inject a default reasoning_effort on memory's
    structured calls. Memory's admit/extract/reconcile are cheap classification tasks;
    without a low effort a reasoning model runs at its slow API-default and the 60s
    call times out (chat passes an effort, memory historically did not). Transparent
    delegate — only completion() is touched, and only when an effort is configured."""

    def __init__(self, inner: CompletionClient, effort: str | None):
        self._inner = inner
        self._effort = effort

    async def completion(self, **kwargs):
        if self._effort is not None:
            kwargs.setdefault("reasoning_effort", self._effort)
        return await self._inner.completion(**kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class MemoryPipeline:
    def __init__(
        self,
        *,
        store: MemoryStore,
        embed: Embedder,
        cheap_llm: CompletionClient,
        strong_llm: CompletionClient,
        raw_sessions,
        raw_automations,
        config: MemoryPipelineConfig,
        eligible_scopes,
    ):
        self.store = store
        self.config = config
        # All memory + lens LLM calls go through the effort-injecting wrapper.
        cheap_llm = _EffortClient(cheap_llm, config.cheap_reasoning_effort)
        strong_llm = _EffortClient(strong_llm, config.strong_reasoning_effort)

        self.capture = CaptureService(
            raw_sessions=raw_sessions,
            raw_automations=raw_automations,
            store=store,
            cheap_llm=_BoundaryJudge(cheap_llm),
            config=CaptureConfig(
                idle_seconds=config.idle_seconds, semantic_model=config.cheap_model
            ),
        )
        self.admit = AdmitGate(store, cheap_llm, embed, model=config.cheap_model)
        self.extract = Extractor(cheap_llm)
        self.reconcile = Reconciler(
            store,
            cheap_llm,
            strong_llm,
            embed,
            cheap_model=config.cheap_model,
            strong_model=config.strong_model,
        )
        # Lenses are VIEWS (a separate registry + computed-projection cache), not
        # memory rows. The expander gives retrieve its read-only lens egress;
        # membership runs Mode-1 cache-warming in ingest_unit.
        self.lens_expander = LensExpander(store, embed)
        self.retriever = Retriever(
            store,
            embed,
            cheap_llm,
            model=config.cheap_model,
            lens_expander=self.lens_expander,
        )
        self.write_seam = WriteSeam(
            store, self.reconcile, self.admit, self.extract, model=config.cheap_model
        )
        self.lens_membership = LensMembership(
            store,
            cheap_llm,
            strong_llm,
            embed,
            cheap_model=config.cheap_model,
            strong_model=config.strong_model,
        )
        self.lens_projector = LensProjector(
            store,
            embed,
            cheap_llm,
            strong_llm,
            cheap_model=config.cheap_model,
            strong_model=config.strong_model,
        )
        self.lens_generator = LensPageGenerator(self.lens_projector)
        self.lens_writeback = LensWriteBack(store)
        self.lens_registry = LensRegistry(
            store, self.lens_membership, projector=self.lens_projector
        )
        self.consolidate = ConsolidateLint(
            store,
            cheap_llm,
            strong_llm,
            model=config.strong_model,
            config=ConsolidateConfig(consolidation_interval=config.consolidation_interval),
            eligible_scopes=eligible_scopes,
        )

        self._tasks: set[asyncio.Task] = set()

    # --- ingest: capture -> admit -> extract -> reconcile ---------------

    async def ingest_unit(self, unit: CaptureUnit) -> list[ReconcileResult]:
        """Run one CaptureUnit through admit -> extract -> reconcile.

        On a durable result (anything past REJECT) the capture watermark is
        advanced so the unit is not re-swept. A REJECT or empty extract still
        advances: the unit was processed; re-reading it would only re-reject.
        """
        admitted = await self.admit.admit(unit)
        if admitted.verdict is Verdict.REJECT:
            await self.capture.commit_watermark(unit.watermark)
            return []

        extracted = await self.extract.extract(admitted, model=self.config.cheap_model)
        if not extracted.candidates:
            await self.capture.commit_watermark(unit.watermark)
            return []

        results = await self.reconcile.reconcile(
            extracted.candidates, unit.scope, prior_candidates=admitted.candidates
        )

        # Mode 1: cache-warm the membership projection for freshly written claims
        # against the scope's active lenses. O(new x K), bounded by the candidate
        # recall fan-out — never O(corpus). Best-effort: correctness does not depend
        # on it (the projector recomputes on a cache miss).
        written = [r.written_id for r in results if r.written_id]
        if written:
            try:
                await self.lens_membership.score_into_active_lenses(written, unit.scope)
            except Exception:
                _logger.exception("lens membership scoring failed for unit %s", unit.watermark)

        await self.capture.commit_watermark(unit.watermark)
        return results

    async def close_session(self, session_id: str, boundary: BoundaryKind) -> list[ReconcileResult]:
        """Bound a session at an interactive boundary and ingest the unit."""
        unit = await self.capture.close(session_id, boundary)
        if unit is None:
            return []
        return await self.ingest_unit(unit)

    def schedule_ingest_session(self, session_id: str, boundary: BoundaryKind) -> None:
        """Fire-and-forget ingest of a session's new exchanges (the interactive
        chat-boundary trigger, spec §4.1). Tracked in self._tasks so it isn't GC'd,
        runs off the chat response path, and never propagates errors to the caller.
        close() is watermark-idempotent, so re-firing is safe."""
        async def _run() -> None:
            try:
                await self.close_session(session_id, boundary)
            except Exception:
                _logger.exception("memory ingest failed for session %s", session_id)

        task = asyncio.create_task(_run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- read: retrieve -------------------------------------------------

    async def retrieve(self, req: Retrieval) -> RetrievedContext:
        return await self.retriever.retrieve(req)

    # --- background loops -----------------------------------------------

    async def sweep_sessions(self, session_ids: list[str]) -> int:
        """Background safety-net sweep over open/never-closing sessions.

        Each unit Capture emits is ingested and its watermark advanced on
        success, so a crash mid-sweep re-reads from the un-advanced cursor.
        """
        ingested = 0
        for session_id in session_ids:
            try:
                units = await self.capture.sweep(f"session:{session_id}")
            except Exception:
                _logger.exception("capture sweep failed for %s", session_id)
                continue
            for unit in units:
                await self.ingest_unit(unit)
                ingested += 1
        return ingested

    def start_background(self) -> None:
        """Start the background loops: consolidate/lint (watermark-durable,
        demote-only) AND the periodic capture sweep (spec §4.1/Fork B — the PRIMARY
        ingest mechanism for sessions that never get an interactive close: idle chats,
        automations, scheduled runs)."""
        for coro in (self.consolidate.run_loop(), self._sweep_loop()):
            task = asyncio.create_task(coro)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _sweep_loop(self) -> None:
        """Periodically sweep recent sessions into the ingest path. capture.sweep only
        emits units past the watermark and only closes an idle/bounded stream, so this
        is watermark-idempotent and composes with the interactive chat-close trigger."""
        while True:
            try:
                await asyncio.sleep(self.config.sweep_interval_seconds)
                ids = await self._recent_session_ids()
                if ids:
                    await self.sweep_sessions(ids)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("memory sweep loop iteration failed")

    async def _recent_session_ids(self) -> list[str]:
        fn = getattr(self.capture.raw_sessions, "recent_session_ids", None)
        if fn is None:
            return []
        try:
            return await fn(self.config.sweep_session_limit)
        except Exception:
            _logger.exception("recent_session_ids failed")
            return []

    async def stop(self) -> None:
        await self.lens_generator.drain()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()

    # --- remember() helpers (the tool calls the WriteSeam directly) -----

    async def remember(
        self, text: str, scope: Scope, source_ref: SourceRef
    ) -> list[ReconcileResult]:
        """Forced single-exchange EXPLICIT ingest (the remember() write path).

        Goes through capture.on_remember -> ingest_unit so it shares the exact
        admit->extract->reconcile path. The WriteSeam is the tool's entry; this
        helper exists for programmatic/background remembers that already hold a
        CaptureUnit shape.
        """
        unit = await self.capture.on_remember(text, scope, source_ref)
        return await self.ingest_unit(unit)
