import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

import aiosqlite
from pydantic import BaseModel, ConfigDict

import ntrp.database as database
from ntrp.channel import Channel
from ntrp.constants import (
    CONSOLIDATION_INTERVAL,
    CONSOLIDATION_MAX_BACKOFF_MULTIPLIER,
    FORGET_SEARCH_LIMIT,
    FORGET_SIMILARITY_THRESHOLD,
    RECALL_SEARCH_LIMIT,
    USER_ENTITY_NAME,
)
from ntrp.core.events import ConsolidationCompleted
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.memory.consolidation import apply_consolidation, get_consolidation_decisions
from ntrp.memory.dreams import run_dream_pass
from ntrp.memory.observation_merge import observation_merge_pass
from ntrp.memory.temporal import temporal_consolidation_pass
from ntrp.memory.events import FactCreated, FactDeleted
from ntrp.memory.extraction import Extractor
from ntrp.memory.models import ExtractionResult, Fact, FactContext
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.store.retrieval import retrieve_with_observations

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
        self.extraction_model = extraction_model
        self.channel = channel
        self._consolidation_task: asyncio.Task | None = None
        self._reembed_task: asyncio.Task | None = None
        self._reembed_progress: dict | None = None
        self._db_lock = asyncio.Lock()
        self._last_temporal_pass: datetime | None = None
        self._last_dream_pass: datetime | None = None
        self._last_merge_pass: datetime | None = None

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

        # LLM decisions outside lock
        decisions = []
        for fact in facts:
            actions = await get_consolidation_decisions(fact, self.observations, self.facts, self.extraction_model)
            decisions.append((fact, actions))

        # Apply under lock
        async with self.transaction():
            count = 0
            obs_created = 0
            for fact, actions in decisions:
                for action in actions:
                    result = await apply_consolidation(
                        fact, action, self.facts, self.observations, self.embedder.embed_one
                    )
                    if result.action == "created":
                        obs_created += 1
                await self.facts.mark_consolidated(fact.id)
                count += 1

        _logger.info("Consolidated %d facts", count)
        self.channel.publish(ConsolidationCompleted(facts_processed=count, observations_created=obs_created))
        return count

    async def _maybe_run_temporal_pass(self) -> None:
        now = datetime.now()
        if self._last_temporal_pass and (now - self._last_temporal_pass) < timedelta(days=1):
            return

        try:
            async with self.transaction():
                created = await temporal_consolidation_pass(
                    self.facts,
                    self.observations,
                    self.extraction_model,
                    self.embedder.embed_one,
                )
            if created > 0:
                _logger.info("Temporal pass created %d observations", created)
            self._last_temporal_pass = now
        except Exception as e:
            _logger.warning("Temporal consolidation pass failed: %s", e)

    async def _maybe_run_observation_merge(self) -> None:
        now = datetime.now()
        if self._last_merge_pass and (now - self._last_merge_pass) < timedelta(days=1):
            return

        try:
            async with self.transaction():
                merged = await observation_merge_pass(
                    self.observations,
                    self.extraction_model,
                    self.embedder.embed_one,
                )
            if merged > 0:
                _logger.info("Observation merge pass: %d merges", merged)
            self._last_merge_pass = now
        except Exception as e:
            _logger.warning("Observation merge pass failed: %s", e)

    async def _maybe_run_dream_pass(self) -> None:
        now = datetime.now()
        if self._last_dream_pass and (now - self._last_dream_pass) < timedelta(days=1):
            return

        try:
            async with self.transaction():
                created = await run_dream_pass(
                    self.facts,
                    self.dreams,
                    self.extraction_model,
                )
            if created > 0:
                _logger.info("Dream pass created %d dreams", created)
            self._last_dream_pass = now
        except Exception as e:
            _logger.warning("Dream pass failed: %s", e)

    @property
    def reembed_running(self) -> bool:
        return self._reembed_task is not None and not self._reembed_task.done()

    def start_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False) -> None:
        if self._reembed_task and not self._reembed_task.done():
            self._reembed_task.cancel()
        self._reembed_task = asyncio.create_task(self._run_reembed(embedding, rebuild=rebuild))

    async def _run_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False) -> None:
        try:
            new_embedder = Embedder(embedding)
            if rebuild:
                await self.db.rebuild_vec_tables(embedding.dim)

            facts = await self.facts.list_all_with_embeddings()
            observations = await self.observations.list_all_with_embeddings()
            total = len(facts) + len(observations)
            self._reembed_progress = {"total": total, "done": 0}

            done = 0
            for fact in facts:
                new_emb = await new_embedder.embed_one(fact.text)
                await self.facts.update_embedding(fact.id, new_emb)
                done += 1
                self._reembed_progress["done"] = done

            for obs in observations:
                new_emb = await new_embedder.embed_one(obs.summary)
                await self.observations.update_embedding(obs.id, new_emb)
                done += 1
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

        async with self.transaction():
            fact = await self.facts.create(
                text=text,
                source_type=source_type,
                source_ref=source_ref,
                embedding=embedding,
                happened_at=happened_at,
            )

            extraction = await self.extractor.extract(text)
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
                for obs in context.observations:
                    fact_ids = await self.observations.get_fact_ids(obs.id)
                    if fact_ids:
                        await self.facts.reinforce(fact_ids)

        return context

    async def forget(self, query: str) -> int:
        query_embedding = await self.embedder.embed_one(query)
        results = await self.facts.search_facts_vector(query_embedding, limit=FORGET_SEARCH_LIMIT)

        async with self.transaction():
            count = 0
            for fact, score in results:
                if score >= FORGET_SIMILARITY_THRESHOLD:
                    await self.facts.delete(fact.id)
                    count += 1
                    self.channel.publish(FactDeleted(fact_id=fact.id))
            if count > 0:
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
            _logger.info("Merged entities %s → '%s' (%d merged)", [e.name for e in entities], keep.name, count)
            return count

    async def count(self) -> int:
        return await self.facts.count()

    async def get_context(self, user_limit: int = 10) -> list[Fact]:
        return await self.facts.get_facts_for_entity(USER_ENTITY_NAME, limit=user_limit)

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
