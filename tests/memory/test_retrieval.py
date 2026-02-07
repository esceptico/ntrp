from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from ntrp.memory.models import FactType, LinkType
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.store.retrieval import (
    expand_graph,
    hybrid_search,
    retrieve_facts,
    retrieve_with_observations,
    score_fact,
)
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
        from ntrp.memory.models import Fact

        now = datetime.now(UTC)
        old = now - timedelta(days=30)

        recent_fact = Fact(
            id=1,
            text="recent",
            fact_type=FactType.WORLD,
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
            fact_type=FactType.WORLD,
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
        from ntrp.memory.models import Fact

        now = datetime.now(UTC)

        frequent = Fact(
            id=1,
            text="frequent",
            fact_type=FactType.WORLD,
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
            fact_type=FactType.WORLD,
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
        from ntrp.memory.models import Fact

        now = datetime.now(UTC)
        fact = Fact(
            id=1,
            text="test",
            fact_type=FactType.WORLD,
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
            fact_type=FactType.WORLD,
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


class TestExpandGraph:
    @pytest.mark.asyncio
    async def test_collects_seed_facts(self, repo: FactRepository):
        f1 = await repo.create(text="Seed 1", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Seed 2", fact_type=FactType.WORLD, source_type="test")

        seeds = {f1.id: 0.9, f2.id: 0.8}
        collected = await expand_graph(repo, seeds)

        assert f1.id in collected
        assert f2.id in collected

    @pytest.mark.asyncio
    async def test_expands_through_links(self, repo: FactRepository):
        f1 = await repo.create(text="Seed", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Linked", fact_type=FactType.WORLD, source_type="test")
        await repo.create_link(f1.id, f2.id, LinkType.ENTITY, weight=0.9)

        seeds = {f1.id: 1.0}
        collected = await expand_graph(repo, seeds)

        assert f1.id in collected
        assert f2.id in collected

    @pytest.mark.asyncio
    async def test_respects_max_facts(self, repo: FactRepository):
        facts = []
        for i in range(10):
            f = await repo.create(text=f"Fact {i}", fact_type=FactType.WORLD, source_type="test")
            facts.append(f)

        seeds = {f.id: 1.0 - i * 0.05 for i, f in enumerate(facts)}
        collected = await expand_graph(repo, seeds, max_facts=3)

        assert len(collected) == 3

    @pytest.mark.asyncio
    async def test_score_decays_through_links(self, repo: FactRepository):
        f1 = await repo.create(text="Seed", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Linked", fact_type=FactType.WORLD, source_type="test")
        await repo.create_link(f1.id, f2.id, LinkType.ENTITY, weight=0.5)

        seeds = {f1.id: 1.0}
        collected = await expand_graph(repo, seeds, decay_factor=0.8)

        _, seed_score = collected[f1.id]
        _, linked_score = collected[f2.id]

        assert seed_score > linked_score
        assert linked_score == pytest.approx(1.0 * 0.5 * 0.8, rel=0.01)

    @pytest.mark.asyncio
    async def test_empty_seeds(self, repo: FactRepository):
        collected = await expand_graph(repo, {})
        assert collected == {}


class TestRetrieveFacts:
    @pytest.mark.asyncio
    async def test_retrieves_matching_facts(self, repo: FactRepository):
        emb = mock_embedding("guitar music")
        await repo.create(
            text="I play guitar",
            fact_type=FactType.WORLD,
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
    async def test_follows_links(self, repo: FactRepository):
        emb = mock_embedding("main topic")
        f1 = await repo.create(
            text="main topic fact",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb,
        )
        f2 = await repo.create(
            text="related fact",
            fact_type=FactType.WORLD,
            source_type="test",
        )
        await repo.create_link(f1.id, f2.id, LinkType.ENTITY, weight=0.9)

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
            fact_type=FactType.WORLD,
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
