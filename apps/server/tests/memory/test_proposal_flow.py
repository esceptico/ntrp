from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import ntrp.database as database
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.skill_inducer import (
    ProposalDraftGone,
    ProposalStateError,
    SkillInducer,
    SkillSlugCollision,
)
from ntrp.memory.store.base import GraphDatabase
from ntrp.server.deps import require_pattern_finder
from ntrp.server.routers.admin_memory import router as admin_memory_router

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
SKILL_BODY = """# PR Triage

## When to use
Use this when morning PR triage starts.

## Steps
1. Check PRs.

## Inputs
- Pull request list

## Outputs
- Review assignment

## Notes
Keep evidence visible.
"""


class _FakeLLM:
    def __init__(self, response: str = SKILL_BODY):
        self.response = response

    async def __call__(self, prompt: str) -> str:
        return self.response


class _FakeEmbedder:
    def __init__(self):
        self.calls: list[str] = []

    async def embed_one(self, text: str) -> np.ndarray:
        self.calls.append(text)
        return _vec(0)


@pytest_asyncio.fixture
async def conn(tmp_path: Path):
    db_conn = await database.connect(tmp_path / "memory.db", vec=True)
    await db_conn.execute("PRAGMA foreign_keys=ON")
    db = GraphDatabase(db_conn, TEST_EMBEDDING_DIM)
    await db.init_schema()
    try:
        yield db_conn
    finally:
        await db_conn.close()


def _vec(index: int) -> np.ndarray:
    vector = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    vector[index] = 1.0
    return vector


def _cos_vec(cosine: float) -> np.ndarray:
    vector = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    vector[0] = cosine
    vector[1] = math.sqrt(1.0 - cosine * cosine)
    return vector


async def _insert_claim(conn: aiosqlite.Connection, tags: list[str] | None = None) -> str:
    repo = MemoryItemsRepository(conn)
    claim_id = await repo.insert_item(
        MemoryItemInsert(
            kind="claim",
            content="User triages pull requests every morning.",
            provenance="inferred",
            source_refs=[],
            confidence=0.8,
            status="active",
            scope="user",
            tags=tags or ["toolable:true", "trigger:morning-pr-triage"],
            embedding=_cos_vec(0.9),
            valid_from=NOW,
        )
    )
    for index in range(3):
        evidence_id = await repo.insert_item(
            MemoryItemInsert(
                kind="observation",
                content=f"evidence {index}",
                provenance="inferred",
                source_refs=[],
                confidence=0.7,
                status="active",
                scope="user",
                tags=["triage"],
                embedding=_vec(0),
                valid_from=NOW,
            )
        )
        await repo.insert_parent_edge(claim_id, evidence_id, "evidence")
    return claim_id


async def _proposal(
    conn: aiosqlite.Connection,
    tmp_path: Path,
    *,
    tags: list[str] | None = None,
    draft_exists: bool = True,
) -> tuple[SkillInducer, str, str]:
    claim_id = await _insert_claim(conn)
    inducer = SkillInducer(
        repo=MemoryItemsRepository(conn),
        draft_client=_FakeLLM(SKILL_BODY),
        embedder=_FakeEmbedder(),
        draft_dir=tmp_path / "drafts",
        skills_dir=tmp_path / "skills",
    )
    await inducer.run(now=NOW)
    proposal_id = (await _rows(conn, "proposal"))[0]["id"]
    if tags is not None:
        await conn.execute("UPDATE memory_items SET tags = ? WHERE id = ?", (json.dumps(tags), proposal_id))
        await conn.commit()
    if not draft_exists:
        (tmp_path / "drafts" / "pr-triage" / "SKILL.md").unlink()
    return inducer, proposal_id, claim_id


async def _rows(conn: aiosqlite.Connection, kind: str) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind = ? ORDER BY created_at, id", (kind,))


async def _row(conn: aiosqlite.Connection, item_id: str) -> aiosqlite.Row:
    rows = await conn.execute_fetchall("SELECT * FROM memory_items WHERE id = ?", (item_id,))
    assert rows
    return rows[0]


