import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import aiosqlite
from pydantic import BaseModel, ConfigDict

import ntrp.database as database
from ntrp.channel import Channel
from ntrp.constants import (
    CONSOLIDATION_INTERVAL,
    CONSOLIDATION_MAX_BACKOFF_MULTIPLIER,
    ENTITY_CANDIDATES_LIMIT,
    ENTITY_RESOLUTION_AUTO_MERGE,
    ENTITY_RESOLUTION_NAME_SIM_THRESHOLD,
    FORGET_SEARCH_LIMIT,
    FORGET_SIMILARITY_THRESHOLD,
    RECALL_SEARCH_LIMIT,
    USER_ENTITY_NAME,
)
from ntrp.core.events import ConsolidationCompleted
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.memory.consolidation import apply_consolidation, get_consolidation_decision
from ntrp.memory.events import FactCreated, FactDeleted
from ntrp.memory.extraction import Extractor
from ntrp.memory.models import ExtractionResult, Fact, FactContext, FactType
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.linking import create_links_for_fact
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.store.retrieval import retrieve_with_observations

_logger = get_logger(__name__)


class RememberFactResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    fact: Fact
    links_created: int
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
        self.embedder = embedder or Embedder(embedding)
        self.extractor = extractor or Extractor(extraction_model)
        self.extraction_model = extraction_model
        self.channel = channel
        self._consolidation_task: asyncio.Task | None = None
        self._db_lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection]:
        async with self._db_lock:
            try:
                yield self.db.conn
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
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _logger.warning("Consolidation batch failed: %s", e)
                backoff = min(backoff * 2, max_backoff)

    async def _consolidate_pending(self, batch_size: int = 10) -> int:
        # Phase 1: read unconsolidated facts under lock
        async with self._db_lock:
            repo = FactRepository(self.db.conn)
            facts = await repo.list_unconsolidated(limit=batch_size)
            if not facts:
                return 0
            facts = [fact.model_copy(update={"entity_refs": await repo.get_entity_refs(fact.id)}) for fact in facts]

        # Phase 2: LLM decisions outside lock (DB reads + LLM calls, no writes)
        decisions = []
        for fact in facts:
            obs_repo = ObservationRepository(self.db.conn)
            fact_repo = FactRepository(self.db.conn)
            action = await get_consolidation_decision(fact, obs_repo, fact_repo, self.extraction_model)
            decisions.append((fact, action))

        # Phase 3: apply results under lock (single transaction)
        async with self.transaction() as conn:
            repo = FactRepository(conn, auto_commit=False)
            obs_repo = ObservationRepository(conn, auto_commit=False)
            count = 0
            obs_created = 0
            for fact, action in decisions:
                result = await apply_consolidation(fact, action, repo, obs_repo, self.embedder.embed_one)
                count += 1
                if result.action == "created":
                    obs_created += 1

        _logger.info("Consolidated %d facts", count)
        await self.channel.publish(ConsolidationCompleted(facts_processed=count, observations_created=obs_created))
        return count

    async def close(self) -> None:
        if self._consolidation_task:
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                pass
            self._consolidation_task = None
        await self.db.conn.close()

    async def remember(
        self,
        text: str,
        source_type: str = "explicit",
        source_ref: str | None = None,
        fact_type: FactType = FactType.WORLD,
        happened_at: datetime | None = None,
    ) -> RememberFactResult:
        embedding = await self.embedder.embed_one(text)

        async with self.transaction() as conn:
            repo = FactRepository(conn, auto_commit=False)

            fact = await repo.create(
                text=text,
                fact_type=fact_type,
                source_type=source_type,
                source_ref=source_ref,
                embedding=embedding,
                happened_at=happened_at,
            )

            extraction = await self.extractor.extract(text)
            entities_extracted = await self._process_extraction(repo, fact.id, extraction, source_ref)

            fact = fact.model_copy(update={"entity_refs": await repo.get_entity_refs(fact.id)})
            links_created = await create_links_for_fact(repo, fact)

        await self.channel.publish(FactCreated(fact_id=fact.id, text=text))

        return RememberFactResult(
            fact=fact,
            links_created=links_created,
            entities_extracted=entities_extracted,
        )

    async def _add_entity_ref(
        self,
        repo: FactRepository,
        fact_id: int,
        name: str,
        entity_type: str,
        source_ref: str | None,
        seen: set[str],
    ) -> None:
        if name in seen:
            return
        canonical_id = await self._resolve_entity(repo, name, entity_type, source_ref)
        await repo.add_entity_ref(fact_id, name, entity_type, canonical_id)
        seen.add(name)

    async def _process_extraction(
        self,
        repo: FactRepository,
        fact_id: int,
        extraction: ExtractionResult,
        source_ref: str | None,
    ) -> list[str]:
        seen: set[str] = set()

        async def add_ref(name: str, entity_type: str) -> None:
            await self._add_entity_ref(repo, fact_id, name, entity_type, source_ref, seen)

        for entity in extraction.entities:
            await add_ref(entity.name, entity.entity_type)

        for pair in extraction.entity_pairs:
            await add_ref(pair.source, pair.source_type)
            await add_ref(pair.target, pair.target_type)

        return list(seen)

    async def _create_new_entity(self, repo: FactRepository, name: str, entity_type: str) -> int:
        embedding = await self.embedder.embed_one(f"{name} ({entity_type})")
        entity = await repo.create_entity(name=name, entity_type=entity_type, embedding=embedding)
        return entity.id

    async def _find_best_candidate(
        self,
        repo: FactRepository,
        name: str,
        candidates: list,
        source_ref: str | None,
    ) -> tuple | None:
        from ntrp.memory.entity_resolution import (
            compute_resolution_score,
            name_similarity,
            temporal_proximity_score,
        )

        now = datetime.now(UTC)
        best_candidate = None
        best_score = 0.0

        for candidate in candidates:
            name_sim = name_similarity(name, candidate.name)
            if name_sim < ENTITY_RESOLUTION_NAME_SIM_THRESHOLD:
                continue

            co_occurrence = (
                1.0 if source_ref and await repo.get_entity_source_overlap(candidate.name, source_ref) else 0.0
            )

            candidate_last = await repo.get_entity_last_mention(candidate.name)
            temporal = temporal_proximity_score(now, candidate_last)
            score = compute_resolution_score(name_sim, co_occurrence, temporal)

            if score > best_score:
                best_score = score
                best_candidate = candidate

        return (best_candidate, best_score) if best_candidate else None

    async def _resolve_entity(
        self, repo: FactRepository, name: str, entity_type: str, source_ref: str | None = None
    ) -> int | None:
        existing = await repo.get_entity_by_name(name, entity_type)
        if existing:
            return existing.id

        # Name-based candidates
        name_candidates = await repo.list_entities_by_type(entity_type, limit=ENTITY_CANDIDATES_LIMIT)

        # Embedding-based candidates
        embedding = await self.embedder.embed_one(f"{name} ({entity_type})")
        vec_results = await repo.search_entities_vector(embedding, limit=ENTITY_CANDIDATES_LIMIT)
        vec_candidates = [entity for entity, _ in vec_results if entity.entity_type == entity_type]

        # Merge and deduplicate
        seen_ids: set[int] = set()
        candidates = []
        for c in [*name_candidates, *vec_candidates]:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                candidates.append(c)

        if not candidates:
            return await self._create_new_entity(repo, name, entity_type)

        result = await self._find_best_candidate(repo, name, candidates, source_ref)
        if not result:
            return await self._create_new_entity(repo, name, entity_type)

        best_candidate, best_score = result
        if best_score < ENTITY_RESOLUTION_AUTO_MERGE:
            return await self._create_new_entity(repo, name, entity_type)

        _logger.info("Entity resolution: '%s' → '%s' (score=%.2f)", name, best_candidate.name, best_score)
        return best_candidate.id

    async def recall(self, query: str, limit: int = RECALL_SEARCH_LIMIT) -> FactContext:
        repo = FactRepository(self.db.conn)
        obs_repo = ObservationRepository(self.db.conn)
        query_embedding = await self.embedder.embed_one(query)

        context = await retrieve_with_observations(repo, obs_repo, query, query_embedding, seed_limit=limit)

        async with self._db_lock:
            # Reinforce accessed facts
            if context.facts:
                await repo.reinforce([f.id for f in context.facts])

            # Reinforce accessed observations and their supporting facts
            if context.observations:
                await obs_repo.reinforce([o.id for o in context.observations])
                for obs in context.observations:
                    fact_ids = await obs_repo.get_fact_ids(obs.id)
                    if fact_ids:
                        await repo.reinforce(fact_ids)

        return context

    async def forget(self, query: str) -> int:
        repo = FactRepository(self.db.conn)
        query_embedding = await self.embedder.embed_one(query)
        results = await repo.search_facts_vector(query_embedding, limit=FORGET_SEARCH_LIMIT)

        async with self._db_lock:
            count = 0
            for fact, score in results:
                if score >= FORGET_SIMILARITY_THRESHOLD:
                    await repo.delete(fact.id)
                    count += 1
                    await self.channel.publish(FactDeleted(fact_id=fact.id))
            if count > 0:
                await repo.cleanup_orphaned_entities()
            return count

    async def merge_entities(self, names: list[str], canonical_name: str | None = None) -> int:
        if len(names) < 2:
            return 0

        async with self._db_lock:
            repo = FactRepository(self.db.conn)

            entities = []
            for name in names:
                entity = await repo.get_entity_by_name(name)
                if entity:
                    entities.append(entity)

            if len(entities) < 2:
                return 0

            if canonical_name:
                keep = next((e for e in entities if e.name == canonical_name), entities[0])
            else:
                keep = entities[0]

            merge_ids = [e.id for e in entities if e.id != keep.id]

            count = await repo.merge_entities(keep.id, merge_ids)
            _logger.info("Merged entities %s → '%s' (%d refs)", [e.name for e in entities], keep.name, count)
            return count

    async def count(self) -> int:
        repo = FactRepository(self.db.conn)
        return await repo.count()

    async def get_context(self, user_limit: int = 10, recent_limit: int = 10) -> tuple[list[Fact], list[Fact]]:
        repo = FactRepository(self.db.conn)

        user_facts = await repo.get_facts_for_entity(USER_ENTITY_NAME, limit=user_limit)
        recent_facts = await repo.list_recent(limit=recent_limit)

        return user_facts, recent_facts

    def fact_repo(self) -> FactRepository:
        return FactRepository(self.db.conn)

    def obs_repo(self) -> ObservationRepository:
        return ObservationRepository(self.db.conn)

    async def link_count(self) -> int:
        repo = FactRepository(self.db.conn)
        return await repo.link_count()

    async def clear(self) -> dict[str, int]:
        async with self._db_lock:
            repo = FactRepository(self.db.conn)
            obs_repo = ObservationRepository(self.db.conn)

            counts = {
                "facts": await repo.count(),
                "links": await repo.link_count(),
                "observations": await obs_repo.count(),
            }
            await self.db.clear_all()
            return counts
