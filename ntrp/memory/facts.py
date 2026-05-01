import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Self, TypedDict

import aiosqlite
from pydantic import BaseModel, ConfigDict

import ntrp.database as database
from ntrp.constants import (
    FACT_DEDUP_EMBEDDING_SIMILARITY,
    FACT_DEDUP_TEXT_RATIO,
    FORGET_SEARCH_LIMIT,
    FORGET_SIMILARITY_THRESHOLD,
    RECALL_SEARCH_LIMIT,
    SYSTEM_PROMPT_OBSERVATION_LIMIT,
    SYSTEM_PROMPT_PROFILE_LIMIT,
    USER_ENTITY_NAME,
)
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.memory.audit import memory_audit
from ntrp.memory.consolidation_runner import ConsolidationRunner
from ntrp.memory.decay import decay_score
from ntrp.memory.extraction import Extractor
from ntrp.memory.models import ExtractedEntity, ExtractionResult, Fact, FactContext, FactKind, Observation, SourceType
from ntrp.memory.retrieval import retrieve_with_observations
from ntrp.memory.store.access_events import MemoryAccessEventRepository
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.events import MemoryEventRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.learning import LearningRepository
from ntrp.memory.store.observations import ObservationRepository

_logger = get_logger(__name__)

PROFILE_FACT_KINDS = (
    FactKind.IDENTITY,
    FactKind.PREFERENCE,
    FactKind.RELATIONSHIP,
    FactKind.CONSTRAINT,
)


class RememberFactResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    fact: Fact
    entities_extracted: list[str]


@dataclass(frozen=True)
class SessionMemory:
    observations: list[Observation]
    profile_facts: list[Fact]
    user_facts: list[Fact]


