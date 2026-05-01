from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from ntrp.memory.models import FactKind, FactLifetime, SourceType
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.facts import FactRepository
from tests.conftest import mock_embedding


@pytest_asyncio.fixture
async def repo(db: GraphDatabase) -> FactRepository:
    return FactRepository(db.conn)


class TestFactCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo: FactRepository):
        fact = await repo.create(
            text="Test fact",
            source_type=SourceType.EXPLICIT,
            embedding=mock_embedding("test"),
        )

        assert fact.id is not None
        assert fact.text == "Test fact"

        retrieved = await repo.get(fact.id)
        assert retrieved is not None
        assert retrieved.text == "Test fact"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo: FactRepository):
        result = await repo.get(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, repo: FactRepository):
        fact = await repo.create(
            text="To delete",
            source_type=SourceType.EXPLICIT,
        )

        await repo.delete(fact.id)
        assert await repo.get(fact.id) is None

    @pytest.mark.asyncio
    async def test_list_recent(self, repo: FactRepository):
        await repo.create(text="Fact 1", source_type=SourceType.EXPLICIT)
        await repo.create(text="Fact 2", source_type=SourceType.EXPLICIT)

        facts = await repo.list_recent(limit=10)
        assert len(facts) >= 2

    @pytest.mark.asyncio
    async def test_count(self, repo: FactRepository):
        initial = await repo.count()
        await repo.create(text="New fact", source_type=SourceType.EXPLICIT)
        assert await repo.count() == initial + 1

    @pytest.mark.asyncio
    async def test_create_typed_fact(self, repo: FactRepository):
        expires_at = datetime.now(UTC) + timedelta(days=7)
        fact = await repo.create(
            text="User prefers direct SQL",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            salience=2,
            confidence=0.9,
            expires_at=expires_at,
        )

        retrieved = await repo.get(fact.id)
        assert retrieved.kind == FactKind.PREFERENCE
        assert retrieved.salience == 2
        assert retrieved.confidence == 0.9
        assert retrieved.expires_at == expires_at
        assert retrieved.pinned_at is None
        assert retrieved.superseded_by_fact_id is None

    @pytest.mark.asyncio
    async def test_list_profile_facts(self, repo: FactRepository):
        now = datetime.now(UTC)
        visible = await repo.create(
            text="User prefers concise answers",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            salience=1,
        )
        pinned = await repo.create(
            text="User is Timur",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.IDENTITY,
            salience=0,
            pinned_at=now,
        )
        note = await repo.create(
            text="Regular note",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.NOTE,
            salience=2,
        )
        expired = await repo.create(
            text="Expired preference",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            expires_at=now - timedelta(days=1),
        )
        archived = await repo.create(
            text="Archived preference",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        replacement = await repo.create(
            text="Replacement preference",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        superseded = await repo.create(
            text="Superseded preference",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            superseded_by_fact_id=replacement.id,
        )
        await repo.archive_batch([archived.id])

        facts = await repo.list_profile_facts((FactKind.IDENTITY, FactKind.PREFERENCE), limit=10)

        ids = [fact.id for fact in facts]
        assert ids[:2] == [pinned.id, visible.id]
        assert note.id not in ids
        assert expired.id not in ids
        assert archived.id not in ids
        assert superseded.id not in ids

    @pytest.mark.asyncio
    async def test_list_supersession_candidates_for_same_entity_and_kind(self, repo: FactRepository):
        entity = await repo.create_entity("User")
        older = await repo.create(
            text="User prefers concise answers",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        newer = await repo.create(
            text="User prefers detailed answers",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        different_kind = await repo.create(
            text="User works at Anthropic",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.IDENTITY,
        )
        note = await repo.create(
            text="User prefers manual review for memory",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.NOTE,
        )
        other_entity = await repo.create(
            text="Alice prefers concise answers",
            source_type=SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )

        await repo.add_entity_ref(older.id, "User", entity.id)
        await repo.add_entity_ref(newer.id, "User", entity.id)
        await repo.add_entity_ref(different_kind.id, "User", entity.id)
        await repo.add_entity_ref(note.id, "User", entity.id)
        await repo.add_entity_ref(other_entity.id, "Alice")

        rows = await repo.list_supersession_candidates(
            (FactKind.IDENTITY, FactKind.PREFERENCE, FactKind.CONSTRAINT),
            limit=10,
        )

        assert rows == [
            {
                "older_fact_id": older.id,
                "newer_fact_id": newer.id,
                "kind": FactKind.PREFERENCE,
                "entity_name": "User",
                "older_created_at": older.created_at.isoformat(),
                "newer_created_at": newer.created_at.isoformat(),
            }
        ]

    @pytest.mark.asyncio
    async def test_list_filtered_facts(self, repo: FactRepository):
        now = datetime.now(UTC)
        user = await repo.create_entity("User")
        active = await repo.create(
            "User prefers raw SQL",
            SourceType.CHAT,
            kind=FactKind.PREFERENCE,
            salience=1,
        )
        pinned = await repo.create(
            "User is Timur",
            SourceType.EXPLICIT,
            kind=FactKind.IDENTITY,
            pinned_at=now,
        )
        archived = await repo.create("Archived note", SourceType.EXPLICIT)
        replacement = await repo.create("Replacement preference", SourceType.EXPLICIT, kind=FactKind.PREFERENCE)
        superseded = await repo.create(
            "Old preference",
            SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            superseded_by_fact_id=replacement.id,
        )
        expired = await repo.create(
            "Expired temporary state",
            SourceType.EXPLICIT,
            lifetime=FactLifetime.TEMPORARY,
            expires_at=now - timedelta(days=1),
        )
        temporary = await repo.create(
            "Current temporary state",
            SourceType.EXPLICIT,
            lifetime=FactLifetime.TEMPORARY,
            expires_at=now + timedelta(days=1),
        )
        await repo.add_entity_ref(active.id, "User", user.id)
        await repo.archive_batch([archived.id])

        preference_facts, preference_total = await repo.list_filtered(kind=FactKind.PREFERENCE)
        preference_ids = {fact.id for fact in preference_facts}
        assert preference_total == 2
        assert active.id in preference_ids
        assert replacement.id in preference_ids
        assert superseded.id not in preference_ids

        chat_facts, _ = await repo.list_filtered(source_type=SourceType.CHAT)
        assert [fact.id for fact in chat_facts] == [active.id]

        entity_facts, _ = await repo.list_filtered(entity="user")
        assert [fact.id for fact in entity_facts] == [active.id]

        archived_facts, _ = await repo.list_filtered(status="archived")
        assert [fact.id for fact in archived_facts] == [archived.id]

        superseded_facts, _ = await repo.list_filtered(status="superseded")
        assert [fact.id for fact in superseded_facts] == [superseded.id]

        expired_facts, _ = await repo.list_filtered(status="expired")
        assert [fact.id for fact in expired_facts] == [expired.id]

        temporary_facts, _ = await repo.list_filtered(status="temporary")
        assert [fact.id for fact in temporary_facts] == [temporary.id]

        pinned_facts, _ = await repo.list_filtered(status="pinned")
        assert [fact.id for fact in pinned_facts] == [pinned.id]

        never_accessed, _ = await repo.list_filtered(accessed="never")
        assert active.id in {fact.id for fact in never_accessed}

        await repo.reinforce([active.id])
        used_facts, _ = await repo.list_filtered(accessed="used")
        assert [fact.id for fact in used_facts] == [active.id]


class TestReinforce:
    @pytest.mark.asyncio
    async def test_reinforce_updates_access(self, repo: FactRepository):
        fact = await repo.create(
            text="Reinforce test",
            source_type=SourceType.EXPLICIT,
        )
        assert fact.access_count == 0

        await repo.reinforce([fact.id])

        updated = await repo.get(fact.id)
        assert updated.access_count == 1

    @pytest.mark.asyncio
    async def test_reinforce_empty_list(self, repo: FactRepository):
        await repo.reinforce([])

    @pytest.mark.asyncio
    async def test_reinforce_multiple(self, repo: FactRepository):
        f1 = await repo.create(text="Fact 1", source_type=SourceType.EXPLICIT)
        f2 = await repo.create(text="Fact 2", source_type=SourceType.EXPLICIT)

        await repo.reinforce([f1.id, f2.id])

        assert (await repo.get(f1.id)).access_count == 1
        assert (await repo.get(f2.id)).access_count == 1


class TestEntityRefs:
    @pytest.mark.asyncio
    async def test_add_and_get_entity_refs(self, repo: FactRepository):
        fact = await repo.create(text="Alice works here", source_type=SourceType.EXPLICIT)

        ref = await repo.add_entity_ref(fact.id, "Alice")

        assert ref.name == "Alice"

        refs = await repo.get_entity_refs(fact.id)
        assert len(refs) == 1
        assert refs[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_get_facts_for_entity(self, repo: FactRepository):
        f1 = await repo.create(text="Alice fact 1", source_type=SourceType.EXPLICIT)
        f2 = await repo.create(text="Alice fact 2", source_type=SourceType.EXPLICIT)

        await repo.add_entity_ref(f1.id, "Alice")
        await repo.add_entity_ref(f2.id, "Alice")

        facts = await repo.get_facts_for_entity("Alice", limit=10)
        assert len(facts) == 2


class TestConsolidation:
    @pytest.mark.asyncio
    async def test_list_unconsolidated(self, repo: FactRepository):
        f1 = await repo.create(text="Fact 1", source_type=SourceType.EXPLICIT)
        f2 = await repo.create(text="Fact 2", source_type=SourceType.EXPLICIT)

        unconsolidated = await repo.list_unconsolidated(limit=10)
        fact_ids = [f.id for f in unconsolidated]
        assert f1.id in fact_ids
        assert f2.id in fact_ids

    @pytest.mark.asyncio
    async def test_mark_consolidated(self, repo: FactRepository):
        fact = await repo.create(text="To consolidate", source_type=SourceType.EXPLICIT)
        assert fact.consolidated_at is None

        await repo.mark_consolidated(fact.id)

        updated = await repo.get(fact.id)
        assert updated.consolidated_at is not None

    @pytest.mark.asyncio
    async def test_consolidated_facts_not_in_unconsolidated(self, repo: FactRepository):
        f1 = await repo.create(text="Fact 1", source_type=SourceType.EXPLICIT)
        f2 = await repo.create(text="Fact 2", source_type=SourceType.EXPLICIT)

        await repo.mark_consolidated(f1.id)

        unconsolidated = await repo.list_unconsolidated(limit=10)
        fact_ids = [f.id for f in unconsolidated]
        assert f1.id not in fact_ids
        assert f2.id in fact_ids


class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_search_facts_vector(self, repo: FactRepository):
        emb = mock_embedding("guitar music")
        await repo.create(
            text="I play guitar",
            source_type=SourceType.EXPLICIT,
            embedding=emb,
        )

        results = await repo.search_facts_vector(emb, limit=5)
        assert len(results) >= 1
        assert any("guitar" in f.text for f, _ in results)


class TestEntities:
    @pytest.mark.asyncio
    async def test_create_and_get_entity(self, repo: FactRepository):
        entity = await repo.create_entity(name="Alice")

        assert entity.id is not None
        assert entity.name == "Alice"

        retrieved = await repo.get_entity(entity.id)
        assert retrieved is not None
        assert retrieved.name == "Alice"

    @pytest.mark.asyncio
    async def test_get_entity_by_name(self, repo: FactRepository):
        await repo.create_entity(name="Bob")

        entity = await repo.get_entity_by_name("Bob")
        assert entity is not None
        assert entity.name == "Bob"

    @pytest.mark.asyncio
    async def test_merge_entities(self, repo: FactRepository):
        e1 = await repo.create_entity(name="Alice")
        e2 = await repo.create_entity(name="Alicia")

        merged = await repo.merge_entities(e1.id, [e2.id])
        assert merged == 1

        assert await repo.get_entity(e2.id) is None

    @pytest.mark.asyncio
    async def test_create_duplicate_entity_returns_existing(self, repo: FactRepository):
        e1 = await repo.create_entity(name="Charlie")
        e2 = await repo.create_entity(name="Charlie")
        assert e1.id == e2.id

        # Case-insensitive dedup
        e3 = await repo.create_entity(name="charlie")
        assert e3.id == e1.id


class TestGetFactsForEntity:
    @pytest.mark.asyncio
    async def test_gets_facts_with_user_entity(self, repo: FactRepository):
        f1 = await repo.create(text="User works at Google", source_type=SourceType.EXPLICIT)
        f2 = await repo.create(text="User prefers Python", source_type=SourceType.EXPLICIT)
        f3 = await repo.create(text="Alice likes hiking", source_type=SourceType.EXPLICIT)

        await repo.add_entity_ref(f1.id, "User")
        await repo.add_entity_ref(f2.id, "User")
        await repo.add_entity_ref(f3.id, "Alice")

        user_facts = await repo.get_facts_for_entity("User", limit=10)

        fact_ids = [f.id for f in user_facts]
        assert f1.id in fact_ids
        assert f2.id in fact_ids
        assert f3.id not in fact_ids

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_user_entity(self, repo: FactRepository):
        await repo.create(text="Random fact", source_type=SourceType.EXPLICIT)

        user_facts = await repo.get_facts_for_entity("User", limit=10)
        assert user_facts == []


class TestEntityExpansion:
    @pytest.mark.asyncio
    async def test_get_entity_ids_for_facts(self, repo: FactRepository):
        f1 = await repo.create(text="Fact 1", source_type=SourceType.EXPLICIT)
        e1 = await repo.create_entity(name="Alice")
        await repo.add_entity_ref(f1.id, "Alice", e1.id)

        entity_ids = await repo.get_entity_ids_for_facts([f1.id])
        assert e1.id in entity_ids

    @pytest.mark.asyncio
    async def test_get_facts_for_entity_id(self, repo: FactRepository):
        e1 = await repo.create_entity(name="Alice")
        f1 = await repo.create(text="Fact about Alice", source_type=SourceType.EXPLICIT)
        f2 = await repo.create(text="Another Alice fact", source_type=SourceType.EXPLICIT)
        await repo.add_entity_ref(f1.id, "Alice", e1.id)
        await repo.add_entity_ref(f2.id, "Alice", e1.id)

        facts = await repo.get_facts_for_entity_id(e1.id, limit=10)
        assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_count_entity_facts_by_id(self, repo: FactRepository):
        e1 = await repo.create_entity(name="Alice")
        f1 = await repo.create(text="Fact 1", source_type=SourceType.EXPLICIT)
        await repo.add_entity_ref(f1.id, "Alice", e1.id)

        count = await repo.count_entity_facts_by_id(e1.id)
        assert count == 1
