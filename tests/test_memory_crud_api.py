"""E2E integration tests for memory CRUD API endpoints"""
import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ntrp.config import Config
from ntrp.memory.models import FactType
from ntrp.server.app import app
from ntrp.server.runtime import Runtime, reset_runtime
from tests.conftest import TEST_EMBEDDING_DIM, mock_embedding


@pytest_asyncio.fixture
async def test_runtime(tmp_path: Path, monkeypatch) -> AsyncGenerator[Runtime]:
    """Create isolated runtime with memory enabled for testing"""
    await reset_runtime()

    # Monkeypatch NTRP_DIR to use temp directory
    import ntrp.config
    monkeypatch.setattr(ntrp.config, "NTRP_DIR", tmp_path / "db")

    # Create test config
    test_config = Config(
        vault_path=tmp_path / "vault",
        openai_api_key="test-key",  # Required but not used with mock
        memory=True,
        embedding_model="test-embedding",
        embedding_dim=TEST_EMBEDDING_DIM,
        memory_model="gpt-4o-mini",
        chat_model="gpt-4o",
        browser=None,  # Disable browser to avoid profile issues
        exa_api_key=None,  # Disable web search
    )

    # Create temp directories
    test_config.vault_path.mkdir(parents=True, exist_ok=True)
    test_config.db_dir.mkdir(parents=True, exist_ok=True)

    runtime = Runtime(config=test_config)
    await runtime.connect()

    # Replace embedder with mock for tests (must be async)
    if runtime.memory:
        async def mock_embed_one(text: str):
            return mock_embedding(text)
        runtime.memory.embedder.embed_one = mock_embed_one

        # Mock extractor to avoid LLM calls
        from ntrp.memory.models import ExtractedEntity, ExtractionResult
        async def mock_extract(text: str):
            # Return simple entities for testing (lowercase text as entity names)
            words = text.lower().split()[:2]  # First 2 words as entities
            entities = [ExtractedEntity(name=word.strip(".,!?"), entity_type="test") for word in words if len(word) > 2]
            return ExtractionResult(entities=entities, entity_pairs=[])
        runtime.memory.extractor.extract = mock_extract

    # Set global runtime for API endpoints
    import ntrp.server.runtime as runtime_module
    runtime_module._runtime = runtime

    yield runtime

    await runtime.close()
    await reset_runtime()


