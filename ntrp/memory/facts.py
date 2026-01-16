from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from ntrp.constants import (
    ENTITY_CANDIDATES_LIMIT,
    ENTITY_RESOLUTION_AUTO_MERGE,
    ENTITY_RESOLUTION_NAME_SIM_THRESHOLD,
    FORGET_SEARCH_LIMIT,
    FORGET_SIMILARITY_THRESHOLD,
    RECALL_SEARCH_LIMIT,
)
from ntrp.embedder import Embedder, EmbeddingConfig
from ntrp.logging import get_logger
from ntrp.memory.consolidation import consolidate_fact
from ntrp.memory.extraction import Extractor
from ntrp.memory.models import ExtractionResult, Fact, FactContext, FactType
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.linking import create_links_for_fact
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.store.retrieval import retrieve_with_observations

logger = get_logger(__name__)


@dataclass
class RememberFactResult:
    fact: Fact
    links_created: int
    entities_extracted: list[str]


class FactMemory:
    def __init__(self, db_path: Path, embedding: EmbeddingConfig, extraction_model: str):
        self.db = GraphDatabase(db_path, embedding.dim)
        self.embedder = Embedder(embedding)
        self.extractor = Extractor(extraction_model)
        self.extraction_model = extraction_model

    @classmethod
    async def create(cls, db_path: Path, embedding: EmbeddingConfig, extraction_model: str) -> Self:
        instance = cls(db_path, embedding, extraction_model)
        await instance.db.connect()
        return instance

    async def close(self) -> None:
        await self.db.close()

    async def remember(
        self,
        text: str,
        source_type: str = "explicit",
        source_ref: str | None = None,
        fact_type: FactType = FactType.WORLD,
        happened_at: datetime | None = None,
    ) -> RememberFactResult:
        repo = FactRepository(self.db.conn)
        obs_repo = ObservationRepository(self.db.conn)

        embedding = await self.embedder.embed_one(text)
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

        fact.entity_refs = await repo.get_entity_refs(fact.id)
        links_created = await create_links_for_fact(repo, fact)

        # Consolidate immediately
        await consolidate_fact(
            fact=fact,
            fact_repo=repo,
            obs_repo=obs_repo,
            model=self.extraction_model,
            embed_fn=self.embedder.embed_one,
        )

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

        for entity in extraction.entities:
            await self._add_entity_ref(repo, fact_id, entity.name, entity.entity_type, source_ref, seen)

        for pair in extraction.entity_pairs:
            await self._add_entity_ref(repo, fact_id, pair.source, "other", source_ref, seen)
            await self._add_entity_ref(repo, fact_id, pair.target, "other", source_ref, seen)

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

        now = datetime.now()
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

        candidates = await repo.list_entities_by_type(entity_type, limit=ENTITY_CANDIDATES_LIMIT)
        if not candidates:
            return await self._create_new_entity(repo, name, entity_type)

        result = await self._find_best_candidate(repo, name, candidates, source_ref)
        if not result:
            return await self._create_new_entity(repo, name, entity_type)

        best_candidate, best_score = result
        if best_score < ENTITY_RESOLUTION_AUTO_MERGE:
            return await self._create_new_entity(repo, name, entity_type)

        logger.info(f"Entity resolution: '{name}' → '{best_candidate.name}' (score={best_score:.2f})")
        return best_candidate.id

    async def recall(self, query: str, limit: int = RECALL_SEARCH_LIMIT) -> FactContext:
        repo = FactRepository(self.db.conn)
        obs_repo = ObservationRepository(self.db.conn)
        query_embedding = await self.embedder.embed_one(query)

        context = await retrieve_with_observations(repo, obs_repo, query, query_embedding, seed_limit=limit)

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

        count = 0
        for fact, score in results:
            if score >= FORGET_SIMILARITY_THRESHOLD:
                await repo.delete(fact.id)
                count += 1
        return count

    async def merge_entities(self, names: list[str], canonical_name: str | None = None) -> int:
        if len(names) < 2:
            return 0

        repo = FactRepository(self.db.conn)

        entities = []
        for name in names:
            entity = await repo.get_entity_by_name(name)
            if entity:
                entities.append(entity)

        if len(entities) < 2:
            return 0

        keep = next((e for e in entities if e.name == canonical_name), entities[0]) if canonical_name else entities[0]

        merge_ids = [e.id for e in entities if e.id != keep.id]

        count = await repo.merge_entities(keep.id, merge_ids)
        logger.info(f"Merged entities {[e.name for e in entities]} → '{keep.name}' ({count} refs)")
        return count

    async def count(self) -> int:
        repo = FactRepository(self.db.conn)
        return await repo.count()

    async def get_context(self, user_limit: int = 10, recent_limit: int = 10) -> tuple[list[Fact], list[Fact]]:
        """Get memory context for prompt injection. Returns (user_facts, recent_facts)."""
        repo = FactRepository(self.db.conn)

        user_facts = await repo.get_facts_for_entity("User", limit=user_limit)
        recent_facts = await repo.list_recent(limit=recent_limit)

        return user_facts, recent_facts
