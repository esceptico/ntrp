import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Self

import aiosqlite
from pydantic import BaseModel, ConfigDict

import ntrp.database as database
from ntrp.channel import Channel
from ntrp.constants import (
    CONSOLIDATION_INTERVAL,
    CONSOLIDATION_MAX_BACKOFF_MULTIPLIER,
    FACT_DEDUP_EMBEDDING_SIMILARITY,
    FACT_DEDUP_TEXT_RATIO,
    FORGET_SEARCH_LIMIT,
    FORGET_SIMILARITY_THRESHOLD,
    RECALL_SEARCH_LIMIT,
    SYSTEM_PROMPT_OBSERVATION_LIMIT,
    USER_ENTITY_NAME,
)
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.events.internal import ConsolidationCompleted, FactCreated, FactDeleted
from ntrp.logging import get_logger
from ntrp.memory.consolidation import apply_consolidation, get_consolidation_decisions
from ntrp.memory.decay import decay_score
from ntrp.memory.dreams import run_dream_pass
from ntrp.memory.extraction import Extractor
from ntrp.memory.fact_merge import fact_merge_pass
from ntrp.memory.models import ExtractionResult, Fact, FactContext, Observation
from ntrp.memory.observation_merge import observation_merge_pass
from ntrp.memory.retrieval import retrieve_with_observations
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.temporal import temporal_consolidation_pass

_logger = get_logger(__name__)


class RememberFactResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    fact: Fact
    entities_extracted: list[str]


