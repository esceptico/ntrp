from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import ntrp.database as database
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.memory.contradictions import CROSS_SCOPE_OVERRIDE_TAG, ContradictionWatcher
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.pattern_finder import PatternFinder
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.store.base import GraphDatabase
from ntrp.server.deps import require_pattern_finder
from ntrp.server.routers.admin_memory import router as admin_memory_router

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)


class _FakeEmbedder:
    def __init__(self, vectors: dict[str, np.ndarray] | None = None):
        self.config = SimpleNamespace(dim=TEST_EMBEDDING_DIM)
        self.vectors = dict(vectors or {})

    async def embed_one(self, text: str) -> np.ndarray:
        return self.vectors.get(text, _vec(0))


class _FakeJudge:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class _FakeSummaryClient:
    async def __call__(self, prompt: str) -> str:
        return "User avoids Nike for running shoes."


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


async def _insert_claim(
    conn: aiosqlite.Connection,
    content: str,
    *,
    item_id: str | None = None,
    embedding: np.ndarray | None = None,
    tags: list[str] | None = None,
    scope: str = "user",
    valid_from: datetime = NOW,
    created_at: datetime | None = None,
    status: str = "active",
) -> str:
    repo = MemoryItemsRepository(conn)
    claim_id = await repo.insert_item(
        MemoryItemInsert(
            kind="claim",
            content=content,
            provenance="inferred",
            source_refs=[],
            confidence=0.8,
            status=status,
            scope=scope,
            tags=tags or [],
            embedding=embedding if embedding is not None else _vec(0),
            valid_from=valid_from,
        )
    )
    if item_id is not None:
        await conn.execute("UPDATE memory_items SET id = ? WHERE id = ?", (item_id, claim_id))
        await conn.execute("UPDATE memory_items_vec SET item_id = ? WHERE item_id = ?", (item_id, claim_id))
        claim_id = item_id
    if created_at is not None:
        await conn.execute(
            "UPDATE memory_items SET created_at = ?, updated_at = ? WHERE id = ?",
            (created_at.isoformat(), created_at.isoformat(), claim_id),
        )
    await conn.commit()
    return claim_id


async def _row(conn: aiosqlite.Connection, item_id: str) -> aiosqlite.Row:
    rows = await conn.execute_fetchall("SELECT * FROM memory_items WHERE id = ?", (item_id,))
    assert rows
    return rows[0]


