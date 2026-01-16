import pytest
import pytest_asyncio

from ntrp.memory.models import FactType, LinkType
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
            fact_type=FactType.WORLD,
            source_type="test",
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
            fact_type=FactType.WORLD,
            source_type="test",
        )

        await repo.delete(fact.id)
        assert await repo.get(fact.id) is None

    @pytest.mark.asyncio
    async def test_list_recent(self, repo: FactRepository):
        await repo.create(text="Fact 1", fact_type=FactType.WORLD, source_type="test")
        await repo.create(text="Fact 2", fact_type=FactType.WORLD, source_type="test")

        facts = await repo.list_recent(limit=10)
        assert len(facts) >= 2

    @pytest.mark.asyncio
    async def test_count(self, repo: FactRepository):
        initial = await repo.count()
        await repo.create(text="New fact", fact_type=FactType.WORLD, source_type="test")
        assert await repo.count() == initial + 1


class TestReinforce:
    @pytest.mark.asyncio
    async def test_reinforce_updates_access(self, repo: FactRepository):
        fact = await repo.create(
            text="Reinforce test",
            fact_type=FactType.WORLD,
            source_type="test",
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
        f1 = await repo.create(text="Fact 1", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Fact 2", fact_type=FactType.WORLD, source_type="test")

        await repo.reinforce([f1.id, f2.id])

        assert (await repo.get(f1.id)).access_count == 1
        assert (await repo.get(f2.id)).access_count == 1


class TestEntityRefs:
    @pytest.mark.asyncio
    async def test_add_and_get_entity_refs(self, repo: FactRepository):
        fact = await repo.create(text="Alice works here", fact_type=FactType.WORLD, source_type="test")

        ref = await repo.add_entity_ref(fact.id, "Alice", "person")

        assert ref.name == "Alice"
        assert ref.entity_type == "person"

        refs = await repo.get_entity_refs(fact.id)
        assert len(refs) == 1
        assert refs[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_get_facts_for_entity(self, repo: FactRepository):
        f1 = await repo.create(text="Alice fact 1", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Alice fact 2", fact_type=FactType.WORLD, source_type="test")

        await repo.add_entity_ref(f1.id, "Alice", "person")
        await repo.add_entity_ref(f2.id, "Alice", "person")

        facts = await repo.get_facts_for_entity("Alice", limit=10)
        assert len(facts) == 2


class TestFactLinks:
    @pytest.mark.asyncio
    async def test_create_and_get_link(self, repo: FactRepository):
        f1 = await repo.create(text="Source fact", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Target fact", fact_type=FactType.WORLD, source_type="test")

        link = await repo.create_link(f1.id, f2.id, LinkType.ENTITY, weight=0.8)

        assert link.source_fact_id == f1.id
        assert link.target_fact_id == f2.id
        assert link.weight == 0.8

        links = await repo.get_links(f1.id)
        assert len(links) == 1

    @pytest.mark.asyncio
    async def test_get_links_by_type(self, repo: FactRepository):
        f1 = await repo.create(text="Source", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Target 1", fact_type=FactType.WORLD, source_type="test")
        f3 = await repo.create(text="Target 2", fact_type=FactType.WORLD, source_type="test")

        await repo.create_link(f1.id, f2.id, LinkType.ENTITY, weight=0.5)
        await repo.create_link(f1.id, f3.id, LinkType.SEMANTIC, weight=0.7)

        entity_links = await repo.get_links_by_type(f1.id, LinkType.ENTITY)
        assert len(entity_links) == 1
        assert entity_links[0].link_type == LinkType.ENTITY


class TestConsolidation:
    @pytest.mark.asyncio
    async def test_list_unconsolidated(self, repo: FactRepository):
        f1 = await repo.create(text="Fact 1", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Fact 2", fact_type=FactType.WORLD, source_type="test")

        unconsolidated = await repo.list_unconsolidated(limit=10)
        fact_ids = [f.id for f in unconsolidated]
        assert f1.id in fact_ids
        assert f2.id in fact_ids

    @pytest.mark.asyncio
    async def test_mark_consolidated(self, repo: FactRepository):
        fact = await repo.create(text="To consolidate", fact_type=FactType.WORLD, source_type="test")
        assert fact.consolidated_at is None

        await repo.mark_consolidated(fact.id)

        updated = await repo.get(fact.id)
        assert updated.consolidated_at is not None

    @pytest.mark.asyncio
    async def test_consolidated_facts_not_in_unconsolidated(self, repo: FactRepository):
        f1 = await repo.create(text="Fact 1", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="Fact 2", fact_type=FactType.WORLD, source_type="test")

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
            fact_type=FactType.WORLD,
            source_type="test",
            embedding=emb,
        )

        results = await repo.search_facts_vector(emb, limit=5)
        assert len(results) >= 1
        assert any("guitar" in f.text for f, _ in results)


class TestEntities:
    @pytest.mark.asyncio
    async def test_create_and_get_entity(self, repo: FactRepository):
        entity = await repo.create_entity(
            name="Alice",
            entity_type="person",
            embedding=mock_embedding("Alice"),
        )

        assert entity.id is not None
        assert entity.name == "Alice"

        retrieved = await repo.get_entity(entity.id)
        assert retrieved is not None
        assert retrieved.name == "Alice"

    @pytest.mark.asyncio
    async def test_get_entity_by_name(self, repo: FactRepository):
        await repo.create_entity(name="Bob", entity_type="person")

        entity = await repo.get_entity_by_name("Bob")
        assert entity is not None
        assert entity.name == "Bob"

    @pytest.mark.asyncio
    async def test_merge_entities(self, repo: FactRepository):
        e1 = await repo.create_entity(name="Alice", entity_type="person")
        e2 = await repo.create_entity(name="Alicia", entity_type="person")

        merged = await repo.merge_entities(e1.id, [e2.id])
        assert merged == 1

        assert await repo.get_entity(e2.id) is None

    @pytest.mark.asyncio
    async def test_create_duplicate_entity_returns_existing(self, repo: FactRepository):
        """Creating entity with same name+type returns existing entity."""
        e1 = await repo.create_entity(name="Charlie", entity_type="person")
        e2 = await repo.create_entity(name="Charlie", entity_type="person")

        # Should return the same entity, not create duplicate
        assert e1.id == e2.id
        assert e1.name == e2.name

    @pytest.mark.asyncio
    async def test_create_same_name_different_type_creates_new(self, repo: FactRepository):
        """Same name but different type creates separate entities."""
        e1 = await repo.create_entity(name="Apple", entity_type="organization")
        e2 = await repo.create_entity(name="Apple", entity_type="concept")

        # Different types = different entities
        assert e1.id != e2.id


class TestGetFactsForEntity:
    @pytest.mark.asyncio
    async def test_gets_facts_with_user_entity(self, repo: FactRepository):
        """Gets facts tagged with User entity."""
        f1 = await repo.create(text="User works at Google", fact_type=FactType.WORLD, source_type="test")
        f2 = await repo.create(text="User prefers Python", fact_type=FactType.WORLD, source_type="test")
        f3 = await repo.create(text="Alice likes hiking", fact_type=FactType.WORLD, source_type="test")

        # Tag f1 and f2 with User, f3 with Alice
        await repo.add_entity_ref(f1.id, "User", "person")
        await repo.add_entity_ref(f2.id, "User", "person")
        await repo.add_entity_ref(f3.id, "Alice", "person")

        user_facts = await repo.get_facts_for_entity("User", limit=10)

        fact_ids = [f.id for f in user_facts]
        assert f1.id in fact_ids
        assert f2.id in fact_ids
        assert f3.id not in fact_ids

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_user_entity(self, repo: FactRepository):
        """Returns empty list when no User entity exists."""
        await repo.create(text="Random fact", fact_type=FactType.WORLD, source_type="test")

        user_facts = await repo.get_facts_for_entity("User", limit=10)
        assert user_facts == []
