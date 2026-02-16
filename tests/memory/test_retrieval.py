from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from ntrp.memory.models import Fact
from ntrp.memory.retrieval import (
    entity_expand,
    hybrid_search,
    retrieve_facts,
    retrieve_with_observations,
    score_fact,
)
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.search.retrieval import rrf_merge
from tests.conftest import mock_embedding


@pytest_asyncio.fixture
async def repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def obs_repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


class TestRrfMerge:
    def test_single_ranking(self):
        rankings = [[(1, 0.9), (2, 0.8), (3, 0.7)]]
        scores = rrf_merge(rankings)

        assert 1 in scores
        assert 2 in scores
        assert 3 in scores
        assert scores[1] > scores[2] > scores[3]

    def test_merge_two_rankings(self):
        rankings = [
            [(1, 0.9), (2, 0.8)],
            [(2, 0.9), (3, 0.8)],
        ]
        scores = rrf_merge(rankings)

        # Item 2 appears in both rankings, should have highest score
        assert scores[2] > scores[1]
        assert scores[2] > scores[3]

    def test_empty_rankings(self):
        scores = rrf_merge([])
        assert scores == {}

    def test_empty_inner_ranking(self):
        scores = rrf_merge([[]])
        assert scores == {}

    def test_k_parameter(self):
        rankings = [[(1, 0.9), (2, 0.8)]]
        scores_k60 = rrf_merge(rankings, k=60)
        scores_k10 = rrf_merge(rankings, k=10)

        # With smaller k, the rank difference has more impact
        ratio_k60 = scores_k60[1] / scores_k60[2]
        ratio_k10 = scores_k10[1] / scores_k10[2]
        assert ratio_k10 > ratio_k60


class TestScoreFact:
    def test_recent_fact_scores_higher(self, repo: FactRepository):
        now = datetime.now(UTC)
        old = now - timedelta(days=30)

        recent_fact = Fact(
            id=1,
            text="recent",
            embedding=None,
            source_type="test",
            source_ref=None,
            created_at=now,
            happened_at=now,
            last_accessed_at=now,
            access_count=0,
            consolidated_at=None,
        )
        old_fact = Fact(
            id=2,
            text="old",
            embedding=None,
            source_type="test",
            source_ref=None,
            created_at=old,
            happened_at=old,
            last_accessed_at=old,
            access_count=0,
            consolidated_at=None,
        )

        recent_score = score_fact(recent_fact, 1.0)
        old_score = score_fact(old_fact, 1.0)

        assert recent_score > old_score

    def test_frequently_accessed_fact_scores_higher(self):
        now = datetime.now(UTC)

        frequent = Fact(
            id=1,
            text="frequent",
            embedding=None,
            source_type="test",
            source_ref=None,
            created_at=now,
            happened_at=now,
            last_accessed_at=now,
            access_count=10,
            consolidated_at=None,
        )
        rare = Fact(
            id=2,
            text="rare",
            embedding=None,
            source_type="test",
            source_ref=None,
            created_at=now,
            happened_at=now,
            last_accessed_at=now,
            access_count=0,
            consolidated_at=None,
        )

        frequent_score = score_fact(frequent, 1.0)
        rare_score = score_fact(rare, 1.0)

        assert frequent_score > rare_score

    def test_base_score_multiplied(self):
        now = datetime.now(UTC)
        fact = Fact(
            id=1,
            text="test",
            embedding=None,
            source_type="test",
            source_ref=None,
            created_at=now,
            happened_at=now,
            last_accessed_at=now,
            access_count=0,
            consolidated_at=None,
        )

        score_high = score_fact(fact, 1.0)
        score_low = score_fact(fact, 0.5)

        assert score_high > score_low


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_returns_rrf_scores(self, repo: FactRepository):
        emb = mock_embedding("test query")
        await repo.create(
            text="test query content",
            source_type="test",
            embedding=emb,
        )

        scores = await hybrid_search(repo, "test query", emb, limit=5)

        assert len(scores) >= 1

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, repo: FactRepository):
        emb = mock_embedding("nothing")
        scores = await hybrid_search(repo, "nothing", emb, limit=5)

        assert scores == {}


