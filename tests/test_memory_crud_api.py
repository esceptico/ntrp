"""E2E integration tests for memory CRUD API endpoints"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ntrp.config import Config
from ntrp.memory.fact_review import FactMetadataSuggestion
from ntrp.memory.models import FactKind, SourceType
from ntrp.server.app import app
from ntrp.server.runtime import Runtime
from ntrp.settings import hash_api_key
from tests.conftest import TEST_EMBEDDING_DIM, mock_embedding


async def _mock_embed_one(text: str):
    return mock_embedding(text)


@pytest_asyncio.fixture
async def test_runtime(tmp_path: Path, monkeypatch) -> AsyncGenerator[Runtime]:
    """Create isolated runtime with memory enabled for testing"""
    import ntrp.config
    import ntrp.llm.models as llm_models
    import ntrp.settings
    from ntrp.llm.models import EmbeddingModel, Provider

    monkeypatch.setattr(ntrp.settings, "NTRP_DIR", tmp_path / "db")
    monkeypatch.setattr(ntrp.config, "NTRP_DIR", tmp_path / "db")
    test_emb = EmbeddingModel("test-embedding", Provider.OPENAI, TEST_EMBEDDING_DIM)
    monkeypatch.setitem(llm_models._embedding_models, "test-embedding", test_emb)

    test_config = Config(
        ntrp_dir=tmp_path / "db",
        openai_api_key="test-key",
        api_key_hash=hash_api_key("test-api-key"),
        memory=True,
        embedding_model="test-embedding",
        memory_model="gemini-3-flash-preview",
        chat_model="gemini-3-flash-preview",
        exa_api_key=None,
    )

    test_config.db_dir.mkdir(parents=True, exist_ok=True)

    runtime = Runtime(config=test_config)
    await runtime.connect()

    if runtime.memory:
        runtime.memory.embedder.embed_one = _mock_embed_one

        from ntrp.memory.models import ExtractedEntity, ExtractionResult

        async def mock_extract(text: str):
            words = text.lower().split()[:2]
            entities = [ExtractedEntity(name=word.strip(".,!?")) for word in words if len(word) > 2]
            return ExtractionResult(entities=entities)

        runtime.memory.extractor.extract = mock_extract

    runtime.indexer.index.embedder.embed_one = _mock_embed_one
    app.state.runtime = runtime

    yield runtime

    await runtime.close()
    app.state.runtime = None


@pytest_asyncio.fixture
async def test_client(test_runtime: Runtime) -> AsyncGenerator[AsyncClient]:
    """HTTP client for API testing"""
    headers = {"authorization": "Bearer test-api-key"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        yield client


@pytest_asyncio.fixture
async def sample_fact(test_runtime: Runtime) -> int:
    """Create a sample fact for testing"""
    memory = test_runtime.memory
    result = await memory.remember(
        text="Alice works at Anthropic on AI safety",
        source_type=SourceType.EXPLICIT,
    )
    return result.fact.id


@pytest_asyncio.fixture
async def sample_observation(test_runtime: Runtime) -> int:
    """Create a sample observation for testing"""
    memory = test_runtime.memory
    obs_repo = memory.observations

    result = await memory.remember(
        text="Test fact for observation",
        source_type=SourceType.EXPLICIT,
    )

    obs = await obs_repo.create(
        summary="Test observation summary",
        embedding=mock_embedding("test observation"),
        source_fact_id=result.fact.id,
    )
    await memory.db.conn.commit()
    return obs.id


class TestFactCRUD:
    """E2E tests for fact PATCH and DELETE endpoints"""

    @pytest.mark.asyncio
    async def test_patch_fact_updates_text_and_reextracts(self, test_client: AsyncClient, sample_fact: int):
        """PATCH /facts/{id} should update text, re-extract entities, and recreate links"""
        response = await test_client.patch(
            f"/facts/{sample_fact}", json={"text": "Alice is a researcher at Anthropic working on Claude"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "fact" in data
        assert "entity_refs" in data

        fact = data["fact"]
        assert fact["id"] == sample_fact
        assert fact["text"] == "Alice is a researcher at Anthropic working on Claude"
        assert fact["kind"] == "note"
        assert fact["salience"] == 0

        entity_refs = data["entity_refs"]
        assert isinstance(entity_refs, list)
        assert all("name" in e and "entity_id" in e for e in entity_refs)

        events = await test_client.get("/memory/events", params={"target_type": "fact", "target_id": sample_fact})
        assert events.status_code == 200
        latest = events.json()["events"][0]
        assert latest["action"] == "fact.updated"
        assert latest["actor"] == "user"
        assert latest["policy_version"] == "memory.api.v1"
        assert latest["details"]["old_chars"] > 0

    @pytest.mark.asyncio
    async def test_patch_fact_marks_for_reconsolidation(
        self, test_client: AsyncClient, sample_fact: int, test_runtime: Runtime
    ):
        """PATCH should set consolidated_at=NULL to trigger re-consolidation"""
        await test_client.patch(f"/facts/{sample_fact}", json={"text": "Updated text"})

        repo = test_runtime.memory.facts
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
    async def test_delete_fact_returns_cascade_counts(
        self, test_client: AsyncClient, sample_fact: int, test_runtime: Runtime
    ):
        """DELETE /facts/{id} should return counts of cascaded deletions"""
        repo = test_runtime.memory.facts
        entity_refs = await repo.get_entity_refs(sample_fact)

        response = await test_client.delete(f"/facts/{sample_fact}")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "deleted"
        assert data["fact_id"] == sample_fact
        assert "cascaded" in data
        assert data["cascaded"]["entity_refs"] == len(entity_refs)

        fact = await repo.get(sample_fact)
        assert fact is None

    @pytest.mark.asyncio
    async def test_delete_fact_cascades_to_entity_refs(self, test_client: AsyncClient, test_runtime: Runtime):
        """DELETE should cascade to entity_refs table"""
        memory = test_runtime.memory
        result = await memory.remember(text="Bob works at Google", source_type=SourceType.EXPLICIT)
        fact_id = result.fact.id

        repo = memory.facts
        await repo.add_entity_ref(fact_id, "Additional")

        entity_refs_before = await repo.get_entity_refs(fact_id)
        assert len(entity_refs_before) > 0

        response = await test_client.delete(f"/facts/{fact_id}")
        assert response.status_code == 200

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
        responses = await asyncio.gather(
            test_client.patch(f"/facts/{sample_fact}", json={"text": "First update"}),
            test_client.patch(f"/facts/{sample_fact}", json={"text": "Second update"}),
        )

        assert all(r.status_code == 200 for r in responses)

    @pytest.mark.asyncio
    async def test_list_facts_supports_review_filters(self, test_client: AsyncClient, test_runtime: Runtime):
        repo = test_runtime.memory.facts
        user = await repo.create_entity("User")
        visible = await repo.create(
            "User prefers raw SQL",
            SourceType.CHAT,
            kind=FactKind.PREFERENCE,
        )
        hidden = await repo.create(
            "Archived preference",
            SourceType.CHAT,
            kind=FactKind.PREFERENCE,
        )
        await repo.add_entity_ref(visible.id, "User", user.id)
        await repo.add_entity_ref(hidden.id, "User", user.id)
        await repo.archive_batch([hidden.id])
        await test_runtime.memory.db.conn.commit()

        response = await test_client.get(
            "/facts",
            params={"kind": "preference", "source_type": "chat", "entity": "user"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert [fact["id"] for fact in body["facts"]] == [visible.id]

        archived = await test_client.get("/facts", params={"status": "archived"})
        assert archived.status_code == 200
        assert hidden.id in {fact["id"] for fact in archived.json()["facts"]}


class TestFactMetadataAPI:
    @pytest.mark.asyncio
    async def test_patch_fact_metadata(self, test_client: AsyncClient, sample_fact: int):
        expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()

        response = await test_client.patch(
            f"/facts/{sample_fact}/metadata",
            json={
                "kind": "preference",
                "salience": 2,
                "confidence": 0.8,
                "expires_at": expires_at,
                "pinned": True,
            },
        )

        assert response.status_code == 200
        fact = response.json()["fact"]
        assert fact["kind"] == "preference"
        assert fact["salience"] == 2
        assert fact["confidence"] == 0.8
        assert fact["expires_at"] == expires_at
        assert fact["pinned_at"] is not None

        events = await test_client.get(
            "/memory/events",
            params={"target_type": "fact", "target_id": sample_fact, "action": "fact.metadata_updated"},
        )
        assert events.status_code == 200
        event = events.json()["events"][0]
        assert event["details"]["fields"] == ["confidence", "expires_at", "kind", "pinned_at", "salience"]

    @pytest.mark.asyncio
    async def test_patch_fact_metadata_rejects_missing_superseding_fact(
        self,
        test_client: AsyncClient,
        sample_fact: int,
    ):
        response = await test_client.patch(
            f"/facts/{sample_fact}/metadata",
            json={"superseded_by_fact_id": 999_999},
        )

        assert response.status_code == 422
        assert "superseding fact not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_kind_review_lists_untyped_facts(self, test_client: AsyncClient, test_runtime: Runtime):
        review_fact = await test_runtime.memory.facts.create(
            "User has not reviewed this fact yet",
            SourceType.EXPLICIT,
        )
        typed_fact = await test_runtime.memory.facts.create(
            "User prefers typed facts",
            SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        await test_runtime.memory.db.conn.commit()

        response = await test_client.get("/memory/facts/kind-review")

        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["facts"]]
        assert review_fact.id in ids
        assert typed_fact.id not in ids

    @pytest.mark.asyncio
    async def test_kind_review_suggestions_do_not_write_metadata(
        self,
        test_client: AsyncClient,
        test_runtime: Runtime,
        monkeypatch,
    ):
        review_fact = await test_runtime.memory.facts.create(
            "User prefers raw SQL over ORMs",
            SourceType.EXPLICIT,
        )
        await test_runtime.memory.db.conn.commit()

        async def mock_suggest(facts, model):
            assert [fact.id for fact in facts] == [review_fact.id]
            return [
                FactMetadataSuggestion(
                    fact_id=review_fact.id,
                    kind=FactKind.PREFERENCE,
                    salience=1,
                    confidence=0.9,
                    reason="stable preference",
                )
            ]

        monkeypatch.setattr("ntrp.memory.service.suggest_fact_metadata", mock_suggest)

        response = await test_client.post(
            "/memory/facts/kind-review/suggestions",
            json={"fact_ids": [review_fact.id]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total_reviewable"] == 1
        suggestion = body["suggestions"][0]["suggestion"]
        assert suggestion["kind"] == "preference"
        assert suggestion["salience"] == 1
        assert suggestion["confidence"] == 0.9

        stored = await test_runtime.memory.facts.get(review_fact.id)
        assert stored.kind == FactKind.NOTE
        assert stored.salience == 0

    @pytest.mark.asyncio
    async def test_supersession_candidates_list_review_pairs(
        self,
        test_client: AsyncClient,
        test_runtime: Runtime,
    ):
        repo = test_runtime.memory.facts
        user = await repo.create_entity("User")
        older = await repo.create(
            "User prefers concise answers",
            SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        newer = await repo.create(
            "User prefers detailed answers",
            SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
        )
        await repo.add_entity_ref(older.id, "User", user.id)
        await repo.add_entity_ref(newer.id, "User", user.id)
        await test_runtime.memory.db.conn.commit()

        response = await test_client.get("/memory/supersession/candidates")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        candidate = body["candidates"][0]
        assert candidate["kind"] == "preference"
        assert candidate["entity"] == "User"
        assert candidate["older_fact"]["id"] == older.id
        assert candidate["newer_fact"]["id"] == newer.id
        assert "review" in candidate["reason"]


class TestObservationCRUD:
    """E2E tests for observation PATCH and DELETE endpoints"""

    @pytest.mark.asyncio
    async def test_list_observations_filters_and_total(
        self,
        test_client: AsyncClient,
        sample_observation: int,
    ):
        response = await test_client.get("/observations?accessed=never&min_sources=1&status=active")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(row["id"] == sample_observation for row in data["observations"])
        row = next(row for row in data["observations"] if row["id"] == sample_observation)
        assert row["archived_at"] is None
        assert row["last_accessed_at"]

    @pytest.mark.asyncio
    async def test_observation_details_returns_full_supporting_fact_payload(
        self,
        test_client: AsyncClient,
        sample_observation: int,
    ):
        response = await test_client.get(f"/observations/{sample_observation}")

        assert response.status_code == 200
        data = response.json()
        assert data["observation"]["id"] == sample_observation
        assert data["supporting_facts"]
        support = data["supporting_facts"][0]
        assert {"id", "text", "kind", "source_type", "archived_at", "superseded_by_fact_id"} <= set(support)

    @pytest.mark.asyncio
    async def test_patch_observation_updates_summary(self, test_client: AsyncClient, sample_observation: int):
        """PATCH /observations/{id} should update summary and re-embed"""
        response = await test_client.patch(
            f"/observations/{sample_observation}", json={"summary": "Updated observation summary"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "observation" in data
        obs = data["observation"]
        assert obs["id"] == sample_observation
        assert obs["summary"] == "Updated observation summary"
        assert "evidence_count" in obs
        assert "updated_at" in obs

        events = await test_client.get(
            "/memory/events",
            params={"target_type": "observation", "target_id": sample_observation},
        )
        assert events.status_code == 200
        latest = events.json()["events"][0]
        assert latest["action"] == "observation.updated"
        assert latest["details"]["support_count"] == 1

    @pytest.mark.asyncio
    async def test_patch_observation_preserves_facts(
        self, test_client: AsyncClient, sample_observation: int, test_runtime: Runtime
    ):
        """PATCH should preserve source_fact_ids and evidence_count"""
        obs_repo = test_runtime.memory.observations
        original = await obs_repo.get(sample_observation)

        await test_client.patch(f"/observations/{sample_observation}", json={"summary": "New summary"})

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

        obs_repo = test_runtime.memory.observations
        obs = await obs_repo.get(sample_observation)
        assert obs is None

    @pytest.mark.asyncio
    async def test_delete_observation_not_found(self, test_client: AsyncClient):
        """DELETE /observations/{id} should return 404 for non-existent observation"""
        response = await test_client.delete("/observations/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Observation not found"


class TestMemoryAuditAPI:
    @pytest.mark.asyncio
    async def test_memory_audit(self, test_client: AsyncClient, sample_observation: int):
        response = await test_client.get("/memory/audit")

        assert response.status_code == 200
        data = response.json()
        assert data["facts"]["total"] >= 1
        assert data["observations"]["total"] >= 1
        assert "observation_source_distribution" in data
        assert "provenance" in data

    @pytest.mark.asyncio
    async def test_memory_events_list_remember_provenance(self, test_client: AsyncClient, sample_fact: int):
        response = await test_client.get("/memory/events", params={"target_type": "fact", "target_id": sample_fact})

        assert response.status_code == 200
        events = response.json()["events"]
        assert events
        created = next(event for event in events if event["action"] == "fact.created")
        assert created["actor"] == "backend"
        assert created["reason"] == "remembered fact"
        assert created["policy_version"] == "memory.remember.v1"
        assert created["details"]["kind"] == "note"

    @pytest.mark.asyncio
    async def test_memory_profile(self, test_client: AsyncClient, test_runtime: Runtime):
        fact = await test_runtime.memory.facts.create(
            "User prefers concise status updates",
            SourceType.EXPLICIT,
            kind=FactKind.PREFERENCE,
            salience=2,
        )
        await test_runtime.memory.db.conn.commit()

        response = await test_client.get("/memory/profile")

        assert response.status_code == 200
        data = response.json()
        assert [row["id"] for row in data["facts"]] == [fact.id]
        assert data["facts"][0]["kind"] == "preference"

    @pytest.mark.asyncio
    async def test_prune_dry_run_does_not_delete(
        self,
        test_client: AsyncClient,
        test_runtime: Runtime,
        sample_observation: int,
    ):
        now = datetime.now(UTC)
        old = (now - timedelta(days=31)).isoformat()
        await test_runtime.memory.db.conn.execute(
            "UPDATE observations SET created_at = ?, updated_at = ? WHERE id = ?",
            (old, old, sample_observation),
        )
        await test_runtime.memory.db.conn.commit()

        response = await test_client.post(
            "/memory/prune/dry-run",
            json={"older_than_days": 30, "max_sources": 5, "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["criteria"]["older_than_days"] == 30
        assert data["criteria"]["max_sources"] == 5
        assert data["summary"]["total"] >= 1
        assert any(row["id"] == sample_observation for row in data["candidates"])
        candidate = next(row for row in data["candidates"] if row["id"] == sample_observation)
        assert {"summary", "created_at", "updated_at", "evidence_count", "chars", "reason"} <= set(candidate)

        obs = await test_runtime.memory.observations.get(sample_observation)
        assert obs is not None

    @pytest.mark.asyncio
    async def test_prune_apply_archives_only_matching_candidates(
        self,
        test_client: AsyncClient,
        test_runtime: Runtime,
        sample_observation: int,
    ):
        recent = await test_runtime.memory.observations.create(
            summary="Recent pattern should not be archived",
            embedding=mock_embedding("recent pattern"),
        )
        old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        await test_runtime.memory.db.conn.execute(
            "UPDATE observations SET created_at = ?, updated_at = ? WHERE id = ?",
            (old, old, sample_observation),
        )
        await test_runtime.memory.db.conn.commit()

        response = await test_client.post(
            "/memory/prune/apply",
            json={
                "observation_ids": [sample_observation, recent.id],
                "older_than_days": 30,
                "max_sources": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived"] == 1
        assert data["archived_ids"] == [sample_observation]
        assert data["skipped_ids"] == [recent.id]

        archived = await test_runtime.memory.observations.get(sample_observation)
        not_archived = await test_runtime.memory.observations.get(recent.id)
        assert archived.archived_at is not None
        assert not_archived.archived_at is None

        events = await test_client.get("/memory/events", params={"action": "observations.archived"})
        assert events.status_code == 200
        event = events.json()["events"][0]
        assert event["actor"] == "user"
        assert event["policy_version"] == "memory.prune.v1"
        assert event["details"]["ids"] == [sample_observation]

    @pytest.mark.asyncio
    async def test_prune_apply_can_archive_all_matching_candidates(
        self,
        test_client: AsyncClient,
        test_runtime: Runtime,
        sample_observation: int,
    ):
        recent = await test_runtime.memory.observations.create(
            summary="Recent pattern should not be archived by bulk prune",
            embedding=mock_embedding("recent pattern"),
        )
        old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        await test_runtime.memory.db.conn.execute(
            "UPDATE observations SET created_at = ?, updated_at = ? WHERE id = ?",
            (old, old, sample_observation),
        )
        await test_runtime.memory.db.conn.commit()

        response = await test_client.post(
            "/memory/prune/apply",
            json={
                "all_matching": True,
                "older_than_days": 30,
                "max_sources": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived"] == 1
        assert data["archived_ids"] == [sample_observation]
        assert data["skipped_ids"] == []

        archived = await test_runtime.memory.observations.get(sample_observation)
        not_archived = await test_runtime.memory.observations.get(recent.id)
        assert archived.archived_at is not None
        assert not_archived.archived_at is None

        events = await test_client.get("/memory/events", params={"action": "observations.archived"})
        assert events.status_code == 200
        event = events.json()["events"][0]
        assert event["details"]["all_matching"] is True

    @pytest.mark.asyncio
    async def test_prune_apply_requires_ids_unless_all_matching(self, test_client: AsyncClient):
        response = await test_client.post(
            "/memory/prune/apply",
            json={"older_than_days": 30, "max_sources": 5},
        )

        assert response.status_code == 422
        assert "observation_ids required" in response.json()["detail"]


class TestMemoryDisabled:
    """Test error handling when memory is disabled"""

    @pytest.mark.asyncio
    async def test_endpoints_fail_when_memory_disabled(self, tmp_path: Path, monkeypatch):
        """All CRUD endpoints should return 503 when memory is disabled"""
        import ntrp.config
        import ntrp.settings

        monkeypatch.setattr(ntrp.settings, "NTRP_DIR", tmp_path / "db")
        monkeypatch.setattr(ntrp.config, "NTRP_DIR", tmp_path / "db")

        test_config = Config(
            ntrp_dir=tmp_path / "db",
            openai_api_key="test-key",
            api_key_hash=hash_api_key("test-api-key"),
            memory=False,
            chat_model="gemini-3-flash-preview",
            memory_model="gemini-3-flash-preview",
            embedding_model="text-embedding-3-small",
            exa_api_key=None,
        )
        test_config.db_dir.mkdir(parents=True, exist_ok=True)

        runtime = Runtime(config=test_config)
        await runtime.connect()
        app.state.runtime = runtime

        headers = {"authorization": "Bearer test-api-key"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
            responses = await asyncio.gather(
                client.patch("/facts/1", json={"text": "test"}),
                client.patch("/facts/1/metadata", json={"kind": "preference"}),
                client.get("/facts"),
                client.delete("/facts/1"),
                client.patch("/observations/1", json={"summary": "test"}),
                client.delete("/observations/1"),
                client.get("/memory/audit"),
                client.get("/memory/events"),
                client.get("/memory/facts/kind-review"),
                client.post("/memory/facts/kind-review/suggestions", json={}),
                client.get("/memory/supersession/candidates"),
                client.get("/memory/profile"),
                client.post("/memory/prune/dry-run", json={}),
                client.post("/memory/prune/apply", json={"observation_ids": [1]}),
            )

            assert all(r.status_code == 503 for r in responses)
            assert all("Memory is disabled" in r.json()["detail"] for r in responses)

        await runtime.close()
        app.state.runtime = None