class FactMemory:
    def __init__(
        self,
        conn: aiosqlite.Connection,
        embedding: EmbeddingConfig,
        extraction_model: str,
        channel: Channel,
        embedder: Embedder | None = None,
        extractor: Extractor | None = None,
    ):
        self.db = GraphDatabase(conn, embedding.dim)
        self.facts = FactRepository(conn)
        self.observations = ObservationRepository(conn)
        self.dreams = DreamRepository(conn)
        self.embedder = embedder or Embedder(embedding)
        self.extractor = extractor or Extractor(extraction_model)
        self.channel = channel
        self._consolidation_task: asyncio.Task | None = None
        self._reembed_task: asyncio.Task | None = None
        self._reembed_progress: dict | None = None
        self._db_lock = asyncio.Lock()
        self._last_temporal_pass: datetime | None = None
        self._last_dream_pass: datetime | None = None
        self._last_merge_pass: datetime | None = None
        self._last_fact_merge_pass: datetime | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        async with self._db_lock:
            try:
                yield
                await self.db.conn.commit()
            except Exception:
                await self.db.conn.rollback()
                raise

    @property
    def is_consolidating(self) -> bool:
        return self._consolidation_task is not None and not self._consolidation_task.done()

    @classmethod
    async def create(
        cls,
        db_path: Path,
        embedding: EmbeddingConfig,
        extraction_model: str,
        channel: Channel,
    ) -> Self:
        conn = await database.connect(db_path, vec=True)
        instance = cls(conn, embedding, extraction_model, channel=channel)
        await instance.db.init_schema()
        if instance.db.dim_changed:
            _logger.info("Embedding dimension changed — starting background re-embed")
            instance.start_reembed(embedding)
        return instance

    def start_consolidation(self, interval: float = CONSOLIDATION_INTERVAL) -> None:
        if self._consolidation_task is None:
            self._consolidation_task = asyncio.create_task(self._consolidation_loop(interval))

    async def _consolidation_loop(self, interval: float) -> None:
        backoff = interval
        max_backoff = interval * CONSOLIDATION_MAX_BACKOFF_MULTIPLIER
        while True:
            await asyncio.sleep(backoff)
            try:
                count = await self._consolidate_pending()
                if count > 0:
                    backoff = interval
                await self._maybe_run_temporal_pass()
                await self._maybe_run_observation_merge()
                await self._maybe_run_fact_merge()
                await self._maybe_run_dream_pass()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _logger.warning("Consolidation batch failed: %s", e)
                backoff = min(backoff * 2, max_backoff)

    async def _consolidate_pending(self, batch_size: int = 10) -> int:
        async with self._db_lock:
            facts = await self.facts.list_unconsolidated(limit=batch_size)
            if not facts:
                return 0
            facts = [
                fact.model_copy(update={"entity_refs": await self.facts.get_entity_refs(fact.id)}) for fact in facts
            ]

        # LLM decisions + embeddings outside lock
        decisions = []
        for fact in facts:
            actions = await get_consolidation_decisions(fact, self.observations, self.facts, self.extraction_model)
            # Pre-compute embeddings for actions that need them
            precomputed = []
            for action in actions:
                embedding = None
                if action.action in ("update", "create") and action.text:
                    embedding = await self.embedder.embed_one(action.text)
                precomputed.append((action, embedding))
            decisions.append((fact, precomputed))

        # Apply under lock — DB writes only, no network I/O
        async with self.transaction():
            count = 0
            obs_created = 0
            for fact, precomputed in decisions:
                # Verify fact still exists (could be deleted by concurrent forget())
                if not await self.facts.get(fact.id):
                    continue
                for action, embedding in precomputed:
                    result = await apply_consolidation(fact, action, self.facts, self.observations, embedding)
                    if result.action == "created":
                        obs_created += 1
                await self.facts.mark_consolidated(fact.id)
                count += 1

        _logger.info("Consolidated %d facts", count)
        self.channel.publish(ConsolidationCompleted(facts_processed=count, observations_created=obs_created))
        return count

    @asynccontextmanager
    async def _atomic(self) -> AsyncGenerator[None]:
        """Lock + commit for background passes. Wraps a logical write unit."""
        async with self._db_lock:
            try:
                yield
                await self.db.conn.commit()
            except Exception:
                await self.db.conn.rollback()
                raise

    async def _maybe_run_temporal_pass(self) -> None:
        now = datetime.now(UTC)
        if self._last_temporal_pass and (now - self._last_temporal_pass) < timedelta(days=1):
            return

        try:
            created = await temporal_consolidation_pass(
                self.facts,
                self.observations,
                self.extraction_model,
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
                self.extraction_model,
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
                self.extraction_model,
                self.embedder.embed_one,
                atomic=self._atomic,
            )
            if merged > 0:
                _logger.info("Fact merge pass: %d merges", merged)
            self._last_fact_merge_pass = now
        except Exception as e:
            _logger.warning("Fact merge pass failed: %s", e)

    async def _maybe_run_dream_pass(self) -> None:
        now = datetime.now(UTC)
        if self._last_dream_pass and (now - self._last_dream_pass) < timedelta(days=1):
            return

        try:
            created = await run_dream_pass(
                self.facts,
                self.dreams,
                self.extraction_model,
                self.embedder.embed_one,
                atomic=self._atomic,
            )
            if created > 0:
                _logger.info("Dream pass created %d dreams", created)
            self._last_dream_pass = now
        except Exception as e:
            _logger.warning("Dream pass failed: %s", e)

    @property
    def reembed_running(self) -> bool:
        return self._reembed_task is not None and not self._reembed_task.done()

    @property
    def reembed_progress(self) -> dict | None:
        return self._reembed_progress

    @property
    def extraction_model(self) -> str:
        return self.extractor.model

    def update_extraction_model(self, model: str) -> None:
        self.extractor.model = model

    def start_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False) -> None:
        if self._reembed_task and not self._reembed_task.done():
            self._reembed_task.cancel()
        self._reembed_task = asyncio.create_task(self._run_reembed(embedding, rebuild=rebuild))

    async def _run_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False, batch_size: int = 100) -> None:
        try:
            new_embedder = Embedder(embedding)
            if rebuild:
                await self.db.rebuild_vec_tables(embedding.dim)

            facts = await self.facts.list_all_with_embeddings()
            observations = await self.observations.list_all_with_embeddings()
            total = len(facts) + len(observations)
            self._reembed_progress = {"total": total, "done": 0}

            done = 0
            for i in range(0, len(facts), batch_size):
                batch = facts[i : i + batch_size]
                embeddings = await new_embedder.embed([f.text for f in batch])
                for fact, emb in zip(batch, embeddings):
                    await self.facts.update_embedding(fact.id, emb)
                done += len(batch)
                self._reembed_progress["done"] = done

            for i in range(0, len(observations), batch_size):
                batch = observations[i : i + batch_size]
                embeddings = await new_embedder.embed([o.summary for o in batch])
                for obs, emb in zip(batch, embeddings):
                    await self.observations.update_embedding(obs.id, emb)
                done += len(batch)
                self._reembed_progress["done"] = done

            await self.db.conn.commit()
            self.embedder = new_embedder
            _logger.info("Re-embedded %d memory vectors", total)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("Memory re-embed failed", exc_info=True)
        finally:
            self._reembed_progress = None

    async def close(self) -> None:
        for task in (self._consolidation_task, self._reembed_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._consolidation_task = None
        self._reembed_task = None
        await self.db.conn.close()

    async def remember(
        self,
        text: str,
        source_type: str = "explicit",
        source_ref: str | None = None,
        happened_at: datetime | None = None,
    ) -> RememberFactResult | None:
        if not text or not text.strip():
            return None
        embedding = await self.embedder.embed_one(text)

        # Extract entities outside lock (LLM call)
        extraction = await self.extractor.extract(text)

        async with self.transaction():
            # Dedup inside lock to prevent TOCTOU race
            similar = await self.facts.search_facts_vector(embedding, limit=1)
            if similar:
                existing_fact, similarity = similar[0]
                text_ratio = SequenceMatcher(None, text.lower(), existing_fact.text.lower()).ratio()
                is_dup = text_ratio >= FACT_DEDUP_TEXT_RATIO or similarity >= FACT_DEDUP_EMBEDDING_SIMILARITY
                _logger.info(
                    "Dedup check: fact %d text_ratio=%.3f sim=%.3f dup=%s — %r",
                    existing_fact.id,
                    text_ratio,
                    similarity,
                    is_dup,
                    existing_fact.text[:80],
                )
                if is_dup:
                    await self.facts.reinforce([existing_fact.id])
                    return None

            fact = await self.facts.create(
                text=text,
                source_type=source_type,
                source_ref=source_ref,
                embedding=embedding,
                happened_at=happened_at,
            )
            entities_extracted = await self._process_extraction(fact.id, extraction)

        self.channel.publish(FactCreated(fact_id=fact.id, text=text))

        return RememberFactResult(fact=fact, entities_extracted=entities_extracted)

    async def _process_extraction(
        self,
        fact_id: int,
        extraction: ExtractionResult,
    ) -> list[str]:
        seen: set[str] = set()

        for entity in extraction.entities:
            name = entity.name.strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())

            entity_id = await self._resolve_entity(name)
            await self.facts.add_entity_ref(fact_id, name, entity_id)

        return list(seen)

    async def _resolve_entity(self, name: str) -> int | None:
        # Exact match (COLLATE NOCASE handles case-insensitivity)
        existing = await self.facts.get_entity_by_name(name)
        if existing:
            return existing.id

        # Create new entity — no fuzzy matching.
        # SequenceMatcher can't distinguish similar-but-different entities
        # ("Avatar 2" vs "Avatar", "Australia" vs "Austria").
        entity = await self.facts.create_entity(name=name)
        return entity.id

    async def recall(
        self,
        query: str,
        limit: int = RECALL_SEARCH_LIMIT,
        query_time: datetime | None = None,
    ) -> FactContext:
        query_embedding = await self.embedder.embed_one(query)

        context = await retrieve_with_observations(
            self.facts,
            self.observations,
            query,
            query_embedding,
            seed_limit=limit,
            query_time=query_time,
        )

        async with self.transaction():
            if context.facts:
                await self.facts.reinforce([f.id for f in context.facts])

            if context.observations:
                await self.observations.reinforce([o.id for o in context.observations])
                # Reinforce only the displayed source facts (bundled_sources), not all
                displayed_fact_ids = [f.id for facts in context.bundled_sources.values() for f in facts]
                if displayed_fact_ids:
                    await self.facts.reinforce(displayed_fact_ids)

        return context

    async def forget(self, query: str) -> int:
        query_embedding = await self.embedder.embed_one(query)
        results = await self.facts.search_facts_vector(query_embedding, limit=FORGET_SEARCH_LIMIT)

        async with self.transaction():
            count = 0
            deleted_ids = []
            for fact, score in results:
                if score >= FORGET_SIMILARITY_THRESHOLD:
                    await self.facts.delete(fact.id)
                    deleted_ids.append(fact.id)
                    count += 1
                    self.channel.publish(FactDeleted(fact_id=fact.id))
            if count > 0:
                await self.observations.remove_source_facts(deleted_ids)
                await self.facts.cleanup_orphaned_entities()
            return count

    async def merge_entities(self, names: list[str], canonical_name: str | None = None) -> int:
        if len(names) < 2:
            return 0

        async with self.transaction():
            entities = []
            for name in names:
                entity = await self.facts.get_entity_by_name(name)
                if entity:
                    entities.append(entity)

            if len(entities) < 2:
                return 0

            if canonical_name:
                keep = next((e for e in entities if e.name.lower() == canonical_name.lower()), entities[0])
            else:
                keep = entities[0]

            merge_ids = [e.id for e in entities if e.id != keep.id]
            count = await self.facts.merge_entities(keep.id, merge_ids)
            await self.observations.merge_entity_refs(keep.id, merge_ids)
            _logger.info("Merged entities %s → '%s' (%d merged)", [e.name for e in entities], keep.name, count)
            return count

    async def count(self) -> int:
        return await self.facts.count()

    async def get_context(self, user_limit: int = 10) -> tuple[list[Observation], list[Fact]]:
        # Get User-linked observations, scored by decay
        user_entity = await self.facts.get_entity_by_name(USER_ENTITY_NAME)
        if user_entity:
            raw_obs = await self.observations.get_for_entity(user_entity.id, limit=20)
            scored_obs = sorted(
                raw_obs,
                key=lambda o: decay_score(o.last_accessed_at, o.access_count),
                reverse=True,
            )
            observations = scored_obs[:SYSTEM_PROMPT_OBSERVATION_LIMIT]
        else:
            observations = []

        # Exclusion set: all source fact IDs from selected observations
        exclude_ids: set[int] = set()
        for obs in observations:
            exclude_ids.update(obs.source_fact_ids)

        # User facts, minus those already covered by observations
        all_user_facts = await self.facts.get_facts_for_entity(USER_ENTITY_NAME, limit=user_limit + len(exclude_ids))
        user_facts = [f for f in all_user_facts if f.id not in exclude_ids][:user_limit]

        return observations, user_facts

    async def clear_observations(self) -> dict[str, int]:
        async with self.transaction():
            obs_count = await self.observations.clear_all()
            facts_reset = await self.facts.reset_consolidated()
            return {"observations_deleted": obs_count, "facts_reset": facts_reset}

    async def clear(self) -> dict[str, int]:
        async with self.transaction():
            counts = {
                "facts": await self.facts.count(),
                "observations": await self.observations.count(),
            }
            await self.db.clear_all()
            return counts
