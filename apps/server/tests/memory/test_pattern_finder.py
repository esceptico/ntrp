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
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.pattern_finder import PatternFinder, PatternFinderRunResult
from ntrp.memory.store.base import GraphDatabase
from ntrp.server.deps import require_pattern_finder
from ntrp.server.routers.admin_memory import router as admin_memory_router

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)


class _FakeSummaryClient:
    def __init__(self, response: str = "The user repeated a pattern across these recent conversations."):
        self.response = response
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class _FakeEmbedder:
    def __init__(self, vectors: Mapping[str, np.ndarray] | None = None):
        self.config = SimpleNamespace(dim=TEST_EMBEDDING_DIM)
        self.vectors = dict(vectors or {})
        self.calls: list[str] = []

    async def embed_one(self, text: str) -> np.ndarray:
        self.calls.append(text)
        return self.vectors.get(text, _vec(0))


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


def _chain_c_vec() -> np.ndarray:
    vector = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    vector[0] = 0.5
    vector[1] = 2.0 / 3.0
    vector[2] = math.sqrt(1.0 - vector[0] ** 2 - vector[1] ** 2)
    return vector


async def _insert_episode(
    conn: aiosqlite.Connection,
    content: str,
    *,
    embedding: np.ndarray,
    tags: list[str] | None = None,
    valid_from: datetime = NOW,
    source_refs: list[dict] | None = None,
    scope: str = "user",
) -> str:
    return await MemoryItemsRepository(conn).insert_item(
        MemoryItemInsert(
            kind="episode",
            content=content,
            provenance="inferred",
            source_refs=source_refs or [{"kind": "chat_msg", "ref": content, "captured_at": valid_from.isoformat()}],
            confidence=0.5,
            status="active",
            scope=scope,
            tags=tags or [],
            embedding=embedding,
            valid_from=valid_from,
        )
    )


async def _memory_rows(conn: aiosqlite.Connection, *, kind: str | None = None) -> list[aiosqlite.Row]:
    where = "WHERE kind = ?" if kind else ""
    params = (kind,) if kind else ()
    return await conn.execute_fetchall(f"SELECT * FROM memory_items {where} ORDER BY created_at, id", params)


async def _run(
    conn: aiosqlite.Connection,
    *,
    summary: _FakeSummaryClient | None = None,
    embedder: _FakeEmbedder | None = None,
    now: datetime = NOW,
):
    summary = summary or _FakeSummaryClient()
    embedder = embedder or _FakeEmbedder()
    finder = PatternFinder(
        repo=MemoryItemsRepository(conn),
        summary_client=summary,
        embedder=embedder,
    )
    return await finder.run_pass1(window_days=7, scope="user", now=now)


@pytest.mark.asyncio
async def test_pattern_finder_emits_observation_for_two_similar_episodes(conn: aiosqlite.Connection):
    await _insert_episode(conn, "alpha one", embedding=_vec(0), tags=["alpha"])
    await _insert_episode(conn, "alpha two", embedding=_cos_vec(0.85), tags=["alpha"])

    result = await _run(conn)

    assert result.clusters_found == 1
    assert result.observations_written == 1
    observations = await _memory_rows(conn, kind="observation")
    assert len(observations) == 1
    assert observations[0]["confidence"] == 0.6
    edges = await MemoryItemsRepository(conn).list_parent_edges(observations[0]["id"])
    assert sorted(edge.role for edge in edges) == ["evidence", "evidence"]


@pytest.mark.asyncio
async def test_pattern_finder_drops_singleton_clusters(conn: aiosqlite.Connection):
    await _insert_episode(conn, "pair one", embedding=_vec(0), tags=["pair"])
    await _insert_episode(conn, "pair two", embedding=_cos_vec(0.85), tags=["pair"])
    await _insert_episode(conn, "isolated", embedding=_vec(3), tags=["other"])

    result = await _run(conn)

    assert result.episodes_considered == 3
    assert result.clusters_found == 1
    assert result.observations_written == 1


@pytest.mark.asyncio
async def test_pattern_finder_clusters_three_chained_episodes_via_single_link(conn: aiosqlite.Connection):
    await _insert_episode(conn, "chain a", embedding=_vec(0), tags=["chain"])
    await _insert_episode(conn, "chain b", embedding=_cos_vec(0.8), tags=["chain"])
    await _insert_episode(conn, "chain c", embedding=_chain_c_vec(), tags=["chain"])

    result = await _run(conn)

    assert result.clusters_found == 1
    observations = await _memory_rows(conn, kind="observation")
    edges = await MemoryItemsRepository(conn).list_parent_edges(observations[0]["id"])
    assert len([edge for edge in edges if edge.role == "evidence"]) == 3


