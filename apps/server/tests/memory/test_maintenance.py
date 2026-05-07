import pytest
import pytest_asyncio

from ntrp.memory.maintenance import duplicate_memory_candidates
from ntrp.memory.models import SourceType
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository
from tests.conftest import mock_embedding


@pytest_asyncio.fixture
async def fact_repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def obs_repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


@pytest.mark.asyncio
async def test_duplicate_memory_candidates_are_review_only(
    fact_repo: FactRepository,
    obs_repo: ObservationRepository,
):
    shared_fact_embedding = mock_embedding("concise reports")
    fact_a = await fact_repo.create("User likes concise reports", SourceType.EXPLICIT, embedding=shared_fact_embedding)
    fact_b = await fact_repo.create(
        "User prefers concise reports",
        SourceType.EXPLICIT,
        embedding=shared_fact_embedding,
    )
    await fact_repo.create(
        "User likes long-form strategy docs",
        SourceType.EXPLICIT,
        embedding=mock_embedding("different fact"),
    )

    shared_observation_embedding = mock_embedding("stable concise preference")
    obs_a = await obs_repo.create(
        "User tends to prefer concise reports",
        embedding=shared_observation_embedding,
        source_fact_id=fact_a.id,
    )
    obs_b = await obs_repo.create(
        "User has a stable preference for concise reporting",
        embedding=shared_observation_embedding,
        source_fact_id=fact_b.id,
    )
    await obs_repo.create(
        "User is exploring personal context OS design",
        embedding=mock_embedding("different observation"),
        source_fact_id=fact_a.id,
    )
    await fact_repo.conn.commit()

    candidates = await duplicate_memory_candidates(fact_repo, obs_repo, limit=10)

    assert candidates["facts"] == [
        {
            "ids": [fact_a.id, fact_b.id],
            "score": 1.0,
            "left": "User likes concise reports",
            "right": "User prefers concise reports",
        }
    ]
    assert candidates["observations"] == [
        {
            "ids": [obs_a.id, obs_b.id],
            "score": 1.0,
            "left": "User tends to prefer concise reports",
            "right": "User has a stable preference for concise reporting",
        }
    ]
    assert await fact_repo.get(fact_a.id) is not None
    assert await fact_repo.get(fact_b.id) is not None
    assert await obs_repo.get(obs_a.id) is not None
    assert await obs_repo.get(obs_b.id) is not None
