from types import SimpleNamespace

from fastapi.testclient import TestClient

from ntrp.knowledge.models import (
    KnowledgeFactConsolidationCommitResult,
    KnowledgeFactConsolidationProposal,
    KnowledgeFactConsolidationResult,
)
from ntrp.server.app import app
from ntrp.server.deps import require_memory


class _FactObjects:
    def __init__(self):
        self.batch_calls = []

    async def get_batch(self, object_ids: list[int]):
        self.batch_calls.append(object_ids)
        return {
            1: SimpleNamespace(title="Canonical preference", text="Use concise answers."),
            2: SimpleNamespace(title="Duplicate preference", text="Keep responses short."),
        }


class _FactConsolidationMemory:
    def __init__(self):
        self.knowledge_objects = _FactObjects()
        self.proposal = KnowledgeFactConsolidationProposal(
            canonical_object_id=1,
            duplicate_object_ids=[2],
            reason="Same user preference",
            confidence=0.91,
            evidence_terms=["concise"],
            source_ids=["knowledge:1", "knowledge:2"],
        )
        self.calls = []
        self.commit_calls = []

    async def propose_fact_consolidation(self, *, limit: int, min_confidence: float, max_proposals: int):
        self.calls.append(
            {
                "limit": limit,
                "min_confidence": min_confidence,
                "max_proposals": max_proposals,
            }
        )
        return KnowledgeFactConsolidationResult(proposals=[self.proposal], scanned=2, skipped=0)

    async def commit_fact_consolidation_proposal(self, proposal, *, apply: bool):
        self.commit_calls.append({"proposal": proposal, "apply": apply})
        return KnowledgeFactConsolidationCommitResult(
            proposal=proposal,
            committed=True,
            reason="Merged duplicate fact",
        )


def test_fact_consolidation_route_enriches_cached_review_payload():
    svc = _FactConsolidationMemory()
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        client = TestClient(app)
        response = client.get("/knowledge/facts/consolidation?limit=99999&min_confidence=2&max_proposals=999&refresh=true")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert response.status_code == 200
    payload = response.json()
    assert svc.calls == [{"limit": 10000, "min_confidence": 1.0, "max_proposals": 200}]
    assert svc.knowledge_objects.batch_calls == [[1, 2]]
    assert payload["cache"]["hit"] is False
    assert payload["scanned"] == 2
    assert payload["proposals"][0]["canonical_id"] == 1
    assert payload["proposals"][0]["canonical_title"] == "Canonical preference"
    assert payload["proposals"][0]["canonical_text"] == "Use concise answers."
    assert payload["proposals"][0]["duplicate_ids"] == [2]
    assert payload["proposals"][0]["duplicate_titles"] == ["Duplicate preference"]


def test_fact_consolidation_commit_route_invalidates_cache_scope():
    svc = _FactConsolidationMemory()
    app.dependency_overrides[require_memory] = lambda: svc
    try:
        client = TestClient(app)
        first = client.get("/knowledge/facts/consolidation?refresh=true")
        second = client.get("/knowledge/facts/consolidation")
        commit = client.post(
            "/knowledge/facts/consolidation/commit",
            json={"proposal": svc.proposal.model_dump()},
        )
        after_commit = client.get("/knowledge/facts/consolidation")
    finally:
        app.dependency_overrides.pop(require_memory, None)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["cache"]["hit"] is True
    assert commit.status_code == 200
    assert commit.json()["committed"] is True
    assert svc.commit_calls == [{"proposal": svc.proposal, "apply": True}]
    assert after_commit.status_code == 200
    assert after_commit.json()["cache"]["hit"] is False
    assert len(svc.calls) == 2