async def _edges(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall(
        'SELECT child_id, parent_id, role FROM memory_item_parents ORDER BY child_id, parent_id, role'
    )


def _watcher(conn: aiosqlite.Connection, *, judge: _FakeJudge | None = None) -> ContradictionWatcher:
    # Default to an "opposed" judge: the watcher now defers every persistence decision
    # to the LLM, so tests that assert a contradiction is written supply that verdict.
    return ContradictionWatcher(
        repo=MemoryItemsRepository(conn),
        embedder=_FakeEmbedder(),
        judge_client=judge or _FakeJudge("opposed\nThe claims conflict."),
    )


@pytest.mark.asyncio
async def test_scan_for_new_claim_writes_contradicts_edge_within_scope(conn: aiosqlite.Connection):
    old = await _insert_claim(
        conn,
        "User uses Nike for running shoes.",
        tags=["nike"],
        created_at=NOW - timedelta(minutes=2),
    )
    new = await _insert_claim(
        conn,
        "User avoids Nike for running shoes.",
        embedding=_cos_vec(0.95),
        tags=["nike"],
        created_at=NOW,
    )

    candidates = await _watcher(conn).scan_for_new_claim(new, scope="user")

    assert [(candidate.new_claim_id, candidate.old_claim_id) for candidate in candidates] == [(new, old)]
    assert (new, old, "contradicts") in [(row["child_id"], row["parent_id"], row["role"]) for row in await _edges(conn)]


@pytest.mark.asyncio
async def test_scan_for_new_claim_writes_supersedes_edge_and_flips_status_within_scope(conn: aiosqlite.Connection):
    old = await _insert_claim(
        conn,
        "User uses Nike for running shoes.",
        tags=["nike"],
        created_at=NOW - timedelta(minutes=2),
    )
    new = await _insert_claim(
        conn,
        "User avoids Nike for running shoes.",
        embedding=_cos_vec(0.95),
        tags=["nike"],
        created_at=NOW,
    )

    await _watcher(conn).scan_for_new_claim(new, scope="user")

    edge_tuples = [(row["child_id"], row["parent_id"], row["role"]) for row in await _edges(conn)]
    assert (new, old, "supersedes") in edge_tuples
    old_row = await _row(conn, old)
    assert old_row["status"] == "superseded"
    assert old_row["invalid_at"] is not None


@pytest.mark.asyncio
async def test_scan_for_new_claim_cross_scope_writes_only_contradicts_edge(conn: aiosqlite.Connection):
    old = await _insert_claim(
        conn,
        "User uses Nike for running shoes.",
        tags=["nike"],
        scope="user",
        created_at=NOW - timedelta(minutes=2),
    )
    new = await _insert_claim(
        conn,
        "In ntrp, user avoids Nike for running shoes.",
        embedding=_cos_vec(0.95),
        tags=["nike"],
        scope="project:ntrp",
        created_at=NOW,
    )

    await _watcher(conn).scan_for_new_claim(new, scope="project:ntrp")

    edge_tuples = [(row["child_id"], row["parent_id"], row["role"]) for row in await _edges(conn)]
    assert (new, old, "contradicts") in edge_tuples
    assert (new, old, "supersedes") not in edge_tuples
    assert (await _row(conn, old))["status"] == "active"
    assert (await _row(conn, new))["status"] == "active"


@pytest.mark.asyncio
async def test_scan_for_new_user_claim_detects_existing_project_claim(conn: aiosqlite.Connection):
    old = await _insert_claim(
        conn,
        "In ntrp, user avoids Nike for running shoes.",
        tags=["nike"],
        scope="project:ntrp",
        created_at=NOW - timedelta(minutes=2),
    )
    new = await _insert_claim(
        conn,
        "User uses Nike for running shoes.",
        embedding=_cos_vec(0.95),
        tags=["nike"],
        scope="user",
        created_at=NOW,
    )

    candidates = await _watcher(conn).scan_for_new_claim(new, scope="user")

    assert len(candidates) == 1
    assert candidates[0].cross_scope is True
    edge_tuples = [(row["child_id"], row["parent_id"], row["role"]) for row in await _edges(conn)]
    assert (new, old, "contradicts") in edge_tuples
    assert (new, old, "supersedes") not in edge_tuples
    assert (await _row(conn, old))["status"] == "active"
    assert (await _row(conn, new))["status"] == "active"
    assert CROSS_SCOPE_OVERRIDE_TAG in json.loads((await _row(conn, new))["tags"])


@pytest.mark.asyncio
async def test_scan_for_new_claim_cross_scope_tags_metadata_overrides(conn: aiosqlite.Connection):
    await _insert_claim(
        conn,
        "User uses Nike for running shoes.",
        tags=["nike"],
        scope="user",
        created_at=NOW - timedelta(minutes=2),
    )
    new = await _insert_claim(
        conn,
        "In ntrp, user avoids Nike for running shoes.",
        embedding=_cos_vec(0.95),
        tags=["nike"],
        scope="project:ntrp",
        created_at=NOW,
    )

    await _watcher(conn).scan_for_new_claim(new, scope="project:ntrp")

    assert CROSS_SCOPE_OVERRIDE_TAG in json.loads((await _row(conn, new))["tags"])


@pytest.mark.asyncio
async def test_scan_idempotent_skips_existing_contradicts_edges(conn: aiosqlite.Connection):
    await _insert_claim(conn, "User uses Nike.", tags=["nike"], created_at=NOW - timedelta(minutes=2))
    new = await _insert_claim(conn, "User avoids Nike.", embedding=_cos_vec(0.95), tags=["nike"], created_at=NOW)

    first = await _watcher(conn).scan_for_new_claim(new, scope="user")
    second = await _watcher(conn).scan_for_new_claim(new, scope="user")

    assert len(first) == 1
    assert second == []
    assert len([row for row in await _edges(conn) if row["role"] == "contradicts"]) == 1


@pytest.mark.asyncio
async def test_scan_skips_claims_with_no_shared_entities(conn: aiosqlite.Connection):
    old = await _insert_claim(conn, "User uses Nike.", tags=["nike"], created_at=NOW - timedelta(minutes=2))
    new = await _insert_claim(conn, "User avoids Nike.", embedding=_cos_vec(0.95), tags=["adidas"], created_at=NOW)

    candidates = await _watcher(conn).scan_for_new_claim(new, scope="user")

    assert candidates == []
    assert await _edges(conn) == []
    assert (await _row(conn, old))["status"] == "active"


@pytest.mark.asyncio
async def test_judge_is_consulted_for_every_recalled_candidate(conn: aiosqlite.Connection):
    judge = _FakeJudge("opposed\nThe preference values conflict.")
    tea = await _insert_claim(conn, "User prefers tea.", tags=["drink"], created_at=NOW - timedelta(minutes=2))
    # No lexical negation and no embedding signal — the judge alone decides this is opposed.
    coffee = await _insert_claim(conn, "User prefers coffee.", embedding=_vec(0), tags=["drink"], created_at=NOW)

    candidates = await _watcher(conn, judge=judge).scan_for_new_claim(coffee, scope="user")

    assert len(judge.prompts) == 1
    assert "User prefers tea." in judge.prompts[0]
    assert "User prefers coffee." in judge.prompts[0]
    assert [(c.new_claim_id, c.old_claim_id, c.judge_verdict) for c in candidates] == [(coffee, tea, "opposed")]
    assert any(row["child_id"] == coffee and row["parent_id"] == tea for row in await _edges(conn))


@pytest.mark.asyncio
async def test_compatible_verdict_writes_no_edge(conn: aiosqlite.Connection):
    judge = _FakeJudge("compatible\nDifferent contexts.")
    old = await _insert_claim(conn, "User uses Nike.", tags=["nike"], created_at=NOW - timedelta(minutes=2))
    new = await _insert_claim(conn, "User avoids Nike.", embedding=_cos_vec(0.95), tags=["nike"], created_at=NOW)

    candidates = await _watcher(conn, judge=judge).scan_for_new_claim(new, scope="user")

    assert candidates == []
    assert await _edges(conn) == []
    assert (await _row(conn, old))["status"] == "active"


@pytest.mark.asyncio
async def test_judge_unclear_verdict_is_treated_as_compatible(conn: aiosqlite.Connection):
    judge = _FakeJudge("unclear\nBoth could be contextual.")
    old = await _insert_claim(conn, "User prefers tea.", tags=["drink"], created_at=NOW - timedelta(minutes=2))
    new = await _insert_claim(conn, "User prefers coffee.", embedding=_vec(0), tags=["drink"], created_at=NOW)

    candidates = await _watcher(conn, judge=judge).scan_for_new_claim(new, scope="user")

    assert candidates == []
    assert await _edges(conn) == []
    assert (await _row(conn, old))["status"] == "active"


def test_admin_scan_endpoint_processes_window():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakeWatcher:
        def __init__(self):
            self.calls: list[tuple[str, int, int]] = []

        async def scan_window(self, *, scope: str, window_days: int, limit: int = 500):
            self.calls.append((scope, window_days, limit))
            return [SimpleNamespace(new_claim_id="new", old_claim_id="old", cross_scope=False)]

    watcher = _FakeWatcher()
    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(contradiction_watcher=watcher)
    response = TestClient(app).post("/admin/memory/contradictions/scan", json={"scope": "user", "window_days": 7})

    assert response.status_code == 200
    assert response.json() == {"scope": "user", "window_days": 7, "claims_scanned": 1, "contradictions_found": 1}
    assert watcher.calls == [("user", 7, 500)]


@pytest.mark.asyncio
async def test_undo_endpoint_restores_old_claim_status_within_scope(conn: aiosqlite.Connection):
    old = await _insert_claim(conn, "User uses Nike.", tags=["nike"], created_at=NOW - timedelta(minutes=2))
    new = await _insert_claim(conn, "User avoids Nike.", embedding=_cos_vec(0.95), tags=["nike"], created_at=NOW)
    watcher = _watcher(conn)
    await watcher.scan_for_new_claim(new, scope="user")

    result = await watcher.undo(child_id=new, parent_id=old)

    assert result == {"already_undone": False, "restored": True, "cross_scope": False}
    assert await _edges(conn) == []
    old_row = await _row(conn, old)
    assert old_row["status"] == "active"
    assert old_row["invalid_at"] is None


@pytest.mark.asyncio
async def test_undo_does_not_restore_claim_still_superseded_by_another_active_claim(conn: aiosqlite.Connection):
    old = await _insert_claim(conn, "User uses Nike.", tags=["nike"], created_at=NOW - timedelta(minutes=3))
    new_a = await _insert_claim(conn, "User avoids Nike.", embedding=_cos_vec(0.95), tags=["nike"], created_at=NOW - timedelta(minutes=1))
    new_b = await _insert_claim(conn, "User no longer buys Nike.", embedding=_cos_vec(0.95), tags=["nike"], created_at=NOW)
    watcher = _watcher(conn)
    await watcher.scan_for_new_claim(new_a, scope="user")
    repo = MemoryItemsRepository(conn)
    await repo.insert_parent_edge(new_b, old, "supersedes")
    await conn.execute(
        "UPDATE memory_items SET status = 'superseded', invalid_at = ? WHERE id = ?",
        (NOW.isoformat(), old),
    )
    await conn.commit()

    result = await watcher.undo(child_id=new_a, parent_id=old)

    assert result == {"already_undone": False, "restored": False, "cross_scope": False}
    old_row = await _row(conn, old)
    assert old_row["status"] == "superseded"
    assert old_row["invalid_at"] is not None
    assert (new_b, old, "supersedes") in [tuple(edge) for edge in await _edges(conn)]


@pytest.mark.asyncio
async def test_undo_endpoint_idempotent(conn: aiosqlite.Connection):
    old = await _insert_claim(conn, "User uses Nike.", tags=["nike"], created_at=NOW - timedelta(minutes=2))
    new = await _insert_claim(conn, "User avoids Nike.", embedding=_cos_vec(0.95), tags=["nike"], created_at=NOW)
    watcher = _watcher(conn)
    await watcher.scan_for_new_claim(new, scope="user")
    await watcher.undo(child_id=new, parent_id=old)

    result = await watcher.undo(child_id=new, parent_id=old)

    assert result == {"already_undone": True, "restored": False, "cross_scope": False}


@pytest.mark.asyncio
async def test_retrieval_renders_cross_scope_annotation(conn: aiosqlite.Connection):
    old = await _insert_claim(
        conn,
        "User generally uses Nike for running shoes.",
        tags=["nike"],
        scope="user",
        created_at=NOW - timedelta(minutes=2),
        embedding=_vec(1),
    )
    new = await _insert_claim(
        conn,
        "Projectscope claim says user avoids Nike for running shoes.",
        tags=["nike", CROSS_SCOPE_OVERRIDE_TAG],
        scope="project:ntrp",
        created_at=NOW,
        embedding=_vec(0),
    )
    await conn.execute(
        "INSERT INTO memory_item_parents (child_id, parent_id, role) VALUES (?, ?, 'contradicts')",
        (new, old),
    )
    await conn.commit()
    retrieval = MemoryRetrieval(conn, _FakeEmbedder({"projectscope": _vec(0)}))

    bundle = await retrieval.search(
        MemoryActivationRequest(
            query="projectscope",
            kinds=["claim"],
            scope="project:ntrp",
            limit=1,
            budget_chars=800,
            record_access=False,
        ),
        now=NOW,
    )

    assert "general (user): User generally uses Nike for running shoes." in bundle.prompt_context
    assert "in current scope (project:ntrp): Projectscope claim says user avoids Nike" in bundle.prompt_context


@pytest.mark.asyncio
async def test_pattern_finder_persist_claim_invokes_watcher_after_write(conn: aiosqlite.Connection):
    await MemoryItemsRepository(conn).insert_item(
        MemoryItemInsert(
            kind="observation",
            content="User uses Nike.",
            provenance="inferred",
            source_refs=[],
            confidence=0.6,
            scope="user",
            tags=["nike"],
            embedding=_vec(0),
            valid_from=NOW,
        )
    )
    await MemoryItemsRepository(conn).insert_item(
        MemoryItemInsert(
            kind="observation",
            content="User avoids Nike.",
            provenance="inferred",
            source_refs=[],
            confidence=0.6,
            scope="user",
            tags=["nike"],
            embedding=_cos_vec(0.95),
            valid_from=NOW,
        )
    )

    class _HookWatcher:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        async def scan_for_new_claim(self, claim_id: str, *, scope: str):
            rows = await conn.execute_fetchall("SELECT id FROM memory_items WHERE id = ?", (claim_id,))
            assert rows
            self.calls.append((claim_id, scope))
            return []

    hook = _HookWatcher()
    finder = PatternFinder(
        repo=MemoryItemsRepository(conn),
        summary_client=_FakeSummaryClient(),
        embedder=_FakeEmbedder({"User avoids Nike for running shoes.": _vec(0)}),
        contradiction_watcher=hook,
        sim_threshold=0.1,
    )

    result = await finder.run_pass2(window_days=30, scope="user", now=NOW)

    assert result.claims_written == 1
    assert len(hook.calls) == 1