@pytest.mark.asyncio
async def test_approve_promotes_proposal_to_skill_file_row_and_edges(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, claim_id = await _proposal(conn, tmp_path)

    result = await inducer.approve_proposal(proposal_id, now=NOW)

    skill_path = tmp_path / "skills" / "pr-triage" / "SKILL.md"
    assert result["skill_path"] == str(skill_path)
    assert skill_path.read_text() == SKILL_BODY
    skills = await _rows(conn, "skill")
    assert len(skills) == 1
    assert skills[0]["content"] == SKILL_BODY
    assert "skill_match" not in json.loads(skills[0]["tags"])
    assert "proposal-status:approved" in json.loads((await _row(conn, proposal_id))["tags"])
    edges = await MemoryItemsRepository(conn).list_parent_edges(skills[0]["id"])
    assert [(edge.parent_id, edge.role) for edge in edges] == [(claim_id, "evidence")]


@pytest.mark.asyncio
async def test_approve_uses_atomic_rename_within_filesystem(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, _ = await _proposal(conn, tmp_path)
    draft_path = tmp_path / "drafts" / "pr-triage" / "SKILL.md"

    await inducer.approve_proposal(proposal_id, now=NOW)

    assert not draft_path.exists()
    assert (tmp_path / "skills" / "pr-triage" / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_approve_rejects_missing_draft_file(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, _ = await _proposal(conn, tmp_path, draft_exists=False)

    with pytest.raises(ProposalDraftGone):
        await inducer.approve_proposal(proposal_id, now=NOW)


@pytest.mark.asyncio
async def test_approve_rejects_non_open_proposal(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, _ = await _proposal(
        conn,
        tmp_path,
        tags=["proposal", "skill-draft", "proposal-status:rejected", "slug:pr-triage"],
    )

    with pytest.raises(ProposalStateError):
        await inducer.approve_proposal(proposal_id, now=NOW)


@pytest.mark.asyncio
async def test_approve_rejects_skill_slug_collision(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, _ = await _proposal(conn, tmp_path)
    (tmp_path / "skills" / "pr-triage").mkdir(parents=True)

    with pytest.raises(SkillSlugCollision):
        await inducer.approve_proposal(proposal_id, now=NOW)


@pytest.mark.asyncio
async def test_reject_marks_proposal_and_deletes_draft(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, _ = await _proposal(conn, tmp_path)
    draft_path = tmp_path / "drafts" / "pr-triage" / "SKILL.md"

    result = await inducer.reject_proposal(proposal_id, reason="duplicate workflow", now=NOW)

    tags = json.loads((await _row(conn, proposal_id))["tags"])
    assert result["rejected_at"] == NOW.isoformat()
    assert "proposal-status:rejected" in tags
    assert "proposal-status:open" not in tags
    assert "rejection-reason:duplicate-workflow" in tags
    assert not draft_path.exists()


@pytest.mark.asyncio
async def test_reject_rejects_non_open_proposal(conn: aiosqlite.Connection, tmp_path: Path):
    inducer, proposal_id, _ = await _proposal(
        conn,
        tmp_path,
        tags=["proposal", "skill-draft", "proposal-status:approved", "slug:pr-triage"],
    )

    with pytest.raises(ProposalStateError):
        await inducer.reject_proposal(proposal_id, now=NOW)


def test_admin_skill_inducer_run_endpoint_dispatches_to_inducer():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakeInducer:
        async def run(self, *, window_days: int, scope: str, limit: int = 500):
            return SimpleNamespace(to_dict=lambda: {"window_days": window_days, "scope": scope, "limit": limit})

    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(skill_inducer=_FakeInducer())

    response = TestClient(app).post(
        "/admin/memory/skill-inducer/run",
        json={"window_days": 14, "scope": "user", "limit": 25},
    )

    assert response.status_code == 200
    assert response.json() == {"window_days": 14, "scope": "user", "limit": 25}


def test_admin_proposals_list_endpoint_filters_status():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakeInducer:
        async def list_proposals(self, *, status: str, scope: str, window_days: int = 365):
            return [{"id": "p1", "status": status, "scope": scope, "window_days": window_days}]

    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(skill_inducer=_FakeInducer())

    response = TestClient(app).get("/admin/memory/proposals?status=open&scope=user")

    assert response.status_code == 200
    assert response.json()["proposals"] == [{"id": "p1", "status": "open", "scope": "user", "window_days": 365}]


def test_admin_approve_endpoint_maps_success_and_errors():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakeInducer:
        async def approve_proposal(self, proposal_id: str, *, slug: str | None = None):
            if proposal_id == "gone":
                raise ProposalDraftGone("draft file missing")
            if proposal_id == "collision":
                raise SkillSlugCollision("skill slug exists")
            return {"skill_id": "s1", "skill_path": f"/skills/{slug or proposal_id}/SKILL.md"}

    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(skill_inducer=_FakeInducer())
    client = TestClient(app)

    assert client.post("/admin/memory/proposals/pr-triage/approve?slug=new-name").json() == {
        "skill_id": "s1",
        "skill_path": "/skills/new-name/SKILL.md",
    }
    assert client.post("/admin/memory/proposals/gone/approve").status_code == 410
    assert client.post("/admin/memory/proposals/collision/approve").status_code == 409


def test_admin_reject_endpoint_maps_success_and_conflict():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakeInducer:
        async def reject_proposal(self, proposal_id: str, *, reason: str | None = None):
            if proposal_id == "closed":
                raise ProposalStateError("proposal is not open")
            return {"rejected_at": NOW.isoformat(), "reason": reason}

    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(skill_inducer=_FakeInducer())
    client = TestClient(app)

    ok = client.post("/admin/memory/proposals/open/reject", json={"reason": "duplicate"})
    conflict = client.post("/admin/memory/proposals/closed/reject", json={})

    assert ok.json() == {"rejected_at": NOW.isoformat(), "reason": "duplicate"}
    assert conflict.status_code == 409