@pytest.mark.asyncio
async def test_pattern_finder_respects_window_days(conn: aiosqlite.Connection):
    await _insert_episode(conn, "inside one", embedding=_vec(0), tags=["inside"], valid_from=NOW - timedelta(days=1))
    await _insert_episode(conn, "inside two", embedding=_cos_vec(0.85), tags=["inside"], valid_from=NOW - timedelta(days=1))
    await _insert_episode(conn, "outside one", embedding=_vec(0), tags=["outside"], valid_from=NOW - timedelta(days=10))
    await _insert_episode(conn, "outside two", embedding=_cos_vec(0.85), tags=["outside"], valid_from=NOW - timedelta(days=10))

    result = await _run(conn)

    assert result.episodes_considered == 2
    assert result.clusters_found == 1
    observations = await _memory_rows(conn, kind="observation")
    source_refs = json.loads(observations[0]["source_refs"])
    assert {ref["ref"] for ref in source_refs} == {"inside one", "inside two"}


@pytest.mark.asyncio
async def test_pattern_finder_skips_observation_when_summary_returns_no_pattern(conn: aiosqlite.Connection):
    await _insert_episode(conn, "alpha one", embedding=_vec(0), tags=["alpha"])
    await _insert_episode(conn, "alpha two", embedding=_cos_vec(0.85), tags=["alpha"])

    result = await _run(conn, summary=_FakeSummaryClient("NO_PATTERN"))

    assert result.clusters_found == 1
    assert result.observations_written == 0
    assert await _memory_rows(conn, kind="observation") == []


@pytest.mark.asyncio
async def test_pattern_finder_rejects_short_or_refusal_summaries(conn: aiosqlite.Connection):
    await _insert_episode(conn, "alpha one", embedding=_vec(0), tags=["alpha"])
    await _insert_episode(conn, "alpha two", embedding=_cos_vec(0.85), tags=["alpha"])
    assert (await _run(conn, summary=_FakeSummaryClient("too short"))).observations_written == 0

    await conn.execute("DELETE FROM memory_items")
    await conn.commit()
    await _insert_episode(conn, "beta one", embedding=_vec(0), tags=["beta"])
    await _insert_episode(conn, "beta two", embedding=_cos_vec(0.85), tags=["beta"])
    result = await _run(conn, summary=_FakeSummaryClient("I cannot infer a pattern from this input."))

    assert result.observations_written == 0


@pytest.mark.asyncio
async def test_pattern_finder_is_idempotent_on_unchanged_clusters(conn: aiosqlite.Connection):
    await _insert_episode(conn, "alpha one", embedding=_vec(0), tags=["alpha"])
    await _insert_episode(conn, "alpha two", embedding=_cos_vec(0.85), tags=["alpha"])

    first = await _run(conn)
    second = await _run(conn)

    assert first.observations_written == 1
    assert second.observations_written == 0
    assert len(await _memory_rows(conn, kind="observation")) == 1


@pytest.mark.asyncio
async def test_pattern_finder_supersedes_observation_when_cluster_grows(conn: aiosqlite.Connection):
    await _insert_episode(conn, "alpha one", embedding=_vec(0), tags=["alpha"])
    await _insert_episode(conn, "alpha two", embedding=_cos_vec(0.85), tags=["alpha"])
    await _run(conn)
    old_observation = (await _memory_rows(conn, kind="observation"))[0]["id"]
    await _insert_episode(conn, "alpha three", embedding=_cos_vec(0.9), tags=["alpha"])

    result = await _run(conn)

    rows = await _memory_rows(conn, kind="observation")
    old_row = next(row for row in rows if row["id"] == old_observation)
    new_row = next(row for row in rows if row["id"] != old_observation)
    assert result.observations_written == 1
    assert result.observations_superseded == 1
    assert old_row["status"] == "superseded"
    assert old_row["invalid_at"] is not None
    edges = await MemoryItemsRepository(conn).list_parent_edges(new_row["id"])
    assert len([edge for edge in edges if edge.role == "evidence"]) == 3
    assert [(edge.parent_id, edge.role) for edge in edges if edge.role == "supersedes"] == [
        (old_observation, "supersedes")
    ]


