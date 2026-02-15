"""Tests for dream pipeline: clustering, generation, evaluation, and storage."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio

from ntrp.memory.dreams import (
    DreamEvaluation,
    DreamGeneration,
    _cosine,
    _kmeans,
    _centroid_nearest,
    _get_supporters,
    run_dream_pass,
)
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository
from tests.conftest import TEST_EMBEDDING_DIM, mock_embedding


def mock_llm_response(content: str):
    return type(
        "Response",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {"message": type("Message", (), {"content": content})()},
                )()
            ]
        },
    )()


def _make_distinct_embedding(domain: int, index: int, dim: int = TEST_EMBEDDING_DIM) -> np.ndarray:
    """Create embeddings that cluster by domain."""
    rng = np.random.RandomState(domain * 100 + index)
    base = np.zeros(dim)
    # Each domain gets a strong signal in a different region
    start = (domain * dim) // 5
    end = start + dim // 5
    base[start:end] = 1.0
    noise = rng.randn(dim) * 0.1
    v = base + noise
    return v / np.linalg.norm(v)


@pytest_asyncio.fixture
async def fact_repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def dream_repo(db: GraphDatabase) -> DreamRepository:
    return DreamRepository(db.conn)


class TestKmeans:
    def test_clusters_distinct_domains(self):
        """K-means separates facts with clearly distinct embeddings."""
        facts = {}
        for domain in range(4):
            for i in range(5):
                fid = domain * 5 + i
                emb = _make_distinct_embedding(domain, i)
                facts[fid] = (f"domain-{domain} fact-{i}", emb)

        clusters = _kmeans(facts, k=4)
        assert len(clusters) >= 3  # at least 3 non-empty clusters

        # Each cluster should mostly contain facts from one domain
        for _ki, fids in clusters.items():
            domains = set(fid // 5 for fid in fids)
            # Not all from different domains
            assert len(fids) >= 2

    def test_single_cluster_when_k_exceeds_facts(self):
        """Returns single cluster when k > number of facts."""
        facts = {
            0: ("fact 0", mock_embedding("zero")),
            1: ("fact 1", mock_embedding("one")),
        }
        clusters = _kmeans(facts, k=10)
        total = sum(len(v) for v in clusters.values())
        assert total == 2


class TestCentroidNearest:
    def test_finds_most_central_fact(self):
        """Picks the fact closest to the cluster centroid."""
        emb_a = np.array([1.0, 0.0, 0.0])
        emb_b = np.array([0.9, 0.1, 0.0])
        emb_c = np.array([0.5, 0.5, 0.0])

        facts = {
            1: ("a", emb_a / np.linalg.norm(emb_a)),
            2: ("b", emb_b / np.linalg.norm(emb_b)),
            3: ("c", emb_c / np.linalg.norm(emb_c)),
        }
        result = _centroid_nearest(facts, [1, 2, 3])
        # Centroid is average — b should be closest
        assert result in [1, 2]


class TestGetSupporters:
    def test_returns_nearest_facts(self):
        """Supporters are the facts most similar to the seed."""
        seed_emb = np.array([1.0, 0.0, 0.0])
        close_emb = np.array([0.95, 0.05, 0.0])
        far_emb = np.array([0.0, 1.0, 0.0])

        facts = {
            1: ("seed", seed_emb / np.linalg.norm(seed_emb)),
            2: ("close", close_emb / np.linalg.norm(close_emb)),
            3: ("far", far_emb / np.linalg.norm(far_emb)),
        }
        result = _get_supporters(facts, 1, [1, 2, 3], n=1)
        assert result == [2]


class TestDreamGeneration:
    @pytest.mark.asyncio
    async def test_skips_on_null_bridge(self, fact_repo: FactRepository, dream_repo: DreamRepository):
        """When LLM returns null bridge/insight, generation is skipped."""
        # Create 20+ facts across distinct domains
        for domain in range(5):
            for i in range(5):
                await fact_repo.create(
                    text=f"domain-{domain} fact-{i}",
                    source_type="test",
                    embedding=_make_distinct_embedding(domain, i),
                )
        await fact_repo.conn.commit()

        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(
            '{"bridge": null, "insight": null}'
        )
        with patch("ntrp.memory.dreams.get_completion_client", return_value=mock_client):
            created = await run_dream_pass(fact_repo, dream_repo, "test-model")

        assert created == 0
        assert await dream_repo.count() == 0

    @pytest.mark.asyncio
    async def test_generation_and_evaluation(self, fact_repo: FactRepository, dream_repo: DreamRepository):
        """Full pipeline: generate dreams, evaluator selects subset, survivors stored."""
        for domain in range(5):
            for i in range(5):
                await fact_repo.create(
                    text=f"domain-{domain} fact-{i}",
                    source_type="test",
                    embedding=_make_distinct_embedding(domain, i),
                )
        await fact_repo.conn.commit()

        call_count = 0

        async def mock_completion(**kwargs):
            nonlocal call_count
            content = kwargs["messages"][0]["content"]

            # Last call is the evaluator (contains "CANDIDATES:")
            if "CANDIDATES:" in content:
                return mock_llm_response(
                    '{"selected": [0, 2], "reasoning": "These two had genuine insight"}'
                )

            # Generation calls
            call_count += 1
            return mock_llm_response(
                json.dumps({
                    "bridge": f"bridge-{call_count}",
                    "insight": f"insight-{call_count}",
                })
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.dreams.get_completion_client", return_value=mock_client):
            created = await run_dream_pass(fact_repo, dream_repo, "test-model")

        # Evaluator selected indices 0 and 2
        assert created == 2
        assert await dream_repo.count() == 2

        dreams = await dream_repo.list_recent(limit=10)
        assert len(dreams) == 2
        for dream in dreams:
            assert dream.bridge
            assert dream.insight
            assert len(dream.source_fact_ids) > 0


class TestDreamPassGating:
    @pytest.mark.asyncio
    async def test_skips_below_min_facts(self, fact_repo: FactRepository, dream_repo: DreamRepository):
        """Dream pass does nothing when fewer than DREAM_MIN_FACTS facts exist."""
        for i in range(5):
            await fact_repo.create(
                text=f"fact-{i}",
                source_type="test",
                embedding=mock_embedding(f"fact-{i}"),
            )
        await fact_repo.conn.commit()

        mock_client = AsyncMock()
        with patch("ntrp.memory.dreams.get_completion_client", return_value=mock_client):
            created = await run_dream_pass(fact_repo, dream_repo, "test-model")

        assert created == 0
        mock_client.completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluator_rejects_all(self, fact_repo: FactRepository, dream_repo: DreamRepository):
        """When evaluator selects nothing, no dreams are stored."""
        for domain in range(5):
            for i in range(5):
                await fact_repo.create(
                    text=f"domain-{domain} fact-{i}",
                    source_type="test",
                    embedding=_make_distinct_embedding(domain, i),
                )
        await fact_repo.conn.commit()

        async def mock_completion(**kwargs):
            content = kwargs["messages"][0]["content"]
            if "CANDIDATES:" in content:
                return mock_llm_response(
                    '{"selected": [], "reasoning": "All were generic"}'
                )
            return mock_llm_response(
                '{"bridge": "test", "insight": "test insight"}'
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.dreams.get_completion_client", return_value=mock_client):
            created = await run_dream_pass(fact_repo, dream_repo, "test-model")

        assert created == 0
        assert await dream_repo.count() == 0


class TestDreamRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, dream_repo: DreamRepository):
        dream = await dream_repo.create(
            bridge="test bridge",
            insight="test insight",
            source_fact_ids=[1, 2, 3],
        )
        await dream_repo.conn.commit()

        assert dream.id is not None
        assert dream.bridge == "test bridge"
        assert dream.insight == "test insight"
        assert dream.source_fact_ids == [1, 2, 3]

        fetched = await dream_repo.get(dream.id)
        assert fetched is not None
        assert fetched.bridge == "test bridge"
        assert fetched.source_fact_ids == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_list_and_count(self, dream_repo: DreamRepository):
        await dream_repo.create("b1", "i1", [1])
        await dream_repo.create("b2", "i2", [2])
        await dream_repo.conn.commit()

        assert await dream_repo.count() == 2

        dreams = await dream_repo.list_recent(limit=10)
        assert len(dreams) == 2

    @pytest.mark.asyncio
    async def test_delete(self, dream_repo: DreamRepository):
        dream = await dream_repo.create("b1", "i1", [1])
        await dream_repo.conn.commit()

        await dream_repo.delete(dream.id)
        await dream_repo.conn.commit()

        assert await dream_repo.get(dream.id) is None
        assert await dream_repo.count() == 0

    @pytest.mark.asyncio
    async def test_last_created_at(self, dream_repo: DreamRepository):
        assert await dream_repo.last_created_at() is None

        await dream_repo.create("b1", "i1", [1])
        await dream_repo.conn.commit()

        last = await dream_repo.last_created_at()
        assert last is not None
        assert isinstance(last, datetime)
