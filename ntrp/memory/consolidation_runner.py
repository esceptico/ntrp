import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from ntrp.constants import CONSOLIDATION_INTERVAL, CONSOLIDATION_MAX_BACKOFF_MULTIPLIER
from ntrp.embedder import Embedder
from ntrp.events.internal import ConsolidationCompleted
from ntrp.logging import get_logger
from ntrp.memory.consolidation import apply_consolidation, get_consolidation_decisions
from ntrp.memory.decay import should_archive_fact, should_archive_observation
from ntrp.memory.dreams import run_dream_pass
from ntrp.memory.fact_merge import fact_merge_pass
from ntrp.memory.observation_merge import observation_merge_pass
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.temporal import temporal_consolidation_pass

_logger = get_logger(__name__)


class ConsolidationRunner:
    """Background loop that consolidates, merges, dreams, and archives memory."""

    def __init__(
        self,
        facts: FactRepository,
        observations: ObservationRepository,
        dreams: DreamRepository,
        embedder: Embedder,
        model_fn: Callable[[], str],
        publish: Callable[[Any], None],
        transaction: Callable[..., Any],
        db_lock: asyncio.Lock,
        db_conn: Any,
    ):
        self.facts = facts
        self.observations = observations
        self.dreams = dreams
        self.embedder = embedder
        self._model_fn = model_fn
        self._publish = publish
        self._transaction = transaction
        self._db_lock = db_lock
        self._db_conn = db_conn

        self._task: asyncio.Task | None = None
        self.interval: float | None = None
        self.dreams_enabled: bool = False

        self._last_temporal_pass: datetime | None = None
        self._last_dream_pass: datetime | None = None
        self._last_merge_pass: datetime | None = None
        self._last_fact_merge_pass: datetime | None = None
        self._last_archival_pass: datetime | None = None

    @property
    def model(self) -> str:
        return self._model_fn()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, interval: float = CONSOLIDATION_INTERVAL) -> None:
        if self._task is None:
            self.interval = interval
            self._task = asyncio.create_task(self._loop(interval))

    def restart(self, interval: float) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self.start(interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, interval: float) -> None:
        backoff = interval
        max_backoff = interval * CONSOLIDATION_MAX_BACKOFF_MULTIPLIER
        while True:
            await asyncio.sleep(backoff)
            try:
                await self._consolidate_pending()
                await self._maybe_run_temporal_pass()
                await self._maybe_run_observation_merge()
                await self._maybe_run_fact_merge()
                await self._maybe_run_dream_pass()
                await self._maybe_run_archival_pass()
                backoff = interval
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _logger.warning("Consolidation batch failed: %s", e)
                backoff = min(backoff * 2, max_backoff)

    @asynccontextmanager
    async def _atomic(self) -> AsyncGenerator[None]:
        async with self._db_lock:
            try:
                yield
                await self._db_conn.commit()
            except Exception:
                await self._db_conn.rollback()
                raise

    async def _consolidate_pending(self, batch_size: int = 10) -> int:
        async with self._db_lock:
            facts = await self.facts.list_unconsolidated(limit=batch_size)
            if not facts:
                return 0
            facts = [
                fact.model_copy(update={"entity_refs": await self.facts.get_entity_refs(fact.id)}) for fact in facts
            ]

        decisions = []
        for fact in facts:
            actions = await get_consolidation_decisions(fact, self.observations, self.facts, self.model)
            precomputed = []
            for action in actions:
                embedding = None
                if action.action in ("update", "create") and action.text:
                    embedding = await self.embedder.embed_one(action.text)
                precomputed.append((action, embedding))
            decisions.append((fact, precomputed))

        async with self._transaction():
            count = 0
            obs_created = 0
            for fact, precomputed in decisions:
                if not await self.facts.get(fact.id):
                    continue
                for action, embedding in precomputed:
                    result = await apply_consolidation(fact, action, self.facts, self.observations, embedding)
                    if result.action == "created":
                        obs_created += 1
                await self.facts.mark_consolidated(fact.id)
                count += 1

        _logger.info("Consolidated %d facts", count)
        self._publish(ConsolidationCompleted(facts_processed=count, observations_created=obs_created))
        return count

    async def _maybe_run_temporal_pass(self) -> None:
        now = datetime.now(UTC)
        if self._last_temporal_pass and (now - self._last_temporal_pass) < timedelta(days=1):
            return
        try:
            created = await temporal_consolidation_pass(
                self.facts,
                self.observations,
                self.model,
                self.embedder.embed_one,
                atomic=self._atomic,
            )
            if created > 0:
                _logger.info("Temporal pass created %d observations", created)
            self._last_temporal_pass = now
        except Exception as e:
            _logger.warning("Temporal consolidation pass failed: %s", e)

    async def _maybe_run_observation_merge(self) -> None:
        now = datetime.now(UTC)
        if self._last_merge_pass and (now - self._last_merge_pass) < timedelta(days=1):
            return
        try:
            merged = await observation_merge_pass(
                self.observations,
                self.model,
                self.embedder.embed_one,
                atomic=self._atomic,
            )
            if merged > 0:
                _logger.info("Observation merge pass: %d merges", merged)
            self._last_merge_pass = now
        except Exception as e:
            _logger.warning("Observation merge pass failed: %s", e)

    async def _maybe_run_fact_merge(self) -> None:
        now = datetime.now(UTC)
        if self._last_fact_merge_pass and (now - self._last_fact_merge_pass) < timedelta(days=1):
            return
        try:
            merged = await fact_merge_pass(
                self.facts,
                self.observations,
                self.model,
                self.embedder.embed_one,
                atomic=self._atomic,
                dream_repo=self.dreams,
            )
            if merged > 0:
                _logger.info("Fact merge pass: %d merges", merged)
            self._last_fact_merge_pass = now
        except Exception as e:
            _logger.warning("Fact merge pass failed: %s", e)

    async def _maybe_run_dream_pass(self) -> None:
        if not self.dreams_enabled:
            return
        now = datetime.now(UTC)
        if self._last_dream_pass and (now - self._last_dream_pass) < timedelta(weeks=1):
            return
        try:
            created = await run_dream_pass(
                self.facts,
                self.dreams,
                self.model,
                self.embedder.embed_one,
                atomic=self._atomic,
            )
            if created > 0:
                _logger.info("Dream pass created %d dreams", created)
            self._last_dream_pass = now
        except Exception as e:
            _logger.warning("Dream pass failed: %s", e)

    async def _maybe_run_archival_pass(self) -> None:
        now = datetime.now(UTC)
        if self._last_archival_pass and (now - self._last_archival_pass) < timedelta(days=1):
            return
        try:
            archived_facts = 0
            candidates = await self.facts.list_archival_candidates(limit=100)
            archive_ids = [
                f.id
                for f in candidates
                if should_archive_fact(f.consolidated_at, f.created_at, f.last_accessed_at, f.access_count, now)
            ]
            if archive_ids:
                async with self._transaction():
                    archived_facts = await self.facts.archive_batch(archive_ids)

            archived_obs = 0
            obs_candidates = await self.observations.list_archival_candidates(limit=100)
            obs_archive_ids = [
                o.id
                for o in obs_candidates
                if should_archive_observation(o.created_at, o.updated_at, o.last_accessed_at, o.access_count, now)
            ]
            if obs_archive_ids:
                async with self._transaction():
                    archived_obs = await self.observations.archive_batch(obs_archive_ids)

            if archived_facts or archived_obs:
                _logger.info("Archival pass: %d facts, %d observations archived", archived_facts, archived_obs)
            self._last_archival_pass = now
        except Exception as e:
            _logger.warning("Archival pass failed: %s", e)
