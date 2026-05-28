from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import ntrp.database as database
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase
from ntrp.server.deps import require_memory
from ntrp.server.routers.admin_memory import router as admin_memory_router

if TYPE_CHECKING:
    import aiosqlite

TEST_EMBEDDING_DIM = 4
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def conn(tmp_path):
    db_conn = await database.connect(tmp_path / "memory.db", vec=True)
    await db_conn.execute("PRAGMA foreign_keys=ON")
    db = GraphDatabase(db_conn, TEST_EMBEDDING_DIM)
    await db.init_schema()
    try:
        yield db_conn
    finally:
        await db_conn.close()


def _vec(i: int) -> np.ndarray:
    v = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    v[i] = 1.0
    return v


async def _insert(
    repo: MemoryItemsRepository,
    *,
    kind: str,
    content: str,
    status: str = "active",
    scope: str = "user",
    confidence: float = 0.5,
    embedding: np.ndarray | None = None,
    tags: list[str] | None = None,
    valid_from: datetime | None = None,
    invalid_at: datetime | None = None,
) -> str:
    return await repo.insert_item(
        MemoryItemInsert(
            kind=kind,
            content=content,
            source_refs=[],
            confidence=confidence,
            provenance="recorded",
            scope=scope,
            status=status,
            tags=tags or [],
            embedding=embedding,
            valid_from=valid_from,
            invalid_at=invalid_at,
        )
    )


def _build_client(memory_service) -> TestClient:
    app = FastAPI()
    app.include_router(admin_memory_router)
    app.dependency_overrides[require_memory] = lambda: memory_service
    return TestClient(app)


class _FakeMemoryService:
    def __init__(self, conn: aiosqlite.Connection):
        self.memory = type("M", (), {"items": MemoryItemsRepository(conn)})()


