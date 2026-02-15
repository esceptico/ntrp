"""Tests for temporal observation pass (Layer 2)."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from ntrp.memory.temporal import temporal_consolidation_pass
from tests.conftest import mock_embedding


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


@pytest_asyncio.fixture
async def fact_repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def obs_repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


class TestTemporalPass:
    @pytest.mark.asyncio
    async def test_declining_sequence(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Temporal pass detects a trend across 3+ chronological facts for one entity.

        Noise facts (coffee with Sarah, finished book, grocery shopping) share the same entity
        and time window but don't form a temporal pattern.
        """
        embed_fn = AsyncMock(return_value=mock_embedding("sleep pattern"))

        # Create entity
        entity = await fact_repo.create_entity("User")

        now = datetime.now(UTC)
        base = now - timedelta(days=20)

        # Pattern facts — declining sleep
        f1 = await fact_repo.create(
            text="User slept 7.5 hours",
            source_type="test",
            embedding=mock_embedding("sleep 7.5"),
            happened_at=base,
        )
        await fact_repo.add_entity_ref(f1.id, "User", entity.id)

        f2 = await fact_repo.create(
            text="User slept 5 hours",
            source_type="test",
            embedding=mock_embedding("sleep 5"),
            happened_at=base + timedelta(days=7),
        )
        await fact_repo.add_entity_ref(f2.id, "User", entity.id)

        f3 = await fact_repo.create(
            text="User slept 4 hours, felt exhausted",
            source_type="test",
            embedding=mock_embedding("sleep 4"),
            happened_at=base + timedelta(days=14),
        )
        await fact_repo.add_entity_ref(f3.id, "User", entity.id)

        f4 = await fact_repo.create(
            text="User's resting heart rate was elevated",
            source_type="test",
            embedding=mock_embedding("heart rate"),
            happened_at=base + timedelta(days=15),
        )
        await fact_repo.add_entity_ref(f4.id, "User", entity.id)

        # Noise facts — same entity, same window, unrelated
        noise1 = await fact_repo.create(
            text="User had coffee with Sarah",
            source_type="test",
            embedding=mock_embedding("coffee sarah"),
            happened_at=base + timedelta(days=2),
        )
        await fact_repo.add_entity_ref(noise1.id, "User", entity.id)

        noise2 = await fact_repo.create(
            text="User finished reading a book",
            source_type="test",
            embedding=mock_embedding("finished book"),
            happened_at=base + timedelta(days=9),
        )
        await fact_repo.add_entity_ref(noise2.id, "User", entity.id)

        noise3 = await fact_repo.create(
            text="User went grocery shopping",
            source_type="test",
            embedding=mock_embedding("grocery"),
            happened_at=base + timedelta(days=13),
        )
        await fact_repo.add_entity_ref(noise3.id, "User", entity.id)

        await fact_repo.conn.commit()

        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(
            json.dumps({"actions": [
                {
                    "action": "create",
                    "text": "User shows declining sleep pattern over the past 3 weeks, correlating with elevated resting heart rate",
                    "reason": "sleep hours decreasing from 7.5 to 4 over 2 weeks, followed by elevated HR",
                    "source_fact_ids": [f1.id, f2.id, f3.id, f4.id],
                }
            ]})
        )
        with patch("ntrp.memory.temporal.get_completion_client", return_value=mock_client):
            created = await temporal_consolidation_pass(
                fact_repo, obs_repo, "test-model", embed_fn, days=30, min_facts=3
            )

        assert created == 1

        # Verify observation was created
        obs_list = await obs_repo.list_recent(limit=10)
        assert len(obs_list) == 1
        assert "sleep" in obs_list[0].summary.lower()
        assert "heart rate" in obs_list[0].summary.lower()

        # Verify the LLM received chronological facts
        call_args = mock_client.completion.call_args
        prompt_content = call_args[1]["messages"][0]["content"]
        assert "User slept 7.5 hours" in prompt_content
        assert "User slept 4 hours" in prompt_content
        # Noise facts are also in the input (they share the entity), but LLM ignores them
        assert "coffee with Sarah" in prompt_content

    @pytest.mark.asyncio
    async def test_skips_already_processed_entities(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Temporal pass skips entities with existing checkpoint for the window."""
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        entity = await fact_repo.create_entity("User")
        now = datetime.now(UTC)

        for i in range(4):
            f = await fact_repo.create(
                text=f"User fact {i}",
                source_type="test",
                embedding=mock_embedding(f"fact {i}"),
                happened_at=now - timedelta(days=i),
            )
            await fact_repo.add_entity_ref(f.id, "User", entity.id)

        # Insert checkpoint for today
        window_end = now.date().isoformat()
        await fact_repo.set_temporal_checkpoint(entity.id, window_end)
        await fact_repo.conn.commit()

        mock_client = AsyncMock()
        with patch("ntrp.memory.temporal.get_completion_client", return_value=mock_client):
            created = await temporal_consolidation_pass(
                fact_repo, obs_repo, "test-model", embed_fn, days=30, min_facts=3
            )

        assert created == 0
        mock_client.completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pattern_returns_skip(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """LLM returns skip when no patterns found — no observations created."""
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        entity = await fact_repo.create_entity("User")
        now = datetime.now(UTC)

        for i in range(4):
            f = await fact_repo.create(
                text=f"User did random thing {i}",
                source_type="test",
                embedding=mock_embedding(f"random {i}"),
                happened_at=now - timedelta(days=i),
            )
            await fact_repo.add_entity_ref(f.id, "User", entity.id)

        await fact_repo.conn.commit()

        mock_client = AsyncMock()
        mock_client.completion.return_value = mock_llm_response(
            '{"actions": [{"action": "skip", "reason": "no temporal patterns found"}]}'
        )
        with patch("ntrp.memory.temporal.get_completion_client", return_value=mock_client):
            created = await temporal_consolidation_pass(
                fact_repo, obs_repo, "test-model", embed_fn, days=30, min_facts=3
            )

        assert created == 0
        obs_count = await obs_repo.count()
        assert obs_count == 0

    @pytest.mark.asyncio
    async def test_ignores_entities_below_threshold(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Entities with fewer facts than min_facts are skipped entirely."""
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        entity = await fact_repo.create_entity("Alice")
        now = datetime.now(UTC)

        # Only 2 facts — below min_facts=3
        for i in range(2):
            f = await fact_repo.create(
                text=f"Alice fact {i}",
                source_type="test",
                embedding=mock_embedding(f"alice {i}"),
                happened_at=now - timedelta(days=i),
            )
            await fact_repo.add_entity_ref(f.id, "Alice", entity.id)

        await fact_repo.conn.commit()

        mock_client = AsyncMock()
        with patch("ntrp.memory.temporal.get_completion_client", return_value=mock_client):
            created = await temporal_consolidation_pass(
                fact_repo, obs_repo, "test-model", embed_fn, days=30, min_facts=3
            )

        assert created == 0
        mock_client.completion.assert_not_called()
