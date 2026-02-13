"""Tests for Hindsight-style per-fact consolidation (synthesis, not decomposition)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from ntrp.memory.consolidation import (
    ConsolidationAction,
    ConsolidationResponse,
    ConsolidationResult,
    _execute_action,
    _format_observations,
    apply_consolidation,
    get_consolidation_decisions,
)
from ntrp.memory.models import Fact, HistoryEntry, Observation
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from tests.conftest import mock_embedding


def make_fact(id: int, text: str, embedding=None, happened_at: datetime | None = None) -> Fact:
    now = datetime.now()
    return Fact(
        id=id,
        text=text,
        embedding=embedding or mock_embedding(text),
        source_type="test",
        source_ref=None,
        created_at=now,
        happened_at=happened_at,
        last_accessed_at=now,
        access_count=0,
        consolidated_at=None,
    )


def make_observation(
    id: int,
    summary: str,
    evidence_count: int = 1,
    source_fact_ids: list[int] | None = None,
    history: list[HistoryEntry] | None = None,
) -> Observation:
    now = datetime.now()
    return Observation(
        id=id,
        summary=summary,
        embedding=mock_embedding(summary),
        evidence_count=evidence_count,
        source_fact_ids=source_fact_ids or [1],
        history=history or [],
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        access_count=0,
    )


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


async def consolidate_fact(fact, fact_repo, obs_repo, model, embed_fn):
    """Test helper that combines the multi-action consolidation API."""
    actions = await get_consolidation_decisions(fact, obs_repo, fact_repo, model)
    results = []
    for action in actions:
        result = await apply_consolidation(fact, action, fact_repo, obs_repo, embed_fn)
        results.append(result)
    await fact_repo.mark_consolidated(fact.id)
    return results[-1] if results else ConsolidationResult(action="skipped", reason="no_actions")


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
            source_type="test",
        )
        obs = make_observation(1, "Test observation", evidence_count=1)

        obs = obs.model_copy(update={"source_fact_ids": [fact.id]})

        result = await _format_observations([(obs, 0.85)], fact_repo)
        assert '"id": 1' in result
        assert '"text": "Test observation"' in result
        assert '"evidence_count": 1' in result
        assert '"source_facts"' in result
        assert "Source fact text" in result


class TestConsolidationSchema:
    def test_parse_create(self):
        parsed = ConsolidationAction.model_validate_json('{"action": "create", "text": "New observation"}')
        assert parsed.action == "create"
        assert parsed.text == "New observation"

    def test_parse_update(self):
        parsed = ConsolidationAction.model_validate_json(
            '{"action": "update", "observation_id": 1, "text": "Updated", "reason": "refinement"}'
        )
        assert parsed.action == "update"
        assert parsed.observation_id == 1
        assert parsed.text == "Updated"
        assert parsed.reason == "refinement"

    def test_parse_skip(self):
        parsed = ConsolidationAction.model_validate_json('{"action": "skip", "reason": "ephemeral state"}')
        assert parsed.action == "skip"
        assert parsed.reason == "ephemeral state"

    def test_invalid_action_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            ConsolidationAction.model_validate_json('{"action": "invalid"}')

    def test_parse_response_wrapper(self):
        parsed = ConsolidationResponse.model_validate_json(
            '{"actions": [{"action": "create", "text": "obs"}, {"action": "skip", "reason": "ephemeral"}]}'
        )
        assert len(parsed.actions) == 2
        assert parsed.actions[0].action == "create"
        assert parsed.actions[1].action == "skip"


class TestExecuteAction:
    @pytest.mark.asyncio
    async def test_skip_action_returns_none(self, obs_repo: ObservationRepository):
        fact = make_fact(1, "Test fact")
        action = ConsolidationAction(action="skip", reason="ephemeral")
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result is None

    @pytest.mark.asyncio
    async def test_create_action(self, obs_repo: ObservationRepository):
        fact = make_fact(1, "Test fact")
        action = ConsolidationAction(action="create", text="Alice is a Python developer")
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result.action == "created"
        assert result.observation_id is not None

        obs = await obs_repo.get(result.observation_id)
        assert obs.summary == "Alice is a Python developer"
        assert obs.evidence_count == 1

    @pytest.mark.asyncio
    async def test_update_action(self, obs_repo: ObservationRepository, fact_repo: FactRepository):
        f1 = await fact_repo.create(text="Alice prefers Python", source_type="test")
        obs = await obs_repo.create(summary="Alice is a Python developer", source_fact_id=f1.id)

        fact = make_fact(2, "Alice writes clean code")
        action = ConsolidationAction(
            action="update",
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
        action = ConsolidationAction(action="update", text="New text", observation_id=None)
        embed_fn = AsyncMock()

        result = await _execute_action(action, fact, obs_repo, embed_fn)

        assert result is None


class TestConsolidateFact:
    @pytest.mark.asyncio
    async def test_fact_without_embedding_skipped(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        fact = await fact_repo.create(
            text="No embedding",
            source_type="test",
            embedding=None,
        )
        embed_fn = AsyncMock()

        result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "skipped"

        updated = await fact_repo.get(fact.id)
        assert updated.consolidated_at is not None

    @pytest.mark.asyncio
    async def test_ephemeral_fact_skipped(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """LLM returns skip for ephemeral facts."""
        fact = await fact_repo.create(
            text="User is at coffee shop",
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
                            "Message", (), {"content": '{"actions": [{"action": "skip", "reason": "ephemeral location state"}]}'}
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
            source_type="test",
            embedding=mock_embedding("alice python"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": '{"actions": [{"action": "create", "text": "Alice is a Python-focused developer", "reason": "synthesized preference"}]}'
                            },
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "created"
        assert result.observation_id is not None

        obs = await obs_repo.get(result.observation_id)
        assert obs.summary == "Alice is a Python-focused developer"

        obs_count = await obs_repo.count()
        assert obs_count == 1

    @pytest.mark.asyncio
    async def test_fact_updates_existing_observation(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """New fact updates existing observation instead of creating new one."""
        emb = mock_embedding("alice developer")
        f1 = await fact_repo.create(
            text="Alice prefers Python",
            source_type="test",
            embedding=emb,
        )
        obs = await obs_repo.create(summary="Alice is a Python-focused developer", embedding=emb, source_fact_id=f1.id)

        fact = await fact_repo.create(
            text="Alice writes clean code",
            source_type="test",
            embedding=emb,
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": f'{{"actions": [{{"action": "update", "observation_id": {obs.id}, "text": "Alice is a Python-focused developer who values code quality", "reason": "synthesis"}}]}}'
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

        obs_count = await obs_repo.count()
        assert obs_count == 1

    @pytest.mark.asyncio
    async def test_contradiction_preserved_in_history(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Contradictions are merged with history preserved."""
        emb = mock_embedding("alice employment")
        f1 = await fact_repo.create(
            text="Alice works at Google",
            source_type="test",
            embedding=emb,
        )
        obs = await obs_repo.create(summary="Alice works at Google", embedding=emb, source_fact_id=f1.id)

        fact = await fact_repo.create(
            text="Alice now works at Meta",
            source_type="test",
            embedding=emb,
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": f'{{"actions": [{{"action": "update", "observation_id": {obs.id}, "text": "Alice works at Meta (previously at Google)", "reason": "contradiction - job change"}}]}}'
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
            source_type="test",
            embedding=emb_work,
        )
        await obs_repo.create(summary="Alice works at Google", embedding=emb_work, source_fact_id=f1.id)

        emb_hobby = mock_embedding("alice hobby")
        fact = await fact_repo.create(
            text="Alice likes hiking",
            source_type="test",
            embedding=emb_hobby,
        )
        embed_fn = AsyncMock(return_value=emb_hobby)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": '{"actions": [{"action": "create", "text": "Alice enjoys outdoor activities like hiking", "reason": "new topic - hobbies"}]}'
                            },
                        )()
                    },
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "created"

        obs_count = await obs_repo.count()
        assert obs_count == 2

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_none(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Invalid JSON from LLM results in skipped consolidation."""
        fact = await fact_repo.create(
            text="Bob likes pizza",
            source_type="test",
            embedding=mock_embedding("bob pizza"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {"message": type("Message", (), {"content": "not valid json at all"})()},
                )()
            ]
            result = await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "skipped"


class TestAlwaysConsolidated:
    """Verify facts are always marked consolidated after processing."""

    @pytest.mark.asyncio
    async def test_skipped_fact_still_consolidated(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Even skipped facts get marked as consolidated."""
        fact = await fact_repo.create(
            text="User walked to the store",
            source_type="test",
            embedding=mock_embedding("ephemeral"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {"message": type("Message", (), {"content": '{"actions": [{"action": "skip", "reason": "ephemeral"}]}'})()},
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
            source_type="test",
            embedding=mock_embedding("bob pizza"),
        )
        embed_fn = AsyncMock(return_value=mock_embedding("test"))

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value.choices = [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message", (), {"content": '{"actions": [{"action": "create", "text": "Bob enjoys pizza"}]}'}
                        )()
                    },
                )()
            ]
            await consolidate_fact(fact, fact_repo, obs_repo, "test-model", embed_fn)

        updated = await fact_repo.get(fact.id)
        assert updated.consolidated_at is not None