@pytest.mark.asyncio
async def test_list_items_filters_by_kind_and_status(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    ep_id = await _insert(repo, kind="episode", content="ep one", embedding=_vec(0))
    obs_id = await _insert(repo, kind="observation", content="obs one", embedding=_vec(1))
    await _insert(repo, kind="claim", content="archived claim", status="archived")

    client = _build_client(_FakeMemoryService(conn))

    resp = client.get("/admin/memory/items?kinds=episode&statuses=active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == ep_id
    assert data["items"][0]["kind"] == "episode"

    resp = client.get("/admin/memory/items?kinds=episode,observation&statuses=active")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["items"]}
    assert ids == {ep_id, obs_id}


@pytest.mark.asyncio
async def test_list_items_validity_filter_applies_to_list_and_search(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    current = await _insert(
        repo,
        kind="claim",
        content="validity token current",
        valid_from=NOW - timedelta(days=1),
    )
    future = await _insert(
        repo,
        kind="claim",
        content="validity token future",
        valid_from=NOW + timedelta(days=1),
    )
    expired = await _insert(
        repo,
        kind="claim",
        content="validity token expired",
        valid_from=NOW - timedelta(days=5),
        invalid_at=NOW - timedelta(days=1),
    )

    client = _build_client(_FakeMemoryService(conn))

    current_resp = client.get("/admin/memory/items?validity=current")
    assert current_resp.status_code == 200
    assert {item["id"] for item in current_resp.json()["items"]} == {current}

    future_resp = client.get("/admin/memory/items?validity=future")
    assert future_resp.status_code == 200
    assert {item["id"] for item in future_resp.json()["items"]} == {future}

    expired_resp = client.get("/admin/memory/items?query=validity&validity=expired")
    assert expired_resp.status_code == 200
    assert {item["id"] for item in expired_resp.json()["items"]} == {expired}


@pytest.mark.asyncio
async def test_invalid_validity_returns_400(conn: aiosqlite.Connection):
    client = _build_client(_FakeMemoryService(conn))
    resp = client.get("/admin/memory/items?validity=bogus")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_items_fts_query(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    target = await _insert(repo, kind="observation", content="the user prefers TypeScript")
    await _insert(repo, kind="observation", content="random noise about kittens")

    client = _build_client(_FakeMemoryService(conn))

    resp = client.get("/admin/memory/items?query=TypeScript")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == target


@pytest.mark.asyncio
async def test_get_item_returns_parents(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    parent_id = await _insert(repo, kind="episode", content="origin episode")
    child_id = await _insert(repo, kind="claim", content="derived claim")
    await repo.insert_parent_edge(child_id, parent_id, "evidence")

    client = _build_client(_FakeMemoryService(conn))

    resp = client.get(f"/admin/memory/items/{child_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["item"]["id"] == child_id
    assert len(data["parents"]) == 1
    assert data["parents"][0]["parent_id"] == parent_id
    assert data["parents"][0]["role"] == "evidence"
    assert data["parents"][0]["parent"]["content"] == "origin episode"


@pytest.mark.asyncio
async def test_get_item_404(conn: aiosqlite.Connection):
    client = _build_client(_FakeMemoryService(conn))
    resp = client.get("/admin/memory/items/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stats_returns_counts_per_kind_status(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    await _insert(repo, kind="episode", content="a")
    await _insert(repo, kind="episode", content="b")
    await _insert(repo, kind="claim", content="c", status="archived")

    client = _build_client(_FakeMemoryService(conn))
    resp = client.get("/admin/memory/stats")
    assert resp.status_code == 200
    counts = resp.json()["counts"]
    assert counts["episode"]["active"] == 2
    assert counts["claim"]["archived"] == 1
    assert counts["claim"]["active"] == 0


@pytest.mark.asyncio
async def test_invalid_kind_returns_400(conn: aiosqlite.Connection):
    client = _build_client(_FakeMemoryService(conn))
    resp = client.get("/admin/memory/items?kinds=bogus")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_graph_endpoint_returns_parent_and_child_edges(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    episode_id = await _insert(repo, kind="episode", content="source episode")
    claim_id = await _insert(repo, kind="claim", content="derived claim")
    skill_id = await _insert(repo, kind="skill", content="usable skill")
    await repo.insert_parent_edge(claim_id, episode_id, "evidence")
    await repo.insert_parent_edge(skill_id, claim_id, "evidence")

    client = _build_client(_FakeMemoryService(conn))
    resp = client.get(f"/admin/memory/items/{claim_id}/graph?depth=1")
    assert resp.status_code == 200
    data = resp.json()
    assert {node["id"] for node in data["nodes"]} == {episode_id, claim_id, skill_id}
    assert {(edge["child_id"], edge["parent_id"], edge["role"]) for edge in data["edges"]} == {
        (claim_id, episode_id, "evidence"),
        (skill_id, claim_id, "evidence"),
    }


@pytest.mark.asyncio
async def test_today_endpoint_surfaces_review_queues(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    proposal_id = await _insert(repo, kind="proposal", content="draft skill", tags=["proposal-status:open"])
    await _insert(repo, kind="proposal", content="approved draft", tags=["proposal-status:approved"])
    await _insert(repo, kind="proposal", content="rejected draft", tags=["proposal-status:rejected"])
    skill_id = await _insert(repo, kind="skill", content="accepted skill")
    claim_id = await _insert(repo, kind="claim", content="uncertain claim", confidence=0.4)
    superseded_id = await _insert(repo, kind="claim", content="old claim", status="superseded")

    client = _build_client(_FakeMemoryService(conn))
    resp = client.get("/admin/memory/today")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["id"] for item in data["pending_proposals"]] == [proposal_id]
    assert [item["id"] for item in data["new_skills"]] == [skill_id]
    assert [item["id"] for item in data["low_confidence_claims"]] == [claim_id]
    assert [item["id"] for item in data["recent_corrections"]] == [superseded_id]


@pytest.mark.asyncio
async def test_skills_endpoint_and_enable_toggle(conn: aiosqlite.Connection):
    repo = MemoryItemsRepository(conn)
    skill_id = await _insert(repo, kind="skill", content="skill body")

    client = _build_client(_FakeMemoryService(conn))
    resp = client.get("/admin/memory/skills")
    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()["skills"]] == [skill_id]

    disable = client.post(f"/admin/memory/skills/{skill_id}/enabled", json={"enabled": False})
    assert disable.status_code == 200
    assert disable.json()["skill"]["status"] == "archived"

    hidden = client.get("/admin/memory/skills?include_disabled=false")
    assert hidden.status_code == 200
    assert hidden.json()["skills"] == []