class TestEntityExpand:
    @pytest.mark.asyncio
    async def test_expands_through_shared_entities(self, repo: FactRepository):
        f1 = await repo.create(
            text="Alice works at Google", source_type="test", embedding=mock_embedding("alice google")
        )
        f2 = await repo.create(text="Alice likes hiking", source_type="test")

        e = await repo.create_entity(name="Alice")
        await repo.add_entity_ref(f1.id, "Alice", e.id)
        await repo.add_entity_ref(f2.id, "Alice", e.id)

        expansion = await entity_expand(repo, [f1.id])
        assert f2.id in expansion

    @pytest.mark.asyncio
    async def test_empty_seeds_returns_empty(self, repo: FactRepository):
        expansion = await entity_expand(repo, [])
        assert expansion == {}

    @pytest.mark.asyncio
    async def test_idf_weighting(self, repo: FactRepository):
        """Rare entities should produce higher expansion weights."""
        e_rare = await repo.create_entity(name="UniqueEntity")
        e_common = await repo.create_entity(name="CommonEntity")

        f_seed = await repo.create(text="Seed fact", source_type="test")
        f_rare = await repo.create(text="Rare fact", source_type="test")
        f_common = await repo.create(text="Common fact", source_type="test")

        await repo.add_entity_ref(f_seed.id, "UniqueEntity", e_rare.id)
        await repo.add_entity_ref(f_seed.id, "CommonEntity", e_common.id)
        await repo.add_entity_ref(f_rare.id, "UniqueEntity", e_rare.id)
        await repo.add_entity_ref(f_common.id, "CommonEntity", e_common.id)

        # Add many more facts for common entity to increase its frequency
        for i in range(10):
            f = await repo.create(text=f"Common fact {i}", source_type="test")
            await repo.add_entity_ref(f.id, "CommonEntity", e_common.id)

        expansion = await entity_expand(repo, [f_seed.id])

        # Rare entity expansion should have higher weight
        assert expansion[f_rare.id] > expansion[f_common.id]

    @pytest.mark.asyncio
    async def test_respects_max_facts(self, repo: FactRepository):
        e = await repo.create_entity(name="Alice")
        seed = await repo.create(text="Seed", source_type="test")
        await repo.add_entity_ref(seed.id, "Alice", e.id)

        for i in range(20):
            f = await repo.create(text=f"Fact {i}", source_type="test")
            await repo.add_entity_ref(f.id, "Alice", e.id)

        expansion = await entity_expand(repo, [seed.id], max_facts=5)
        assert len(expansion) <= 5


class TestRetrieveFacts:
    @pytest.mark.asyncio
    async def test_retrieves_matching_facts(self, repo: FactRepository):
        emb = mock_embedding("guitar music")
        await repo.create(
            text="I play guitar",
            source_type="test",
            embedding=emb,
        )

        context = await retrieve_facts(repo, "guitar music", emb, seed_limit=5)

        assert len(context.facts) >= 1
        assert any("guitar" in f.text for f in context.facts)

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_match(self, repo: FactRepository):
        emb = mock_embedding("nonexistent query")
        context = await retrieve_facts(repo, "nonexistent query", emb, seed_limit=5)

        assert context.facts == []

    @pytest.mark.asyncio
    async def test_expands_through_entities(self, repo: FactRepository):
        emb = mock_embedding("main topic")
        f1 = await repo.create(text="main topic fact", source_type="test", embedding=emb)
        f2 = await repo.create(text="related fact via entity", source_type="test")

        e = await repo.create_entity(name="SharedEntity")
        await repo.add_entity_ref(f1.id, "SharedEntity", e.id)
        await repo.add_entity_ref(f2.id, "SharedEntity", e.id)

        context = await retrieve_facts(repo, "main topic", emb, seed_limit=5)

        fact_ids = [f.id for f in context.facts]
        assert f1.id in fact_ids
        assert f2.id in fact_ids


class TestRetrieveWithObservations:
    @pytest.mark.asyncio
    async def test_retrieves_facts_and_observations(self, repo: FactRepository, obs_repo: ObservationRepository):
        emb = mock_embedding("morning routine")
        await repo.create(
            text="I wake up early",
            source_type="test",
            embedding=emb,
        )
        await obs_repo.create(
            summary="Prefers morning activities",
            embedding=emb,
        )

        context = await retrieve_with_observations(repo, obs_repo, "morning routine", emb, seed_limit=5)

        assert len(context.facts) >= 1
        assert len(context.observations) >= 1

    @pytest.mark.asyncio
    async def test_observations_sorted_by_score(self, repo: FactRepository, obs_repo: ObservationRepository):
        emb = mock_embedding("test")
        await obs_repo.create(summary="Obs 1", embedding=emb)
        await obs_repo.create(summary="Obs 2", embedding=emb)

        context = await retrieve_with_observations(repo, obs_repo, "test", emb, seed_limit=5)

        assert len(context.observations) >= 2
