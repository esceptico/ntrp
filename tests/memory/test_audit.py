from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from ntrp.memory.audit import memory_audit, observation_prune_dry_run
from ntrp.memory.models import FactKind, SourceType
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.dreams import DreamRepository
from ntrp.memory.store.facts import FactRepository
from ntrp.memory.store.observations import ObservationRepository


@pytest_asyncio.fixture
async def fact_repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


@pytest_asyncio.fixture
async def obs_repo(db: GraphDatabase) -> ObservationRepository:
    return ObservationRepository(db.conn)


@pytest_asyncio.fixture
async def dream_repo(db: GraphDatabase) -> DreamRepository:
    return DreamRepository(db.conn)


class TestMemoryAudit:
    @pytest.mark.asyncio
    async def test_reports_core_counts(
        self,
        db: GraphDatabase,
        fact_repo: FactRepository,
        obs_repo: ObservationRepository,
    ):
        active_fact = await fact_repo.create(
            "User prefers raw SQL",
            SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            salience=1,
        )
        archived_fact = await fact_repo.create("Old chat fact", SourceType.CHAT)
        await fact_repo.mark_consolidated(active_fact.id)
        await fact_repo.archive_batch([archived_fact.id])

        await obs_repo.create("User has a stable database preference", source_fact_id=active_fact.id)
        archived_obs = await obs_repo.create("Archived observation")
        await obs_repo.archive_batch([archived_obs.id])

        audit = await memory_audit(db.conn)

        assert audit["facts"]["total"] == 2
        assert audit["facts"]["active"] == 1
        assert audit["facts"]["archived"] == 1
        assert audit["facts"]["unconsolidated"] == 0
        assert audit["facts"]["zero_access"] == 1

        assert audit["observations"]["total"] == 2
        assert audit["observations"]["active"] == 1
        assert audit["observations"]["archived"] == 1
        assert audit["observations"]["zero_access"] == 1
        assert audit["observation_source_distribution"][0]["sources"] == 1

        by_source = {row["source_type"]: row for row in audit["facts_by_source"]}
        assert by_source["explicit"]["active"] == 1
        assert by_source["chat"]["active"] == 0

        by_kind = {row["kind"]: row for row in audit["facts_by_kind"]}
        assert by_kind["preference"]["active"] == 1
        assert by_kind["preference"]["pinned_active"] == 0

    @pytest.mark.asyncio
    async def test_reports_generated_memory_provenance(
        self,
        db: GraphDatabase,
        fact_repo: FactRepository,
        obs_repo: ObservationRepository,
        dream_repo: DreamRepository,
    ):
        active_fact = await fact_repo.create("A supported fact", SourceType.EXPLICIT)
        archived_fact = await fact_repo.create("An old supporting fact", SourceType.CHAT)
        await fact_repo.archive_batch([archived_fact.id])

        await obs_repo.create("Observation with live support", source_fact_id=active_fact.id)
        await obs_repo.create("Observation without support")
        await obs_repo.create("Observation with archived support", source_fact_id=archived_fact.id)
        await obs_repo.create("Observation with missing support", source_fact_id=999_999)

        await dream_repo.create("Bridge", "Insight", [active_fact.id, archived_fact.id, 999_999])
        await dream_repo.create("No source bridge", "No source insight", [])

        audit = await memory_audit(db.conn)

        observation_provenance = audit["provenance"]["observations"]
        assert observation_provenance["records"] == 4
        assert observation_provenance["records_without_sources"] == 1
        assert observation_provenance["source_refs"] == 3
        assert observation_provenance["missing_source_refs"] == 1
        assert observation_provenance["records_with_missing_sources"] == 1
        assert observation_provenance["archived_source_refs"] == 1
        assert observation_provenance["records_with_archived_sources"] == 1

        dream_provenance = audit["provenance"]["dreams"]
        assert dream_provenance["records"] == 2
        assert dream_provenance["records_without_sources"] == 1
        assert dream_provenance["source_refs"] == 3
        assert dream_provenance["missing_source_refs"] == 1
        assert dream_provenance["archived_source_refs"] == 1


class TestObservationPruneDryRun:
    @pytest.mark.asyncio
    async def test_returns_only_old_zero_access_low_support_candidates(
        self,
        db: GraphDatabase,
        obs_repo: ObservationRepository,
    ):
        now = datetime(2026, 5, 1, tzinfo=UTC)
        old = (now - timedelta(days=31)).isoformat()
        recent = (now - timedelta(days=3)).isoformat()

        candidate = await obs_repo.create("Old unused low-support pattern", source_fact_id=1)
        recent_obs = await obs_repo.create("Recent unused pattern", source_fact_id=2)
        accessed = await obs_repo.create("Old accessed pattern", source_fact_id=3)
        high_support = await obs_repo.create("Old high-support pattern", source_fact_id=4)
        await obs_repo.add_source_facts(high_support.id, [5, 6, 7, 8, 9])
        await obs_repo.reinforce([accessed.id])

        for obs_id in (candidate.id, accessed.id, high_support.id):
            await db.conn.execute(
                "UPDATE observations SET created_at = ?, updated_at = ? WHERE id = ?",
                (old, old, obs_id),
            )
        await db.conn.execute(
            "UPDATE observations SET created_at = ?, updated_at = ? WHERE id = ?",
            (recent, recent, recent_obs.id),
        )

        result = await observation_prune_dry_run(
            db.conn,
            older_than_days=30,
            max_sources=5,
            limit=10,
            now=now,
        )

        ids = [row["id"] for row in result["candidates"]]
        assert ids == [candidate.id]
        assert result["summary"]["total"] == 1
        assert result["candidates"][0]["reason"] == "zero_access_low_support"

    @pytest.mark.asyncio
    async def test_limit_applies_after_total_count(self, db: GraphDatabase, obs_repo: ObservationRepository):
        now = datetime(2026, 5, 1, tzinfo=UTC)
        old = (now - timedelta(days=31)).isoformat()

        for index in range(3):
            obs = await obs_repo.create(f"Candidate {index}", source_fact_id=index + 1)
            await db.conn.execute(
                "UPDATE observations SET created_at = ?, updated_at = ? WHERE id = ?",
                (old, old, obs.id),
            )

        result = await observation_prune_dry_run(
            db.conn,
            older_than_days=30,
            max_sources=5,
            limit=2,
            now=now,
        )

        assert result["summary"]["total"] == 3
        assert len(result["candidates"]) == 2
