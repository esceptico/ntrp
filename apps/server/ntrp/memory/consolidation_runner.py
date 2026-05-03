import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from ntrp.constants import CONSOLIDATION_PASS_TIMEOUT
from ntrp.embedder import Embedder
from ntrp.logging import get_logger
from ntrp.memory.consolidation import PATTERN_POLICY_VERSION, apply_consolidation, get_consolidation_decisions
from ntrp.memory.decay import should_archive_fact, should_archive_observation
from ntrp.memory.dreams import run_dream_pass
from ntrp.memory.fact_merge import fact_merge_pass
from ntrp.memory.learning_context import get_applied_memory_policy_context
from ntrp.memory.observation_merge import observation_merge_pass
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.events import MemoryEventRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.learning import LearningRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.temporal import temporal_consolidation_pass

_logger = get_logger(__name__)


class ConsolidationRunner:
    """Consolidates, merges, dreams, and archives memory. Invoked by the automation scheduler."""

    def __init__(
        self,
        facts: FactRepository,
        observations: ObservationRepository,
        dreams: DreamRepository,
        embedder: Embedder,
        model_fn: Callable[[], str],
        transaction: Callable[..., Any],
        db_lock: asyncio.Lock,
        db_conn: Any,
        learning: LearningRepository,
        events: MemoryEventRepository | None = None,
    ):
        self.facts = facts
        self.observations = observations
        self.dreams = dreams
        self.learning = learning
        self.embedder = embedder
        self._model_fn = model_fn
        self._transaction = transaction
        self._db_lock = db_lock
        self._db_conn = db_conn
        self.events = events

        self.dreams_enabled: bool = False
        self._running: bool = False

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
        return self._running

    async def run_consolidation(self) -> str:
        self._running = True
        try:
            results = []
            count = await self._consolidate_pending()
            if count:
                results.append(f"consolidated {count} facts")
            await self._maybe_run_temporal_pass()
            await self._maybe_run_dream_pass()
            return "; ".join(results) if results else "no pending consolidation"
        finally:
            self._running = False

    async def run_maintenance(self) -> str:
        self._running = True
        try:
            results = []
            merged_observations = await self._maybe_run_observation_merge()
            if merged_observations is not None:
                results.append(f"merged {merged_observations} patterns")
            merged_facts = await self._maybe_run_fact_merge()
            if merged_facts is not None:
                results.append(f"merged {merged_facts} facts")
            archived_facts, archived_observations = await self._maybe_run_archival_pass()
            if archived_facts or archived_observations:
                results.append(f"archived {archived_facts} facts / {archived_observations} patterns")
            return "; ".join(results) if results else "no maintenance work"
        finally:
            self._running = False

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

        policy_context = await get_applied_memory_policy_context(
            self,
            target_prefixes=("memory.observations.", "memory.facts.supersession."),
        )
        decisions = []
        for fact in facts:
            actions = await get_consolidation_decisions(
                fact,
                self.observations,
                self.facts,
                self.model,
                policy_context=policy_context,
            )
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
            create_gate_skips: dict[str, int] = {}
            for fact, precomputed in decisions:
                if not await self.facts.get(fact.id):
                    continue
                for action, embedding in precomputed:
                    result = await apply_consolidation(fact, action, self.facts, self.observations, embedding)
                    if result.reason and result.reason.startswith("create_gate:"):
                        reason = result.reason.removeprefix("create_gate:")
                        create_gate_skips[reason] = create_gate_skips.get(reason, 0) + 1
                    if result.observation_id and result.action in {"created", "updated"} and self.events:
                        await self.events.create(
                            actor="automation",
                            action=f"observation.{result.action}",
                            target_type="observation",
                            target_id=result.observation_id,
                            source_type=fact.source_type.value,
                            source_ref=fact.source_ref,
                            reason=result.reason or "fact consolidation",
                            policy_version=PATTERN_POLICY_VERSION,
                            details={"source_fact_id": fact.id},
                        )
                    if result.action == "created":
                        obs_created += 1
                await self.facts.mark_consolidated(fact.id)
                count += 1
            if create_gate_skips and self.events:
                await self.events.create(
                    actor="automation",
                    action="observations.create_skipped",
                    target_type="observation_batch",
                    reason="pattern create gate",
                    policy_version=PATTERN_POLICY_VERSION,
                    details={"reasons": create_gate_skips, "count": sum(create_gate_skips.values())},
                )

        if count > 0:
            _logger.info("Consolidated %d facts", count)
        return count

    async def _maybe_run_temporal_pass(self) -> None:
        now = datetime.now(UTC)
        if self._last_temporal_pass and (now - self._last_temporal_pass) < timedelta(days=1):
            return
        try:
            created = await asyncio.wait_for(
                temporal_consolidation_pass(
                    self.facts,
                    self.observations,
                    self.model,
                    self.embedder.embed_one,
                    atomic=self._atomic,
                ),
                timeout=CONSOLIDATION_PASS_TIMEOUT,
            )
            if created > 0:
                _logger.info("Temporal pass created %d observations", created)
            self._last_temporal_pass = now
        except TimeoutError:
            _logger.warning("Temporal consolidation pass timed out after %ds", CONSOLIDATION_PASS_TIMEOUT)
        except Exception as e:
            _logger.warning("Temporal consolidation pass failed: %s", e)

    async def _maybe_run_observation_merge(self) -> int | None:
        now = datetime.now(UTC)
        if self._last_merge_pass and (now - self._last_merge_pass) < timedelta(days=1):
            return None
        try:
            merged = await asyncio.wait_for(
                observation_merge_pass(
                    self.observations,
                    self.model,
                    self.embedder.embed_one,
                    atomic=self._atomic,
                ),
                timeout=CONSOLIDATION_PASS_TIMEOUT,
            )
            if merged > 0:
                _logger.info("Observation merge pass: %d merges", merged)
            self._last_merge_pass = now
            return merged
        except TimeoutError:
            _logger.warning("Observation merge pass timed out after %ds", CONSOLIDATION_PASS_TIMEOUT)
        except Exception as e:
            _logger.warning("Observation merge pass failed: %s", e)
        return None

    async def _maybe_run_fact_merge(self) -> int | None:
        now = datetime.now(UTC)
        if self._last_fact_merge_pass and (now - self._last_fact_merge_pass) < timedelta(days=1):
            return None
        try:
            merged = await asyncio.wait_for(
                fact_merge_pass(
                    self.facts,
                    self.observations,
                    self.model,
                    self.embedder.embed_one,
                    atomic=self._atomic,
                    dream_repo=self.dreams,
                ),
                timeout=CONSOLIDATION_PASS_TIMEOUT,
            )
            if merged > 0:
                _logger.info("Fact merge pass: %d merges", merged)
            self._last_fact_merge_pass = now
            return merged
        except TimeoutError:
            _logger.warning("Fact merge pass timed out after %ds", CONSOLIDATION_PASS_TIMEOUT)
        except Exception as e:
            _logger.warning("Fact merge pass failed: %s", e)
        return None

    async def _maybe_run_dream_pass(self) -> None:
        if not self.dreams_enabled:
            return
        now = datetime.now(UTC)
        if self._last_dream_pass and (now - self._last_dream_pass) < timedelta(weeks=1):
            return
        try:
            created = await asyncio.wait_for(
                run_dream_pass(
                    self.facts,
                    self.dreams,
                    self.model,
                    self.embedder.embed_one,
                    atomic=self._atomic,
                ),
                timeout=CONSOLIDATION_PASS_TIMEOUT,
            )
            if created > 0:
                _logger.info("Dream pass created %d dreams", created)
            self._last_dream_pass = now
        except TimeoutError:
            _logger.warning("Dream pass timed out after %ds", CONSOLIDATION_PASS_TIMEOUT)
        except Exception as e:
            _logger.warning("Dream pass failed: %s", e)

    async def _maybe_run_archival_pass(self) -> tuple[int, int]:
        now = datetime.now(UTC)
        if self._last_archival_pass and (now - self._last_archival_pass) < timedelta(days=1):
            return (0, 0)
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
                    if self.events and archived_facts:
                        await self.events.create(
                            actor="automation",
                            action="facts.archived",
                            target_type="fact_batch",
                            reason="decay archival pass",
                            policy_version="memory.decay.v1",
                            details={"ids": archive_ids, "count": archived_facts},
                        )

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
                    if self.events and archived_obs:
                        await self.events.create(
                            actor="automation",
                            action="observations.archived",
                            target_type="observation_batch",
                            reason="decay archival pass",
                            policy_version="memory.decay.v1",
                            details={"ids": obs_archive_ids, "count": archived_obs},
                        )

            if archived_facts or archived_obs:
                _logger.info("Archival pass: %d facts, %d observations archived", archived_facts, archived_obs)
            self._last_archival_pass = now
            return (archived_facts, archived_obs)
        except Exception as e:
            _logger.warning("Archival pass failed: %s", e)
        return (0, 0)
