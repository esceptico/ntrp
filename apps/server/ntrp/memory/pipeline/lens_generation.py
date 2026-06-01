"""Async lens-page generation — keep the GET off the synthesis critical path.

Generating a lens page is many sequential LLM calls (membership refresh +
re-validate + one strong-model synthesis per subject bucket). Running that on the
HTTP request blocks for seconds and times the request out. The spec (Lens §6)
allows lazy on-demand materialization but never says the GET must block — the
intent is that complex synthesis is deferred and the GET returns immediately.

This module owns that deferral. The page GET asks the generator to `ensure`
generation: a cache-hit returns the page immediately; a miss/dirty/refresh starts
ONE background task (deduplicated per lens) and returns a `generating` status the
UI can render and poll. The background task drives `LensProjector.project`, which
caches the page back into the lens row; while it runs it reports progress (stage +
subject) into a per-lens `LensGenStatus` the UI reads via the status endpoint.

No LLM, no embedding, no keyword logic lives here — it is pure orchestration over
the projector. The projector remains the sole synthesis path.
"""

import asyncio
from dataclasses import dataclass, field

from ntrp.logging import get_logger
from ntrp.memory.models import LensDetailLevel, now_iso
from ntrp.memory.pipeline.project import LensProjector
from ntrp.memory.pipeline.types import LensGenStage, ProjectedPage

_logger = get_logger(__name__)


@dataclass
class LensGenStatus:
    lens_id: str
    stage: LensGenStage
    detail: str  # the requested detail level value
    subject: str | None = None  # current subject bucket while synthesizing
    progress: str | None = None  # "2/5" while synthesizing grouped buckets
    error: str | None = None
    updated_at: str = field(default_factory=now_iso)

    def to_json(self) -> dict:
        return {
            "lens_id": self.lens_id,
            "status": "ready" if self.stage is LensGenStage.READY else self.stage.value,
            "stage": self.stage.value,
            "detail": self.detail,
            "subject": self.subject,
            "progress": self.progress,
            "error": self.error,
            "updated_at": self.updated_at,
        }


class LensPageGenerator:
    """Background-generates lens pages and tracks their live status.

    `ensure` is the single entry point for the GET endpoint: it returns either a
    finished page (cache hit) or a `generating` status while a background task runs.
    """

    def __init__(self, projector: LensProjector):
        self.projector = projector
        self._status: dict[str, LensGenStatus] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def status(self, lens_id: str) -> LensGenStatus | None:
        return self._status.get(lens_id)

    async def ensure(
        self, lens_id: str, *, detail: LensDetailLevel | None, refresh: bool
    ) -> ProjectedPage | LensGenStatus:
        """Cache-hit -> the page (fast path, no synthesis). Miss/dirty/refresh ->
        start one background generation and return a `generating` status."""
        cached = await self.projector.cached_page(lens_id, detail=detail)
        if cached is not None and not refresh:
            # A clean cache hit short-circuits any in-flight status — it is current.
            self._status.pop(lens_id, None)
            return cached

        status = self._status.get(lens_id)
        running = self._tasks.get(lens_id)
        if running is not None and not running.done():
            return status or self._set(lens_id, LensGenStage.CREATING, detail)

        status = self._set(lens_id, LensGenStage.CREATING, detail)
        task = asyncio.create_task(self._generate(lens_id, detail=detail, refresh=refresh))
        self._tasks[lens_id] = task
        task.add_done_callback(lambda t, lid=lens_id: self._tasks.pop(lid, None))
        return status

    async def _generate(
        self, lens_id: str, *, detail: LensDetailLevel | None, refresh: bool
    ) -> None:
        def report(
            stage: LensGenStage, *, subject: str | None = None, progress: str | None = None
        ) -> None:
            self._set(lens_id, stage, detail, subject=subject, progress=progress)

        try:
            await self.projector.project(
                lens_id, detail=detail, refresh=refresh, progress=report
            )
            self._set(lens_id, LensGenStage.READY, detail)
        except Exception as e:  # generation failed; surface it, don't crash the loop
            _logger.warning("lens generation failed for %s: %s", lens_id, e)
            self._set(lens_id, LensGenStage.ERROR, detail, error=str(e))

    def _set(
        self,
        lens_id: str,
        stage: LensGenStage,
        detail: LensDetailLevel | None,
        *,
        subject: str | None = None,
        progress: str | None = None,
        error: str | None = None,
    ) -> LensGenStatus:
        status = LensGenStatus(
            lens_id=lens_id,
            stage=stage,
            detail=(detail or LensDetailLevel.STRUCTURED).value,
            subject=subject,
            progress=progress,
            error=error,
        )
        self._status[lens_id] = status
        return status

    async def drain(self) -> None:
        """Await all in-flight generation tasks — for shutdown and tests."""
        tasks = [t for t in self._tasks.values() if not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