class TestTemporalConsolidation:
    """Tests for temporally-aware consolidation (Layer 1)."""

    @pytest.mark.asyncio
    async def test_simple_transition(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Consolidation detects supersession and produces an evolution narrative.

        Noise facts (all-hands presentation, Bob joining mobile) share the entity or timing
        but should NOT trigger transition detection.
        """
        emb = mock_embedding("alice team lead")

        # Source fact for the existing observation
        jan_10 = datetime(2026, 1, 10, tzinfo=UTC)
        f1 = await fact_repo.create(
            text="Alice is leading the mobile team",
            source_type="test",
            embedding=emb,
            happened_at=jan_10,
        )
        obs = await obs_repo.create(
            summary="Alice is the mobile app lead",
            embedding=emb,
            source_fact_id=f1.id,
        )

        # Noise facts
        await fact_repo.create(
            text="Alice presented at the all-hands meeting",
            source_type="test",
            embedding=mock_embedding("alice all-hands"),
            happened_at=datetime(2026, 2, 15, tzinfo=UTC),
        )
        await fact_repo.create(
            text="Bob joined the mobile team",
            source_type="test",
            embedding=mock_embedding("bob mobile"),
            happened_at=datetime(2026, 3, 1, tzinfo=UTC),
        )

        # New fact: Alice transitions to backend
        mar_5 = datetime(2026, 3, 5, tzinfo=UTC)
        new_fact = await fact_repo.create(
            text="Alice is now leading the backend rewrite",
            source_type="test",
            embedding=emb,
            happened_at=mar_5,
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value = mock_llm_response(
                f'{{"actions": [{{"action": "update", "observation_id": {obs.id}, '
                f'"text": "Alice leads the backend rewrite (previously mobile, transitioned ~March 2026)", '
                f'"reason": "role transition — newer fact supersedes mobile leadership"}}]}}'
            )
            result = await consolidate_fact(new_fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "updated"

        updated_obs = await obs_repo.get(obs.id)
        assert "backend" in updated_obs.summary
        assert "mobile" in updated_obs.summary or "previously" in updated_obs.summary
        assert len(updated_obs.history) == 1
        assert updated_obs.history[0].previous_text == "Alice is the mobile app lead"

        # Verify the LLM received temporal context — happened_at in source facts
        call_args = mock_llm.call_args
        prompt_content = call_args[1]["messages"][0]["content"]
        assert "happened_at" in prompt_content
        assert jan_10.isoformat() in prompt_content

    @pytest.mark.asyncio
    async def test_addition_not_contradiction(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Consolidation distinguishes expansion from supersession.

        Noise: "Alice stopped using Flutter" looks like contradiction but is about a tool, not role.
        "The backend team is hiring" is unrelated context.
        """
        emb = mock_embedding("alice development")

        jan_10 = datetime(2026, 1, 10, tzinfo=UTC)
        f1 = await fact_repo.create(
            text="Alice is building the iOS app",
            source_type="test",
            embedding=emb,
            happened_at=jan_10,
        )
        obs = await obs_repo.create(
            summary="Alice is focused on mobile development",
            embedding=emb,
            source_fact_id=f1.id,
        )

        # Noise
        await fact_repo.create(
            text="Alice stopped using Flutter",
            source_type="test",
            embedding=mock_embedding("alice flutter"),
            happened_at=datetime(2026, 2, 18, tzinfo=UTC),
        )
        await fact_repo.create(
            text="The backend team is hiring",
            source_type="test",
            embedding=mock_embedding("backend hiring"),
            happened_at=datetime(2026, 2, 22, tzinfo=UTC),
        )

        new_fact = await fact_repo.create(
            text="Alice is also helping with the backend API",
            source_type="test",
            embedding=emb,
            happened_at=datetime(2026, 2, 20, tzinfo=UTC),
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value = mock_llm_response(
                f'{{"actions": [{{"action": "update", "observation_id": {obs.id}, '
                f'"text": "Alice works across mobile and backend development", '
                f'"reason": "expanded scope — addition, not replacement"}}]}}'
            )
            result = await consolidate_fact(new_fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "updated"

        updated_obs = await obs_repo.get(obs.id)
        # Should NOT contain transition language
        assert "previously" not in updated_obs.summary.lower()
        assert "transitioned" not in updated_obs.summary.lower()
        # Should reflect both areas
        assert "mobile" in updated_obs.summary.lower()
        assert "backend" in updated_obs.summary.lower()

    @pytest.mark.asyncio
    async def test_partial_update(self, fact_repo: FactRepository, obs_repo: ObservationRepository):
        """Only the contradicted part of an observation changes; unrelated parts survive.

        Noise: mentee promotion and mobile v2.0 are related context but shouldn't merge.
        """
        emb = mock_embedding("alice leadership mentoring")

        jan = datetime(2026, 1, 15, tzinfo=UTC)
        feb = datetime(2026, 2, 10, tzinfo=UTC)

        f1 = await fact_repo.create(
            text="Alice runs mobile team",
            source_type="test",
            embedding=emb,
            happened_at=jan,
        )
        f2 = await fact_repo.create(
            text="Alice mentors two juniors",
            source_type="test",
            embedding=emb,
            happened_at=feb,
        )
        obs = await obs_repo.create(
            summary="Alice leads mobile and mentors junior engineers",
            embedding=emb,
            source_fact_id=f1.id,
        )
        # Add f2 as source
        await obs_repo.update(
            observation_id=obs.id,
            summary=obs.summary,
            embedding=emb,
            new_fact_id=f2.id,
            reason="added mentoring evidence",
        )

        # Noise
        await fact_repo.create(
            text="Alice's mentee got promoted",
            source_type="test",
            embedding=mock_embedding("mentee promoted"),
            happened_at=datetime(2026, 3, 15, tzinfo=UTC),
        )
        await fact_repo.create(
            text="Mobile team shipped v2.0",
            source_type="test",
            embedding=mock_embedding("mobile v2"),
            happened_at=datetime(2026, 3, 20, tzinfo=UTC),
        )

        new_fact = await fact_repo.create(
            text="Alice transitioned off the mobile team",
            source_type="test",
            embedding=emb,
            happened_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
        embed_fn = AsyncMock(return_value=emb)

        with patch("ntrp.memory.consolidation.acompletion") as mock_llm:
            mock_llm.return_value = mock_llm_response(
                f'{{"actions": [{{"action": "update", "observation_id": {obs.id}, '
                f'"text": "Alice mentors junior engineers (previously also led mobile, left ~April 2026)", '
                f'"reason": "partial update — mobile role ended but mentoring continues"}}]}}'
            )
            result = await consolidate_fact(new_fact, fact_repo, obs_repo, "test-model", embed_fn)

        assert result.action == "updated"

        updated_obs = await obs_repo.get(obs.id)
        # Mentoring preserved
        assert "mentor" in updated_obs.summary.lower()
        # Mobile transition captured
        assert "mobile" in updated_obs.summary.lower()
        assert "previously" in updated_obs.summary.lower() or "left" in updated_obs.summary.lower()
        # History records the change
        assert len(updated_obs.history) >= 2  # one from f2 addition, one from this update
