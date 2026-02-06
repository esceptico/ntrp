"""Tests for Hindsight-style per-fact consolidation (synthesis, not decomposition)."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from ntrp.memory.consolidation import (
    ConsolidationAction,
    _execute_action,
    _format_observations,
    consolidate_fact,
)
from ntrp.memory.models import Fact, FactType, Observation
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from tests.conftest import mock_embedding


def make_fact(id: int, text: str, embedding=None) -> Fact:
    now = datetime.now()
    return Fact(
        id=id,
        text=text,
        fact_type=FactType.WORLD,
        embedding=embedding or mock_embedding(text),
        source_type="test",
        source_ref=None,
        created_at=now,
        happened_at=None,
        last_accessed_at=now,
        access_count=0,
        consolidated_at=None,
    )


def make_observation(id: int, summary: str, evidence_count: int = 1) -> Observation:
    now = datetime.now()
    return Observation(
        id=id,
        summary=summary,
        embedding=mock_embedding(summary),
        evidence_count=evidence_count,
        source_fact_ids=[1],
        history=[],
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        access_count=0,
    )


@pytest_asyncio.fixture
async def fact_repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def obs_repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


class TestFormatObservations:
    @pytest.mark.asyncio
    async def test_empty_candidates(self, fact_repo: FactRepository):
        result = await _format_observations([], fact_repo)
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_formats_observations(self, fact_repo: FactRepository):
        fact = await fact_repo.create(
            text="Source fact text",
            fact_type=FactType.WORLD,
            source_type="test",
        )
        obs = make_observation(1, "Test observation", evidence_count=1)
        obs.source_fact_ids = [fact.id]

        result = await _format_observations([(obs, 0.85)], fact_repo)
        assert '"id": 1' in result
        assert '"text": "Test observation"' in result
        assert '"evidence_count": 1' in result
        assert '"source_facts"' in result
        assert "Source fact text" in result


class TestConsolidationAction:
    def test_from_json_create(self):
        data = {"action": "create", "text": "New observation"}
        action = ConsolidationAction.from_json(data)
        assert action.type == "create"
        assert action.text == "New observation"

    def test_from_json_update(self):
        data = {"action": "update", "observation_id": 1, "text": "Updated", "reason": "refinement"}
        action = ConsolidationAction.from_json(data)
        assert action.type == "update"
        assert action.observation_id == 1
        assert action.text == "Updated"
        assert action.reason == "refinement"

    def test_from_json_skip(self):
        data = {"action": "skip", "reason": "ephemeral state"}
        action = ConsolidationAction.from_json(data)
        assert action.type == "skip"
        assert action.reason == "ephemeral state"

    def test_from_json_defaults_to_skip(self):
        action = ConsolidationAction.from_json({})
        assert action.type == "skip"


class TestExecuteAction:
    @pytest.mark.asyncio
    async def test_skip_action_returns_none(self, obs_repo: ObservationRepository):
        fact = make_fact(1, "Test fact")
        action = ConsolidationAction(type="skip", reason="ephemeral")
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result is None

    @pytest.mark.asyncio
    async def test_create_action(self, obs_repo: ObservationRepository):
        fact = make_fact(1, "Test fact")
        action = ConsolidationAction(type="create", text="Alice is a Python developer")
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result.action == "created"
        assert result.observation_id is not None

        obs = await obs_repo.get(result.observation_id)
        assert obs.summary == "Alice is a Python developer"
        assert obs.evidence_count == 1

    @pytest.mark.asyncio
    async def test_update_action(self, obs_repo: ObservationRepository, fact_repo: FactRepository):
        f1 = await fact_repo.create(text="Alice prefers Python", fact_type=FactType.WORLD, source_type="test")
        obs = await obs_repo.create(summary="Alice is a Python developer", source_fact_id=f1.id)

        fact = make_fact(2, "Alice writes clean code")
        action = ConsolidationAction(
            type="update",
            observation_id=obs.id,
            text="Alice is a Python developer who values code quality",
            reason="synthesis",
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result.action == "updated"
        assert result.observation_id == obs.id

        updated = await obs_repo.get(obs.id)
        assert updated.summary == "Alice is a Python developer who values code quality"
        assert updated.evidence_count == 2
        assert len(updated.history) == 1

    @pytest.mark.asyncio
    async def test_update_without_id_returns_none(self, obs_repo: ObservationRepository):
        fact = make_fact(1, "Test fact")
        action = ConsolidationAction(type="update", text="New text", observation_id=None)
        embed_fn = AsyncMock()

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result is None


class TestConsolidateFact:
    @pytest.mark.asyncio
    async def test_fact_without_embedding_skipped(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        fact = await fact_repo.create(
            text="No embedding",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=None,
        )
        embed_fn = AsyncMock()

        result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "skipped"
        assert result.reason == "no_embedding"

        updated = await fact_repo.get(fact.id)
        assert updated.consolidated_at is not None

    @pytest.mark.asyncio
    async def test_ephemeral_fact_skipped(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """LLM returns skip for ephemeral facts."""
        fact = await fact_repo.create(
            text="User is at coffee shop",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=mock_embedding("ephemeral"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message", (), {"content": '{"action": "skip", "reason": "ephemeral location state"}'}
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "skipped"
        assert "ephemeral" in result.reason

        updated = await fact_repo.get(fact.id)
        assert updated.consolidated_at is not None

    @pytest.mark.asyncio
    async def test_fact_creates_synthesized_observation(
        self, fact_repo: FactRepository, obs_repo: ObservationRepository
    ):
        """Fact creates a synthesized observation (higher-level than fact)."""
        fact = await fact_repo.create(
            text="Alice prefers Python",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=mock_embedding("alice python"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            # Observation is higher-level than the raw fact
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": '{"action": "create", "text": "Alice is a Python-focused developer", "reason": "synthesized preference"}'
                            },
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "created"
        assert result.observation_id is not None

        obs = await obs_repo.get(result.observation_id)
        # Observation is higher-level synthesis
        assert obs.summary == "Alice is a Python-focused developer"

        obs_count = await obs_repo.count()
        assert obs_count == 1  # Only ONE observation, not decomposed

    @pytest.mark.asyncio
    async def test_fact_updates_existing_observation(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """New fact updates existing observation instead of creating new one."""
        emb = mock_embedding("alice developer")
        f1 = await fact_repo.create(
            text="Alice prefers Python",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb,
        )
        obs = await obs_repo.create(summary="Alice is a Python-focused developer", embedding=emb, source_fact_id=f1.id)

        fact = await fact_repo.create(
            text="Alice writes clean code",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb,
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            # UPDATE existing observation with synthesis
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": f'{{"action": "update", "observation_id": {obs.id}, "text": "Alice is a Python-focused developer who values code quality", "reason": "synthesis"}}'
                            },
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "updated"
        assert result.observation_id == obs.id

        updated_obs = await obs_repo.get(obs.id)
        assert updated_obs.summary == "Alice is a Python-focused developer who values code quality"
        assert updated_obs.evidence_count == 2

        # Still only ONE observation
        obs_count = await obs_repo.count()
        assert obs_count == 1

    @pytest.mark.asyncio
    async def test_contradiction_preserved_in_history(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Contradictions are merged with history preserved."""
        emb = mock_embedding("alice employment")
        f1 = await fact_repo.create(
            text="Alice works at Google",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb,
        )
        obs = await obs_repo.create(summary="Alice works at Google", embedding=emb, source_fact_id=f1.id)

        fact = await fact_repo.create(
            text="Alice now works at Meta",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb,
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            # Contradiction updates with history
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": f'{{"action": "update", "observation_id": {obs.id}, "text": "Alice works at Meta (previously at Google)", "reason": "contradiction - job change"}}'
                            },
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "updated"

        updated_obs = await obs_repo.get(obs.id)
        assert "Meta" in updated_obs.summary
        assert "previously" in updated_obs.summary or "Google" in updated_obs.summary

    @pytest.mark.asyncio
    async def test_different_topics_create_separate_observations(
        self, fact_repo: FactRepository, obs_repo: ObservationRepository
    ):
        """Different topics for same person create separate observations."""
        emb_work = mock_embedding("alice work")
        f1 = await fact_repo.create(
            text="Alice works at Google",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb_work,
        )
        await obs_repo.create(summary="Alice works at Google", embedding=emb_work, source_fact_id=f1.id)

        # New fact about different topic (hobbies)
        emb_hobby = mock_embedding("alice hobby")
        fact = await fact_repo.create(
            text="Alice likes hiking",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb_hobby,
        )
        embed_fn = AsyncMock(return_value=emb_hobby)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            # Different topic = CREATE new observation
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": '{"action": "create", "text": "Alice enjoys outdoor activities like hiking", "reason": "new topic - hobbies"}'
                            },
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "created"

        # Now have 2 observations: work and hobbies
        obs_count = await obs_repo.count()
        assert obs_count == 2

    @pytest.mark.asyncio
    async def test_legacy_array_response_takes_first(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Legacy array response still works, takes first action."""
        fact = await fact_repo.create(
            text="Bob likes pizza",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=mock_embedding("bob pizza"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            # Legacy array format - takes first
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message", (), {"content": '[{"action": "create", "text": "Bob enjoys pizza"}]'}
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "created"


class TestAlwaysConsolidated:
    """Verify facts are always marked consolidated after processing."""

    @pytest.mark.asyncio
    async def test_skipped_fact_still_consolidated(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Even skipped facts get marked as consolidated."""
        fact = await fact_repo.create(
            text="User walked to the store",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=mock_embedding("ephemeral"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {"message": type("Message", (), {"content": '{"action": "skip", "reason": "ephemeral"}'})()},
                )()
            ]
            await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        updated = await fact_repo.get(fact.id)
        assert updated.consolidated_at is not None

    @pytest.mark.asyncio
    async def test_created_fact_consolidated(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Facts that create observations get marked consolidated."""
        fact = await fact_repo.create(
            text="Bob likes pizza",
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=mock_embedding("bob pizza"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {"message": type("Message", (), {"content": '{"action": "create", "text": "Bob enjoys pizza"}'})()},
                )()
            ]
            await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        updated = await fact_repo.get(fact.id)
        assert updated.consolidated_at is not None