@pytest.mark.asyncio
async def test_pattern_finder_uses_tag_jaccard_to_break_low_cosine_ties(conn: aiosqlite.Connection):
    await _insert_episode(conn, "tag one", embedding=_vec(0), tags=["shared"], valid_from=NOW)
    await _insert_episode(conn, "tag two", embedding=_cos_vec(0.72), tags=["shared"], valid_from=NOW - timedelta(days=7))

    result = await _run(conn, now=NOW)

    assert result.clusters_found == 1
    assert result.observations_written == 1


@pytest.mark.asyncio
async def test_pattern_finder_uses_temporal_proximity_for_low_similarity_pairs(conn: aiosqlite.Connection):
    await _insert_episode(conn, "time one", embedding=_vec(0), valid_from=NOW)
    await _insert_episode(conn, "time two", embedding=_cos_vec(0.86), valid_from=NOW)

    result = await _run(conn, now=NOW)

    assert result.clusters_found == 1
    assert result.observations_written == 1


@pytest.mark.asyncio
async def test_pattern_finder_merges_source_refs_across_cluster(conn: aiosqlite.Connection):
    shared_ref = {"kind": "chat_msg", "ref": "shared", "captured_at": NOW.isoformat()}
    await _insert_episode(
        conn,
        "refs one",
        embedding=_vec(0),
        tags=["refs"],
        source_refs=[shared_ref, {"kind": "chat_msg", "ref": "a", "captured_at": NOW.isoformat()}],
    )
    await _insert_episode(
        conn,
        "refs two",
        embedding=_cos_vec(0.85),
        tags=["refs"],
        source_refs=[shared_ref, {"kind": "chat_msg", "ref": "b", "captured_at": NOW.isoformat()}],
    )

    await _run(conn)

    observation = (await _memory_rows(conn, kind="observation"))[0]
    refs = [ref["ref"] for ref in json.loads(observation["source_refs"])]
    assert len(refs) == 3
    assert set(refs) == {"shared", "a", "b"}


@pytest.mark.asyncio
async def test_pattern_finder_aggregates_tags_across_cluster(conn: aiosqlite.Connection):
    await _insert_episode(conn, "tags one", embedding=_vec(0), tags=["zeta", "alpha"])
    await _insert_episode(conn, "tags two", embedding=_cos_vec(0.85), tags=["beta", "alpha"])

    await _run(conn)

    observation = (await _memory_rows(conn, kind="observation"))[0]
    assert json.loads(observation["tags"]) == ["alpha", "beta", "zeta"]


@pytest.mark.asyncio
async def test_pattern_finder_writes_role_evidence_parent_edges(conn: aiosqlite.Connection):
    first = await _insert_episode(conn, "edge one", embedding=_vec(0), tags=["edge"])
    second = await _insert_episode(conn, "edge two", embedding=_cos_vec(0.85), tags=["edge"])

    await _run(conn)

    observation = (await _memory_rows(conn, kind="observation"))[0]
    edges = await MemoryItemsRepository(conn).list_parent_edges(observation["id"])
    assert {(edge.parent_id, edge.role, edge.order) for edge in edges} == {
        (first, "evidence", None),
        (second, "evidence", None),
    }


@pytest.mark.asyncio
async def test_pattern_finder_run_handles_empty_window(conn: aiosqlite.Connection):
    result = await _run(conn)

    assert result.to_dict() | {"elapsed_ms": result.elapsed_ms} == {
        "window_days": 7,
        "scope": "user",
        "episodes_considered": 0,
        "clusters_found": 0,
        "observations_written": 0,
        "observations_superseded": 0,
        "elapsed_ms": result.elapsed_ms,
    }


def test_pattern_finder_admin_endpoint_returns_summary():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakePatternFinder:
        async def run_pass1(self, *, window_days: int, scope: str, limit: int = 500):
            return PatternFinderRunResult(
                window_days=window_days,
                scope=scope,
                episodes_considered=6,
                clusters_found=2,
                observations_written=2,
                observations_superseded=0,
                elapsed_ms=12,
            )

    app.dependency_overrides[require_pattern_finder] = lambda: _FakePatternFinder()

    response = TestClient(app).post("/admin/memory/pattern-finder/run", json={"window_days": 3, "scope": "user"})

    assert response.status_code == 200
    assert response.json() == {
        "window_days": 3,
        "scope": "user",
        "episodes_considered": 6,
        "clusters_found": 2,
        "observations_written": 2,
        "observations_superseded": 0,
        "elapsed_ms": 12,
    }