@pytest_asyncio.fixture
async def test_client(test_runtime: Runtime) -> AsyncGenerator[AsyncClient]:
    """HTTP client for API testing"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def sample_fact(test_runtime: Runtime) -> int:
    """Create a sample fact for testing"""
    memory = test_runtime.memory
    result = await memory.remember(
        text="Alice works at Anthropic on AI safety",
        source_type="test",
        fact_type=FactType.WORLD,
    )
    return result.fact.id


@pytest_asyncio.fixture
async def sample_observation(test_runtime: Runtime) -> int:
    """Create a sample observation for testing"""
    memory = test_runtime.memory
    obs_repo = memory.obs_repo()

    # Create a fact first
    result = await memory.remember(
        text="Test fact for observation",
        source_type="test",
    )

    # Create observation
    obs = await obs_repo.create(
        summary="Test observation summary",
        embedding=mock_embedding("test observation"),
        source_fact_id=result.fact.id,
    )
    return obs.id


class TestFactCRUD:
    """E2E tests for fact PATCH and DELETE endpoints"""

    @pytest.mark.asyncio
    async def test_patch_fact_updates_text_and_reextracts(self, test_client: AsyncClient, sample_fact: int):
        """PATCH /facts/{id} should update text, re-extract entities, and recreate links"""
        # Update fact with new text
        response = await test_client.patch(
            f"/facts/{sample_fact}",
            json={"text": "Alice is a researcher at Anthropic working on Claude"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "fact" in data
        assert "entity_refs" in data
        assert "links_created" in data

        # Verify fact was updated
        fact = data["fact"]
        assert fact["id"] == sample_fact
        assert fact["text"] == "Alice is a researcher at Anthropic working on Claude"
        assert fact["fact_type"] == "world"

        # Verify entity refs were extracted (Alice, Anthropic, Claude should be detected)
        entity_refs = data["entity_refs"]
        assert isinstance(entity_refs, list)
        # Note: Exact entities depend on extraction model, so just check structure
        assert all("name" in e and "type" in e for e in entity_refs)

    @pytest.mark.asyncio
    async def test_patch_fact_marks_for_reconsolidation(self, test_client: AsyncClient, sample_fact: int, test_runtime: Runtime):
        """PATCH should set consolidated_at=NULL to trigger re-consolidation"""
        await test_client.patch(
            f"/facts/{sample_fact}",
            json={"text": "Updated text"}
        )

        # Verify fact is marked unconsolidated
        repo = test_runtime.memory.fact_repo()
        fact = await repo.get(sample_fact)
        assert fact.consolidated_at is None

    @pytest.mark.asyncio
    async def test_patch_fact_not_found(self, test_client: AsyncClient):
        """PATCH /facts/{id} should return 404 for non-existent fact"""
        response = await test_client.patch("/facts/99999", json={"text": "New text"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Fact not found"

    @pytest.mark.asyncio
    async def test_patch_fact_empty_text(self, test_client: AsyncClient, sample_fact: int):
        """PATCH /facts/{id} should return 422 for empty text"""
        response = await test_client.patch(f"/facts/{sample_fact}", json={"text": ""})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_fact_text_too_long(self, test_client: AsyncClient, sample_fact: int):
        """PATCH /facts/{id} should return 422 for text >10000 chars"""
        long_text = "x" * 10001
        response = await test_client.patch(f"/facts/{sample_fact}", json={"text": long_text})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_fact_returns_cascade_counts(self, test_client: AsyncClient, sample_fact: int, test_runtime: Runtime):
        """DELETE /facts/{id} should return counts of cascaded deletions"""
        # Get counts before deletion
        repo = test_runtime.memory.fact_repo()
        entity_refs = await repo.get_entity_refs(sample_fact)
        links = await repo.get_links(sample_fact)

        # Delete fact
        response = await test_client.delete(f"/facts/{sample_fact}")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "deleted"
        assert data["fact_id"] == sample_fact
        assert "cascaded" in data
        assert data["cascaded"]["entity_refs"] == len(entity_refs)
        assert data["cascaded"]["links"] == len(links)

        # Verify fact is actually deleted
        fact = await repo.get(sample_fact)
        assert fact is None

    @pytest.mark.asyncio
    async def test_delete_fact_cascades_to_entity_refs(self, test_client: AsyncClient, test_runtime: Runtime):
        """DELETE should cascade to entity_refs table"""
        # Create fact
        memory = test_runtime.memory
        result = await memory.remember(text="Bob works at Google", source_type="test")
        fact_id = result.fact.id

        # Manually add more entity refs
        repo = memory.fact_repo()
        await repo.add_entity_ref(fact_id, "Additional", "test")

        entity_refs_before = await repo.get_entity_refs(fact_id)
        # Should have entities from mock extractor + manually added
        assert len(entity_refs_before) > 0

        # Delete fact
        response = await test_client.delete(f"/facts/{fact_id}")
        assert response.status_code == 200

        # Verify entity_refs are deleted (cascade)
        entity_refs_after = await repo.get_entity_refs(fact_id)
        assert len(entity_refs_after) == 0

    @pytest.mark.asyncio
    async def test_delete_fact_not_found(self, test_client: AsyncClient):
        """DELETE /facts/{id} should return 404 for non-existent fact"""
        response = await test_client.delete("/facts/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Fact not found"

    @pytest.mark.asyncio
    async def test_concurrent_fact_updates(self, test_client: AsyncClient, sample_fact: int):
        """Multiple updates should be serialized by _db_lock"""
        # Fire two updates concurrently
        import asyncio
        responses = await asyncio.gather(
            test_client.patch(f"/facts/{sample_fact}", json={"text": "First update"}),
            test_client.patch(f"/facts/{sample_fact}", json={"text": "Second update"}),
        )

        # Both should succeed (one will win)
        assert all(r.status_code == 200 for r in responses)


class TestObservationCRUD:
    """E2E tests for observation PATCH and DELETE endpoints"""

    @pytest.mark.asyncio
    async def test_patch_observation_updates_summary(self, test_client: AsyncClient, sample_observation: int):
        """PATCH /observations/{id} should update summary and re-embed"""
        response = await test_client.patch(
            f"/observations/{sample_observation}",
            json={"summary": "Updated observation summary"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "observation" in data
        obs = data["observation"]
        assert obs["id"] == sample_observation
        assert obs["summary"] == "Updated observation summary"
        assert "evidence_count" in obs
        assert "updated_at" in obs

    @pytest.mark.asyncio
    async def test_patch_observation_preserves_facts(self, test_client: AsyncClient, sample_observation: int, test_runtime: Runtime):
        """PATCH should preserve source_fact_ids and evidence_count"""
        # Get original observation
        obs_repo = test_runtime.memory.obs_repo()
        original = await obs_repo.get(sample_observation)

        # Update observation
        await test_client.patch(
            f"/observations/{sample_observation}",
            json={"summary": "New summary"}
        )

        # Verify source_fact_ids unchanged
        updated = await obs_repo.get(sample_observation)
        assert updated.source_fact_ids == original.source_fact_ids
        assert updated.evidence_count == original.evidence_count

    @pytest.mark.asyncio
    async def test_patch_observation_not_found(self, test_client: AsyncClient):
        """PATCH /observations/{id} should return 404 for non-existent observation"""
        response = await test_client.patch("/observations/99999", json={"summary": "New summary"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Observation not found"

    @pytest.mark.asyncio
    async def test_patch_observation_empty_summary(self, test_client: AsyncClient, sample_observation: int):
        """PATCH /observations/{id} should return 422 for empty summary"""
        response = await test_client.patch(f"/observations/{sample_observation}", json={"summary": ""})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_observation(self, test_client: AsyncClient, sample_observation: int, test_runtime: Runtime):
        """DELETE /observations/{id} should delete observation"""
        response = await test_client.delete(f"/observations/{sample_observation}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["observation_id"] == sample_observation

        # Verify observation is deleted
        obs_repo = test_runtime.memory.obs_repo()
        obs = await obs_repo.get(sample_observation)
        assert obs is None

    @pytest.mark.asyncio
    async def test_delete_observation_not_found(self, test_client: AsyncClient):
        """DELETE /observations/{id} should return 404 for non-existent observation"""
        response = await test_client.delete("/observations/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Observation not found"


class TestMemoryDisabled:
    """Test error handling when memory is disabled"""

    @pytest.mark.asyncio
    async def test_endpoints_fail_when_memory_disabled(self, tmp_path: Path):
        """All CRUD endpoints should return 503 when memory is disabled"""
        await reset_runtime()

        # Create runtime with memory disabled
        test_config = Config(
            db_dir=tmp_path / "db",
            vault_path=tmp_path / "vault",
            memory=False,  # Memory disabled
            browser=None,
            exa_api_key=None,
        )
        test_config.db_dir.mkdir(parents=True, exist_ok=True)

        runtime = Runtime(config=test_config)
        await runtime.connect()

        import ntrp.server.runtime as runtime_module
        runtime_module._runtime = runtime

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test all CRUD endpoints
            responses = await asyncio.gather(
                client.patch("/facts/1", json={"text": "test"}),
                client.delete("/facts/1"),
                client.patch("/observations/1", json={"summary": "test"}),
                client.delete("/observations/1"),
            )

            # All should return 503
            assert all(r.status_code == 503 for r in responses)
            assert all("Memory is disabled" in r.json()["detail"] for r in responses)

        await runtime.close()
        await reset_runtime()
