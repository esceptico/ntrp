import pytest
import pytest_asyncio

from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from tests.conftest import mock_embedding


@pytest_asyncio.fixture
async def fact_repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


class TestObservationCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo: ObservationRepository):
        obs = await repo.create(
            summary="Test observation",
            embedding=mock_embedding("test"),
        )

        assert obs.id is not None
        assert obs.summary == "Test observation"
        assert obs.source_fact_ids == []
        assert obs.history == []

        retrieved = await repo.get(obs.id)
        assert retrieved is not None
        assert retrieved.summary == "Test observation"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo: ObservationRepository):
        result = await repo.get(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_with_source_fact_id(self, repo: ObservationRepository, fact_repo: FactRepository):
        f1 = await fact_repo.create(text="Fact 1", source_type="test")

        obs = await repo.create(
            summary="Observation from fact",
            source_fact_id=f1.id,
        )

        assert obs.evidence_count == 1
        assert obs.source_fact_ids == [f1.id]

        fact_ids = await repo.get_fact_ids(obs.id)
        assert fact_ids == [f1.id]

    @pytest.mark.asyncio
    async def test_list_recent(self, repo: ObservationRepository):
        await repo.create(summary="Obs 1")
        await repo.create(summary="Obs 2")

        observations = await repo.list_recent(limit=10)
        assert len(observations) >= 2

    @pytest.mark.asyncio
    async def test_count(self, repo: ObservationRepository):
        initial = await repo.count()
        await repo.create(summary="New obs")
        assert await repo.count() == initial + 1


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_summary(self, repo: ObservationRepository):
        obs = await repo.create(summary="Original")

        updated = await repo.update(
            observation_id=obs.id,
            summary="Updated",
        )

        assert updated is not None
        assert updated.summary == "Updated"

    @pytest.mark.asyncio
    async def test_update_adds_fact_and_history(self, repo: ObservationRepository, fact_repo: FactRepository):
        f1 = await fact_repo.create(text="Fact 1", source_type="test")
        f2 = await fact_repo.create(text="Fact 2", source_type="test")

        obs = await repo.create(summary="Obs", source_fact_id=f1.id)
        assert obs.evidence_count == 1

        updated = await repo.update(
            observation_id=obs.id,
            summary="Obs updated",
            new_fact_id=f2.id,
            reason="Added new evidence",
        )

        assert updated.evidence_count == 2
        assert set(updated.source_fact_ids) == {f1.id, f2.id}
        assert len(updated.history) == 1
        assert updated.history[0].previous_text == "Obs"
        assert updated.history[0].reason == "Added new evidence"
        assert updated.history[0].source_fact_id == f2.id

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, repo: ObservationRepository):
        result = await repo.update(observation_id=99999, summary="No")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_does_not_duplicate_fact_ids(self, repo: ObservationRepository, fact_repo: FactRepository):
        f1 = await fact_repo.create(text="Fact 1", source_type="test")

        obs = await repo.create(summary="Obs", source_fact_id=f1.id)

        # Update with same fact ID
        updated = await repo.update(
            observation_id=obs.id,
            summary="Obs updated",
            new_fact_id=f1.id,
        )

        # Should not duplicate
        assert updated.evidence_count == 1
        assert updated.source_fact_ids == [f1.id]


class TestReinforce:
    @pytest.mark.asyncio
    async def test_reinforce_updates_access(self, repo: ObservationRepository):
        obs = await repo.create(summary="Reinforce test")
        assert obs.access_count == 0

        await repo.reinforce([obs.id])

        updated = await repo.get(obs.id)
        assert updated.access_count == 1

    @pytest.mark.asyncio
    async def test_reinforce_empty_list(self, repo: ObservationRepository):
        await repo.reinforce([])

    @pytest.mark.asyncio
    async def test_reinforce_multiple(self, repo: ObservationRepository):
        o1 = await repo.create(summary="Obs 1")
        o2 = await repo.create(summary="Obs 2")

        await repo.reinforce([o1.id, o2.id])

        assert (await repo.get(o1.id)).access_count == 1
        assert (await repo.get(o2.id)).access_count == 1


class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_search_vector(self, repo: ObservationRepository):
        emb = mock_embedding("morning routine")
        await repo.create(
            summary="Prefers morning meetings",
            embedding=emb,
        )

        results = await repo.search_vector(emb, limit=5)
        assert len(results) >= 1
        assert any("morning" in o.summary for o, _ in results)
