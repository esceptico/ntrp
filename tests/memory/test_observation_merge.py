"""Tests for observation merge pass: recursive pairwise deduplication."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio

from ntrp.memory.observation_merge import (
    _cosine,
    _find_top_pair,
    observation_merge_pass,
)
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.observations import ObservationRepository
from tests.conftest import TEST_EMBEDDING_DIM, mock_embedding


def _make_similar_pair(base_text: str, dim: int = TEST_EMBEDDING_DIM) -> tuple[np.ndarray, np.ndarray]:
    """Create two embeddings with very high cosine similarity (>0.95)."""
    rng = np.random.RandomState(42)
    base = mock_embedding(base_text)
    noise = rng.randn(dim) * 0.005
    similar = base + noise
    similar = similar / np.linalg.norm(similar)
    return base, similar


def _make_distinct_embeddings(n: int, dim: int = TEST_EMBEDDING_DIM) -> list[np.ndarray]:
    """Create n embeddings with low pairwise similarity."""
    embeddings = []
    for i in range(n):
        e = np.zeros(dim)
        start = (i * dim) // n
        end = start + dim // n
        e[start:end] = 1.0
        rng = np.random.RandomState(i)
        e += rng.randn(dim) * 0.05
        embeddings.append(e / np.linalg.norm(e))
    return embeddings


def mock_llm_response(content: str):
    return type(
        "Response",
        (),
        {"choices": [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]},
    )()


@pytest_asyncio.fixture
async def obs_repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


class TestCosine:
    def test_identical_vectors(self):
        v = np.array([1.0, 0.0, 0.0])
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert _cosine(a, b) == pytest.approx(0.0)


class TestFindTopPair:
    def test_finds_most_similar(self, obs_repo: ObservationRepository):
        from datetime import UTC, datetime

        from ntrp.memory.models import Observation

        now = datetime.now(UTC)
        emb_a, emb_b = _make_similar_pair("test")
        emb_c = mock_embedding("completely-different")

        obs_list = [
            Observation(
                id=1,
                summary="a",
                embedding=emb_a,
                evidence_count=1,
                source_fact_ids=[],
                history=[],
                created_at=now,
                updated_at=now,
                last_accessed_at=now,
                access_count=0,
            ),
            Observation(
                id=2,
                summary="b",
                embedding=emb_b,
                evidence_count=1,
                source_fact_ids=[],
                history=[],
                created_at=now,
                updated_at=now,
                last_accessed_at=now,
                access_count=0,
            ),
            Observation(
                id=3,
                summary="c",
                embedding=emb_c,
                evidence_count=1,
                source_fact_ids=[],
                history=[],
                created_at=now,
                updated_at=now,
                last_accessed_at=now,
                access_count=0,
            ),
        ]

        result = _find_top_pair(obs_list, set(), threshold=0.80)
        assert result is not None
        i, j, sim = result
        assert {obs_list[i].id, obs_list[j].id} == {1, 2}
        assert sim > 0.90

    def test_skips_known_pairs(self):
        from datetime import UTC, datetime

        from ntrp.memory.models import Observation

        now = datetime.now(UTC)
        emb_a, emb_b = _make_similar_pair("test")

        obs_list = [
            Observation(
                id=1,
                summary="a",
                embedding=emb_a,
                evidence_count=1,
                source_fact_ids=[],
                history=[],
                created_at=now,
                updated_at=now,
                last_accessed_at=now,
                access_count=0,
            ),
            Observation(
                id=2,
                summary="b",
                embedding=emb_b,
                evidence_count=1,
                source_fact_ids=[],
                history=[],
                created_at=now,
                updated_at=now,
                last_accessed_at=now,
                access_count=0,
            ),
        ]

        result = _find_top_pair(obs_list, {(1, 2)}, threshold=0.80)
        assert result is None

    def test_no_pairs_above_threshold(self):
        from datetime import UTC, datetime

        from ntrp.memory.models import Observation

        now = datetime.now(UTC)
        embeddings = _make_distinct_embeddings(3)

        obs_list = [
            Observation(
                id=i + 1,
                summary=f"obs-{i}",
                embedding=embeddings[i],
                evidence_count=1,
                source_fact_ids=[],
                history=[],
                created_at=now,
                updated_at=now,
                last_accessed_at=now,
                access_count=0,
            )
            for i in range(3)
        ]

        result = _find_top_pair(obs_list, set(), threshold=0.90)
        assert result is None


class TestObservationMergePass:
    @pytest.mark.asyncio
    async def test_merges_similar_observations(self, obs_repo: ObservationRepository):
        """Similar observations are merged, keeper retains combined source facts."""
        emb_a, emb_b = _make_similar_pair("user likes coffee")

        await obs_repo.create(summary="User enjoys coffee daily", embedding=emb_a, source_fact_id=1)
        await obs_repo.create(summary="User drinks coffee every morning", embedding=emb_b, source_fact_id=2)
        await obs_repo.conn.commit()

        assert await obs_repo.count() == 2

        async def mock_embed(text: str) -> np.ndarray:
            return mock_embedding(text)

        async def mock_completion(**kwargs):
            return mock_llm_response(
                json.dumps(
                    {
                        "action": "merge",
                        "text": "User enjoys coffee daily, drinking it every morning",
                    }
                )
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.observation_merge.get_completion_client", return_value=mock_client):
            merged = await observation_merge_pass(obs_repo, "test-model", mock_embed)

        assert merged == 1
        assert await obs_repo.count() == 1

        remaining = await obs_repo.list_recent(limit=10)
        assert len(remaining) == 1
        assert "coffee" in remaining[0].summary.lower()
        # Merged observation should have source facts from both
        assert len(remaining[0].source_fact_ids) == 2

    @pytest.mark.asyncio
    async def test_skips_distinct_observations(self, obs_repo: ObservationRepository):
        """LLM says skip — both observations preserved."""
        emb_a, emb_b = _make_similar_pair("test")

        await obs_repo.create(summary="User likes coffee", embedding=emb_a, source_fact_id=1)
        await obs_repo.create(summary="User likes tea", embedding=emb_b, source_fact_id=2)
        await obs_repo.conn.commit()

        async def mock_embed(text: str) -> np.ndarray:
            return mock_embedding(text)

        async def mock_completion(**kwargs):
            return mock_llm_response(
                json.dumps(
                    {
                        "action": "skip",
                        "reason": "different beverages",
                    }
                )
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.observation_merge.get_completion_client", return_value=mock_client):
            merged = await observation_merge_pass(obs_repo, "test-model", mock_embed)

        assert merged == 0
        assert await obs_repo.count() == 2

    @pytest.mark.asyncio
    async def test_no_merges_when_below_threshold(self, obs_repo: ObservationRepository):
        """Distinct embeddings below threshold — no LLM calls."""
        embeddings = _make_distinct_embeddings(3)

        for i, emb in enumerate(embeddings):
            await obs_repo.create(summary=f"observation-{i}", embedding=emb, source_fact_id=i + 1)
        await obs_repo.conn.commit()

        async def mock_embed(text: str) -> np.ndarray:
            return mock_embedding(text)

        mock_client = AsyncMock()
        with patch("ntrp.memory.observation_merge.get_completion_client", return_value=mock_client):
            merged = await observation_merge_pass(obs_repo, "test-model", mock_embed)

        assert merged == 0
        mock_client.completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_keeper_has_higher_evidence(self, obs_repo: ObservationRepository):
        """Observation with more evidence is kept."""
        emb_a, emb_b = _make_similar_pair("test")

        obs_a = await obs_repo.create(summary="obs A", embedding=emb_a, source_fact_id=1)
        await obs_repo.add_source_facts(obs_a.id, [2, 3])  # 3 facts total
        obs_b = await obs_repo.create(summary="obs B", embedding=emb_b, source_fact_id=4)  # 1 fact
        await obs_repo.conn.commit()

        async def mock_embed(text: str) -> np.ndarray:
            return mock_embedding(text)

        async def mock_completion(**kwargs):
            return mock_llm_response(
                json.dumps(
                    {
                        "action": "merge",
                        "text": "merged observation",
                    }
                )
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.observation_merge.get_completion_client", return_value=mock_client):
            merged = await observation_merge_pass(obs_repo, "test-model", mock_embed)

        assert merged == 1
        remaining = await obs_repo.list_recent(limit=10)
        assert len(remaining) == 1
        assert remaining[0].id == obs_a.id  # A kept (more evidence)

    @pytest.mark.asyncio
    async def test_recursive_merge(self, obs_repo: ObservationRepository):
        """After merging, if re-embedded result is similar to another obs, merges again."""
        # Create 3 observations where A~B and the merged result will be similar to C
        base = mock_embedding("coffee morning")
        rng = np.random.RandomState(42)
        noise1 = rng.randn(TEST_EMBEDDING_DIM) * 0.01
        noise2 = rng.randn(TEST_EMBEDDING_DIM) * 0.015
        emb_a = base.copy()
        emb_b = (base + noise1) / np.linalg.norm(base + noise1)
        emb_c = (base + noise2) / np.linalg.norm(base + noise2)

        await obs_repo.create(summary="obs A", embedding=emb_a, source_fact_id=1)
        await obs_repo.create(summary="obs B", embedding=emb_b, source_fact_id=2)
        await obs_repo.create(summary="obs C", embedding=emb_c, source_fact_id=3)
        await obs_repo.conn.commit()

        call_count = 0

        async def mock_embed(text: str) -> np.ndarray:
            # Return embedding very similar to all three
            return base.copy()

        async def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            return mock_llm_response(
                json.dumps(
                    {
                        "action": "merge",
                        "text": f"merged-{call_count}",
                    }
                )
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.observation_merge.get_completion_client", return_value=mock_client):
            merged = await observation_merge_pass(obs_repo, "test-model", mock_embed)

        assert merged == 2  # Two merges: A+B → AB, then AB+C → ABC
        assert await obs_repo.count() == 1


class TestObservationRepoMerge:
    @pytest.mark.asyncio
    async def test_merge_combines_source_facts(self, obs_repo: ObservationRepository):
        emb = mock_embedding("test")
        obs_a = await obs_repo.create(summary="obs A", embedding=emb, source_fact_id=1)
        await obs_repo.add_source_facts(obs_a.id, [2])
        obs_b = await obs_repo.create(summary="obs B", embedding=emb, source_fact_id=3)
        await obs_repo.conn.commit()

        merged = await obs_repo.merge(
            keeper_id=obs_a.id,
            removed_id=obs_b.id,
            merged_text="merged text",
            embedding=emb,
            reason="test merge",
        )
        await obs_repo.conn.commit()

        assert merged is not None
        assert merged.summary == "merged text"
        assert set(merged.source_fact_ids) == {1, 2, 3}
        assert len(merged.history) == 1
        assert "merge" in merged.history[0].reason

        # Removed observation should be gone
        assert await obs_repo.get(obs_b.id) is None
        assert await obs_repo.count() == 1

    @pytest.mark.asyncio
    async def test_delete_removes_observation(self, obs_repo: ObservationRepository):
        emb = mock_embedding("test")
        obs = await obs_repo.create(summary="to delete", embedding=emb, source_fact_id=1)
        await obs_repo.conn.commit()

        await obs_repo.delete(obs.id)
        await obs_repo.conn.commit()

        assert await obs_repo.get(obs.id) is None
        assert await obs_repo.count() == 0


class TestTemporalPassDedup:
    @pytest.mark.asyncio
    async def test_temporal_skips_duplicate_observation(self, obs_repo: ObservationRepository):
        """Temporal pass skips creating when a similar observation already exists."""
        from datetime import timedelta

        from ntrp.memory.store.facts import FactRepository
        from ntrp.memory.temporal import temporal_consolidation_pass

        fact_repo = FactRepository(obs_repo.conn)

        entity = await fact_repo.create_entity("TestEntity")
        now = datetime.now(UTC)

        # Create 5 facts with happened_at in the past (needed for SQL date comparison)
        facts = []
        for i in range(5):
            f = await fact_repo.create(
                text=f"TestEntity did thing {i}",
                source_type="test",
                embedding=mock_embedding(f"entity-fact-{i}"),
                happened_at=now - timedelta(days=10 - i),
            )
            await fact_repo.add_entity_ref(f.id, "TestEntity", entity.id)
            facts.append(f)
        await fact_repo.conn.commit()

        # Create an existing observation that will be similar to what temporal pass would create
        existing_emb = mock_embedding("TestEntity shows a pattern of doing things")
        await obs_repo.create(
            summary="TestEntity shows a pattern of doing things",
            embedding=existing_emb,
            source_fact_id=facts[0].id,
        )
        await obs_repo.conn.commit()

        async def mock_embed(text: str) -> np.ndarray:
            # Return the same embedding as the existing observation (perfect duplicate)
            return existing_emb.copy()

        async def mock_completion(**kwargs):
            return mock_llm_response(
                json.dumps(
                    {
                        "actions": [
                            {
                                "action": "create",
                                "text": "TestEntity shows a pattern of doing things repeatedly",
                                "reason": "temporal pattern",
                                "source_fact_ids": [facts[0].id, facts[1].id, facts[2].id],
                            }
                        ]
                    }
                )
            )

        mock_client = AsyncMock()
        mock_client.completion.side_effect = mock_completion
        with patch("ntrp.memory.temporal.get_completion_client", return_value=mock_client):
            created = await temporal_consolidation_pass(
                fact_repo,
                obs_repo,
                "test-model",
                mock_embed,
                days=30,
                min_facts=3,
            )

        # Should have skipped creating the duplicate
        assert created == 0
        # Only the original observation should exist
        assert await obs_repo.count() == 1
        # But source facts should have been added to existing
        existing = await obs_repo.list_recent(limit=1)
        assert facts[1].id in existing[0].source_fact_ids or facts[2].id in existing[0].source_fact_ids