def _dedupe_ids(ids: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def _context_fact_ids(context: FactContext) -> list[int]:
    ids = [fact.id for fact in context.facts]
    ids.extend(fact.id for facts in context.bundled_sources.values() for fact in facts)
    return _dedupe_ids(ids)


def _context_observation_ids(context: FactContext) -> list[int]:
    return _dedupe_ids([observation.id for observation in context.observations])


def _session_fact_ids(memory: SessionMemory) -> list[int]:
    ids = [fact.id for fact in memory.profile_facts]
    ids.extend(fact.id for fact in memory.user_facts)
    return _dedupe_ids(ids)


def _is_active_fact(fact: Fact, now: datetime | None = None) -> bool:
    if fact.archived_at is not None or fact.superseded_by_fact_id is not None:
        return False
    if fact.expires_at is None:
        return True
    return fact.expires_at > (now or datetime.now(UTC))


def _storage_issue_count(storage: dict[str, object]) -> int:
    keys = ("missing_vec_rows", "stale_vec_rows", "missing_fts_rows", "stale_fts_rows")
    return sum(int(storage.get(key, 0) or 0) for key in keys)


def _provenance_issue_count(provenance: dict[str, dict[str, object]]) -> int:
    keys = (
        "records_without_sources",
        "duplicate_source_refs",
        "missing_source_refs",
        "records_with_missing_sources",
        "archived_source_refs",
        "records_with_archived_sources",
    )
    return sum(int(area.get(key, 0) or 0) for area in provenance.values() for key in keys)


class ReembedProgress(TypedDict):
    total: int
    done: int


class RepairEmbeddingsResult(TypedDict):
    apply: bool
    fact_ids: list[int]
    observation_ids: list[int]
    facts_repaired: int
    observations_repaired: int


class FactMemory:
    def __init__(
        self,
        conn: aiosqlite.Connection,
        embedding: EmbeddingConfig,
        model: str,
        embedder: Embedder | None = None,
        extractor: Extractor | None = None,
        read_conn: aiosqlite.Connection | None = None,
        enqueue_fact_index_upsert: Callable[[int, str], Awaitable[bool]] | None = None,
        enqueue_fact_index_delete: Callable[[int], Awaitable[bool]] | None = None,
    ):
        self.db = GraphDatabase(conn, embedding.dim)
        self.facts = FactRepository(conn, read_conn)
        self.observations = ObservationRepository(conn, read_conn)
        self.dreams = DreamRepository(conn, read_conn)
        self.events = MemoryEventRepository(conn, read_conn)
        self.access_events = MemoryAccessEventRepository(conn, read_conn)
        self.learning = LearningRepository(conn, read_conn)
        self.embedder = embedder or Embedder(embedding)
        self.extractor = extractor or Extractor(model)
        self._enqueue_fact_index_upsert = enqueue_fact_index_upsert
        self._enqueue_fact_index_delete = enqueue_fact_index_delete
        self._db_lock = asyncio.Lock()
        self._reembed_task: asyncio.Task | None = None
        self._reembed_progress: ReembedProgress | None = None

        self._consolidation = ConsolidationRunner(
            facts=self.facts,
            observations=self.observations,
            dreams=self.dreams,
            embedder=self.embedder,
            model_fn=lambda: self.model,
            transaction=self.transaction,
            db_lock=self._db_lock,
            db_conn=conn,
            events=self.events,
        )

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
        return self._consolidation.running

    @classmethod
    async def create(
        cls,
        db_path: Path,
        embedding: EmbeddingConfig,
        model: str,
        enqueue_fact_index_upsert: Callable[[int, str], Awaitable[bool]] | None = None,
        enqueue_fact_index_delete: Callable[[int], Awaitable[bool]] | None = None,
    ) -> Self:
        conn = await database.connect(db_path, vec=True)
        read_conn = await database.connect(db_path, vec=True, readonly=True)
        instance = cls(
            conn,
            embedding,
            model,
            read_conn=read_conn,
            enqueue_fact_index_upsert=enqueue_fact_index_upsert,
            enqueue_fact_index_delete=enqueue_fact_index_delete,
        )
        await instance.db.init_schema()
        if instance.db.dim_changed:
            _logger.info("Embedding dimension changed — starting background re-embed")
            instance.start_reembed(embedding)
        return instance

    # --- Consolidation delegation ---

    @property
    def dreams_enabled(self) -> bool:
        return self._consolidation.dreams_enabled

    @dreams_enabled.setter
    def dreams_enabled(self, value: bool) -> None:
        self._consolidation.dreams_enabled = value

    async def run_consolidation(self) -> str:
        return await self._consolidation.run_consolidation()

    async def run_memory_maintenance(self) -> str:
        return await self._consolidation.run_maintenance()

    async def run_memory_health_audit(self) -> str:
        audit = await memory_audit(self.facts.read_conn)
        facts = audit["facts"]
        observations = audit["observations"]
        storage = audit["storage"]
        storage_issues = _storage_issue_count(storage["facts"]) + _storage_issue_count(storage["observations"])
        provenance_issues = _provenance_issue_count(audit["provenance"])
        relations = sum(int(value) for value in audit["relations"].values())
        return (
            f"facts active={facts['active']} unconsolidated={facts['unconsolidated']} "
            f"patterns active={observations['active']} zero_access={observations['zero_access']} "
            f"storage_issues={storage_issues} provenance_issues={provenance_issues} relation_issues={relations}"
        )

    # --- Re-embedding ---

    @property
    def reembed_running(self) -> bool:
        return self._reembed_task is not None and not self._reembed_task.done()

    @property
    def reembed_progress(self) -> ReembedProgress | None:
        return self._reembed_progress

    @property
    def model(self) -> str:
        return self.extractor.model

    def update_model(self, model: str) -> None:
        self.extractor.model = model

    def start_reembed(self, embedding: EmbeddingConfig, *, rebuild: bool = False) -> None:
        if self._reembed_task and not self._reembed_task.done():
            self._reembed_task.cancel()
        self._reembed_task = asyncio.create_task(self._run_reembed(embedding, rebuild=rebuild))

    async def repair_missing_embeddings(self, *, limit: int = 100, apply: bool = False) -> RepairEmbeddingsResult:
        facts = await self.facts.list_missing_embeddings(limit=max(0, limit))
        observation_limit = max(0, limit - len(facts))
        observations = await self.observations.list_missing_embeddings(limit=observation_limit)

        result: RepairEmbeddingsResult = {
            "apply": apply,
            "fact_ids": [fact.id for fact in facts],
            "observation_ids": [obs.id for obs in observations],
            "facts_repaired": 0,
            "observations_repaired": 0,
        }
        if not apply or (not facts and not observations):
            return result

        fact_embeddings = await self.embedder.embed([fact.text for fact in facts]) if facts else []
        observation_embeddings = (
            await self.embedder.embed([obs.summary for obs in observations]) if observations else []
        )

        async with self.transaction():
            for fact, embedding in zip(facts, fact_embeddings, strict=False):
                await self.facts.update_embedding(fact.id, embedding)
            for obs, embedding in zip(observations, observation_embeddings, strict=False):
                await self.observations.update_embedding(obs.id, embedding)
            await self.events.create(
                actor="backend",
                action="embeddings.repaired",
                target_type="memory",
                reason="manual missing-embedding repair",
                policy_version="memory.repair.v1",
                details={
                    "fact_ids": result["fact_ids"],
                    "observation_ids": result["observation_ids"],
                },
            )

        result["facts_repaired"] = len(facts)
        result["observations_repaired"] = len(observations)
        return result

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

    # --- Lifecycle ---

    async def close(self) -> None:
        if self._reembed_task:
            self._reembed_task.cancel()
            try:
                await self._reembed_task
            except asyncio.CancelledError:
                pass
            self._reembed_task = None
        if self.facts.read_conn is not self.db.conn:
            await self.facts.read_conn.close()
        await self.db.conn.close()

    # --- Core API ---

    async def remember(
        self,
        text: str,
        source_type: SourceType = SourceType.EXPLICIT,
        source_ref: str | None = None,
        happened_at: datetime | None = None,
        kind: FactKind = FactKind.NOTE,
        salience: int = 0,
        confidence: float = 1.0,
        expires_at: datetime | None = None,
        entity_names: Sequence[str] | None = None,
    ) -> RememberFactResult | None:
        if not text or not text.strip():
            return None

        if entity_names is None:
            embedding, extraction = await asyncio.gather(
                self.embedder.embed_one(text),
                self.extractor.extract(text),
            )
        else:
            embedding = await self.embedder.embed_one(text)
            extraction = ExtractionResult(entities=[ExtractedEntity(name=name) for name in entity_names])

        async with self.transaction():
            similar = [
                (fact, similarity)
                for fact, similarity in await self.facts.search_facts_vector(embedding, limit=5)
                if _is_active_fact(fact)
            ]
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
                kind=kind,
                salience=salience,
                confidence=confidence,
                expires_at=expires_at,
            )
            entities_extracted = await self._process_extraction(fact.id, extraction)
            await self.events.create(
                actor="backend",
                action="fact.created",
                target_type="fact",
                target_id=fact.id,
                source_type=source_type.value,
                source_ref=source_ref,
                reason="remembered fact",
                policy_version="memory.remember.v1",
                details={
                    "kind": kind.value,
                    "salience": salience,
                    "confidence": confidence,
                    "expires_at": expires_at,
                    "happened_at": happened_at,
                    "entity_count": len(entities_extracted),
                },
            )

        if self._enqueue_fact_index_upsert:
            await self._enqueue_fact_index_upsert(fact.id, text)
        return RememberFactResult(fact=fact, entities_extracted=entities_extracted)

    async def _process_extraction(self, fact_id: int, extraction: ExtractionResult) -> list[str]:
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
        if existing := await self.facts.get_entity_by_name(name):
            return existing.id
        entity = await self.facts.create_entity(name=name)
        return entity.id

    async def recall(
        self,
        query: str,
        limit: int = RECALL_SEARCH_LIMIT,
        query_time: datetime | None = None,
    ) -> FactContext:
        context = await self.inspect_recall(query=query, limit=limit, query_time=query_time)
        fact_ids = _context_fact_ids(context)
        observation_ids = _context_observation_ids(context)
        await self.reinforce_accessed_memory(fact_ids=fact_ids, observation_ids=observation_ids)
        return context

    async def reinforce_accessed_memory(
        self,
        *,
        fact_ids: list[int],
        observation_ids: list[int],
    ) -> None:
        async with self.transaction():
            if fact_ids:
                await self.facts.reinforce(fact_ids)
            if observation_ids:
                await self.observations.reinforce(observation_ids)

    async def inspect_recall(
        self,
        query: str,
        limit: int = RECALL_SEARCH_LIMIT,
        query_time: datetime | None = None,
    ) -> FactContext:
        query_embedding = await self.embedder.embed_one(query)
        return await retrieve_with_observations(
            self.facts,
            self.observations,
            query,
            query_embedding,
            seed_limit=limit,
            query_time=query_time,
        )

    async def record_context_access(
        self,
        *,
        source: str,
        context: FactContext,
        query: str | None = None,
        formatted_chars: int = 0,
        injected_fact_ids: list[int] | None = None,
        injected_observation_ids: list[int] | None = None,
        bundled_fact_ids: list[int] | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        fact_ids = _context_fact_ids(context)
        observation_ids = _context_observation_ids(context)
        injected_fact_ids = _dedupe_ids(injected_fact_ids) if injected_fact_ids is not None else fact_ids
        injected_observation_ids = (
            _dedupe_ids(injected_observation_ids) if injected_observation_ids is not None else observation_ids
        )
        bundled_ids = (
            _dedupe_ids(bundled_fact_ids)
            if bundled_fact_ids is not None
            else _dedupe_ids([fact.id for facts in context.bundled_sources.values() for fact in facts])
        )
        omitted_fact_ids = [fact_id for fact_id in fact_ids if fact_id not in set(injected_fact_ids)]
        omitted_observation_ids = [obs_id for obs_id in observation_ids if obs_id not in set(injected_observation_ids)]
        async with self.transaction():
            await self.access_events.create(
                source=source,
                query=query,
                retrieved_fact_ids=fact_ids,
                retrieved_observation_ids=observation_ids,
                injected_fact_ids=injected_fact_ids,
                injected_observation_ids=injected_observation_ids,
                omitted_fact_ids=omitted_fact_ids,
                omitted_observation_ids=omitted_observation_ids,
                bundled_fact_ids=bundled_ids,
                formatted_chars=formatted_chars,
                policy_version="memory.access.v1",
                details=details,
            )

    async def record_session_memory_access(
        self,
        *,
        source: str,
        memory: SessionMemory,
        formatted_chars: int = 0,
        injected_fact_ids: list[int] | None = None,
        injected_observation_ids: list[int] | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        fact_ids = _session_fact_ids(memory)
        observation_ids = _dedupe_ids([observation.id for observation in memory.observations])
        injected_fact_ids = _dedupe_ids(injected_fact_ids) if injected_fact_ids is not None else fact_ids
        injected_observation_ids = (
            _dedupe_ids(injected_observation_ids) if injected_observation_ids is not None else observation_ids
        )
        omitted_fact_ids = [fact_id for fact_id in fact_ids if fact_id not in set(injected_fact_ids)]
        omitted_observation_ids = [obs_id for obs_id in observation_ids if obs_id not in set(injected_observation_ids)]
        async with self.transaction():
            await self.access_events.create(
                source=source,
                retrieved_fact_ids=fact_ids,
                retrieved_observation_ids=observation_ids,
                injected_fact_ids=injected_fact_ids,
                injected_observation_ids=injected_observation_ids,
                omitted_fact_ids=omitted_fact_ids,
                omitted_observation_ids=omitted_observation_ids,
                formatted_chars=formatted_chars,
                policy_version="memory.access.v1",
                details=details,
            )

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
                    await self.events.create(
                        actor="backend",
                        action="fact.deleted",
                        target_type="fact",
                        target_id=fact.id,
                        reason="forget query matched threshold",
                        policy_version="memory.forget.v1",
                        details={"score": round(float(score), 4)},
                    )
                    count += 1
            if count > 0:
                await self.observations.remove_source_facts(deleted_ids)
                await self.dreams.remove_source_facts(deleted_ids)
                await self.facts.cleanup_orphaned_entities()
        if self._enqueue_fact_index_delete:
            for fact_id in deleted_ids:
                await self._enqueue_fact_index_delete(fact_id)
        return count

    async def merge_entities(self, names: list[str], canonical_name: str | None = None) -> int:
        if len(names) < 2:
            return 0

        async with self.transaction():
            entities = []
            for name in names:
                if entity := await self.facts.get_entity_by_name(name):
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

    async def get_profile(self, limit: int = SYSTEM_PROMPT_PROFILE_LIMIT) -> list[Fact]:
        return await self.facts.list_profile_facts(PROFILE_FACT_KINDS, limit=limit)

    async def get_session_memory(
        self,
        user_limit: int = 10,
        profile_limit: int = SYSTEM_PROMPT_PROFILE_LIMIT,
    ) -> SessionMemory:
        if user_entity := await self.facts.get_entity_by_name(USER_ENTITY_NAME):
            raw_obs = await self.observations.get_for_entity(user_entity.id, limit=20)
            source_ids = _dedupe_ids([fact_id for obs in raw_obs for fact_id in obs.source_fact_ids])
            source_facts = await self.facts.get_batch(source_ids)
            active_source_ids = {
                fact_id for fact_id, fact in source_facts.items() if _is_active_fact(fact)
            }
            raw_obs = [
                obs for obs in raw_obs
                if len([fact_id for fact_id in obs.source_fact_ids if fact_id in active_source_ids]) >= 2
            ]
            scored_obs = sorted(
                raw_obs,
                key=lambda o: decay_score(o.last_accessed_at, o.access_count),
                reverse=True,
            )
            observations = scored_obs[:SYSTEM_PROMPT_OBSERVATION_LIMIT]
        else:
            observations = []

        profile_facts = await self.get_profile(limit=profile_limit)

        exclude_ids: set[int] = set()
        for obs in observations:
            exclude_ids.update(obs.source_fact_ids)
        exclude_ids.update(f.id for f in profile_facts)

        all_user_facts = await self.facts.get_facts_for_entity(USER_ENTITY_NAME, limit=user_limit + len(exclude_ids))
        user_facts = [f for f in all_user_facts if f.id not in exclude_ids][:user_limit]

        return SessionMemory(observations=observations, profile_facts=profile_facts, user_facts=user_facts)

    async def get_context(self, user_limit: int = 10) -> tuple[list[Observation], list[Fact]]:
        session_memory = await self.get_session_memory(user_limit=user_limit)
        return session_memory.observations, [*session_memory.profile_facts, *session_memory.user_facts]

    async def clear_observations(self) -> dict[str, int]:
        async with self.transaction():
            obs_count = await self.observations.clear_all()
            facts_reset = await self.facts.reset_consolidated()
            await self.events.create(
                actor="backend",
                action="observations.cleared",
                target_type="observation",
                reason="clear observations",
                policy_version="memory.clear_observations.v1",
                details={"observations_deleted": obs_count, "facts_reset": facts_reset},
            )
            return {"observations_deleted": obs_count, "facts_reset": facts_reset}

    async def clear(self) -> dict[str, int]:
        async with self.transaction():
            counts = {
                "facts": await self.facts.count(),
                "observations": await self.observations.count(),
            }
            await self.db.clear_all()
            return counts
