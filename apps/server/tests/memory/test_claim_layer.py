from __future__ import annotations

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
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.pattern_finder import (
    PatternFinder,
    PatternFinderPass2RunResult,
    _entity_overlap,
    claim_similarity,
    render_pass2_prompt,
)
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.store.base import GraphDatabase
from ntrp.server.deps import require_pattern_finder
from ntrp.server.routers.admin_memory import router as admin_memory_router

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
CLAIM_TEXT = "User prefers direct production debugging from runtime evidence."


class _FakeSummaryClient:
    def __init__(self, response: str = CLAIM_TEXT):
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


async def _insert_item(
    conn: aiosqlite.Connection,
    content: str,
    *,
    kind: str = "observation",
    embedding: np.ndarray,
    tags: list[str] | None = None,
    valid_from: datetime = NOW,
    confidence: float = 0.6,
    status: str = "active",
    scope: str = "user",
    source_refs: list[dict] | None = None,
) -> str:
    return await MemoryItemsRepository(conn).insert_item(
        MemoryItemInsert(
            kind=kind,
            content=content,
            provenance="inferred",
            source_refs=source_refs or [{"kind": "test", "ref": content, "captured_at": valid_from.isoformat()}],
            confidence=confidence,
            status=status,
            scope=scope,
            tags=tags or [],
            embedding=embedding,
            valid_from=valid_from,
        )
    )


async def _rows(conn: aiosqlite.Connection, *, kind: str | None = None) -> list[aiosqlite.Row]:
    where = "WHERE kind = ?" if kind else ""
    params = (kind,) if kind else ()
    return await conn.execute_fetchall(f"SELECT * FROM memory_items {where} ORDER BY created_at, id", params)


async def _run_pass2(
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
    return await finder.run_pass2(window_days=30, scope="user", now=now)


@pytest.mark.asyncio
async def test_run_pass2_produces_claim_from_two_observations_with_shared_tags(conn: aiosqlite.Connection):
    await _insert_item(conn, "runtime first", embedding=_vec(0), tags=["dex", "prod"], confidence=0.6)
    await _insert_item(conn, "runtime second", embedding=_cos_vec(0.9), tags=["dex", "prod"], confidence=0.8)

    result = await _run_pass2(conn)

    assert result.observations_considered == 2
    assert result.existing_claims_considered == 0
    assert result.clusters_found == 1
    assert result.claims_written == 1
    claims = await _rows(conn, kind="claim")
    assert len(claims) == 1
    assert claims[0]["content"] == CLAIM_TEXT
    assert claims[0]["confidence"] == pytest.approx(0.49)


@pytest.mark.asyncio
async def test_run_pass2_skips_singleton_observation_clusters(conn: aiosqlite.Connection):
    await _insert_item(conn, "only one observation", embedding=_vec(0), tags=["solo"])

    result = await _run_pass2(conn)

    assert result.clusters_found == 0
    assert result.claims_written == 0
    assert await _rows(conn, kind="claim") == []


@pytest.mark.asyncio
async def test_run_pass2_writes_evidence_edges_for_each_source_observation(conn: aiosqlite.Connection):
    first = await _insert_item(conn, "edge first", embedding=_vec(0), tags=["edge"])
    second = await _insert_item(conn, "edge second", embedding=_cos_vec(0.9), tags=["edge"])

    await _run_pass2(conn)

    claim = (await _rows(conn, kind="claim"))[0]
    edges = await MemoryItemsRepository(conn).list_parent_edges(claim["id"])
    assert {(edge.parent_id, edge.role) for edge in edges} == {(first, "evidence"), (second, "evidence")}


@pytest.mark.asyncio
async def test_run_pass2_idempotent_when_evidence_set_unchanged(conn: aiosqlite.Connection):
    await _insert_item(conn, "idem first", embedding=_vec(0), tags=["idem"])
    await _insert_item(conn, "idem second", embedding=_cos_vec(0.9), tags=["idem"])

    first = await _run_pass2(conn)
    second = await _run_pass2(conn)

    assert first.claims_written == 1
    assert second.claims_written == 0
    assert len(await _rows(conn, kind="claim")) == 1


@pytest.mark.asyncio
async def test_run_pass2_supersedes_old_claim_when_evidence_grows_strictly(conn: aiosqlite.Connection):
    old_a = await _insert_item(conn, "grow first", embedding=_vec(0), tags=["grow"])
    old_b = await _insert_item(conn, "grow second", embedding=_cos_vec(0.9), tags=["grow"])
    await _run_pass2(conn)
    old_claim = (await _rows(conn, kind="claim"))[0]["id"]
    await _insert_item(conn, "grow third", embedding=_cos_vec(0.92), tags=["grow"])

    result = await _run_pass2(conn)

    rows = await _rows(conn, kind="claim")
    old_row = next(row for row in rows if row["id"] == old_claim)
    new_row = next(row for row in rows if row["id"] != old_claim)
    assert result.claims_written == 1
    assert result.claims_superseded == 1
    assert old_row["status"] == "superseded"
    edges = await MemoryItemsRepository(conn).list_parent_edges(new_row["id"])
    assert {(edge.parent_id, edge.role) for edge in edges} >= {
        (old_a, "evidence"),
        (old_b, "evidence"),
        (old_claim, "supersedes"),
    }


@pytest.mark.asyncio
async def test_run_pass2_does_not_supersede_overlapping_but_disjoint_evidence(conn: aiosqlite.Connection):
    first = await _insert_item(conn, "old claim evidence", embedding=_vec(3), tags=["oldpolicy"])
    old_claim = await _insert_item(conn, "User has an old policy claim.", kind="claim", embedding=_vec(3), tags=["oldpolicy"])
    await MemoryItemsRepository(conn).insert_parent_edge(old_claim, first, "evidence")
    await _insert_item(conn, "new related one", embedding=_cos_vec(0.9), tags=["policy"])
    await _insert_item(conn, "new related two", embedding=_cos_vec(0.88), tags=["policy"])

    result = await _run_pass2(conn)

    assert result.claims_written == 1
    assert result.claims_superseded == 0
    old_row = next(row for row in await _rows(conn, kind="claim") if row["id"] == old_claim)
    assert old_row["status"] == "active"


@pytest.mark.asyncio
async def test_run_pass2_rejects_no_claim_summary(conn: aiosqlite.Connection):
    await _insert_item(conn, "reject first", embedding=_vec(0), tags=["reject"])
    await _insert_item(conn, "reject second", embedding=_cos_vec(0.9), tags=["reject"])

    result = await _run_pass2(conn, summary=_FakeSummaryClient("NO_CLAIM"))

    assert result.clusters_found == 1
    assert result.claims_written == 0
    assert await _rows(conn, kind="claim") == []


@pytest.mark.asyncio
async def test_run_pass2_handles_empty_observation_set(conn: aiosqlite.Connection):
    result = await _run_pass2(conn)

    assert result.to_dict() | {"elapsed_ms": result.elapsed_ms} == {
        "window_days": 30,
        "scope": "user",
        "observations_considered": 0,
        "existing_claims_considered": 0,
        "clusters_found": 0,
        "claims_written": 0,
        "claims_superseded": 0,
        "elapsed_ms": result.elapsed_ms,
    }


@pytest.mark.asyncio
async def test_run_pass2_window_days_filters_old_observations(conn: aiosqlite.Connection):
    await _insert_item(conn, "inside first", embedding=_vec(0), tags=["inside"], valid_from=NOW - timedelta(days=1))
    await _insert_item(conn, "inside second", embedding=_cos_vec(0.9), tags=["inside"], valid_from=NOW - timedelta(days=1))
    await _insert_item(conn, "outside first", embedding=_vec(0), tags=["outside"], valid_from=NOW - timedelta(days=60))
    await _insert_item(conn, "outside second", embedding=_cos_vec(0.9), tags=["outside"], valid_from=NOW - timedelta(days=60))

    result = await _run_pass2(conn, now=NOW)

    assert result.observations_considered == 2
    assert result.clusters_found == 1
    assert result.claims_written == 1


@pytest.mark.asyncio
async def test_pass2_includes_existing_claims_in_input_set_for_chaining(conn: aiosqlite.Connection):
    summary = _FakeSummaryClient()
    await _insert_item(conn, "chain observation", embedding=_vec(0), tags=["chain"])
    prior_claim = await _insert_item(
        conn,
        "User already has a prior chain claim.",
        kind="claim",
        embedding=_cos_vec(0.9),
        tags=["chain"],
    )

    result = await _run_pass2(conn, summary=summary)

    assert result.observations_considered == 1
    assert result.existing_claims_considered == 1
    assert result.claims_written == 1
    assert "[claim] User already has a prior chain claim." in summary.prompts[0]
    claim = next(row for row in await _rows(conn, kind="claim") if row["id"] != prior_claim)
    edges = await MemoryItemsRepository(conn).list_parent_edges(claim["id"])
    assert any(edge.parent_id == prior_claim and edge.role == "evidence" for edge in edges)


@pytest.mark.asyncio
async def test_pass2_claim_surfaces_with_claim_match_reason_in_retrieval(conn: aiosqlite.Connection):
    await _insert_item(
        conn,
        "User prefers runtime evidence for production debugging.",
        kind="claim",
        embedding=_vec(0),
        tags=["runtime"],
        confidence=0.8,
    )
    retrieval = MemoryRetrieval(conn, _FakeEmbedder({"runtime evidence": _vec(0)}))

    bundle = await retrieval.search(
        MemoryActivationRequest(
            query="runtime evidence",
            kinds=["claim"],
            scope="user",
            limit=1,
            budget_chars=500,
            record_access=False,
        ),
        now=NOW,
    )

    assert bundle.candidates[0].kind == "claim"
    assert "claim_match" in bundle.candidates[0].reasons


def test_claim_similarity_weights_match_design_spec():
    left = SimpleNamespace(embedding=_vec(0), tags=["a", "b"], valid_from=NOW, created_at=NOW)
    right = SimpleNamespace(embedding=_cos_vec(0.5), tags=["b", "c"], valid_from=NOW + timedelta(days=7), created_at=NOW + timedelta(days=7))

    assert claim_similarity(left, right) == pytest.approx(0.65 * 0.5 + 0.20 * (1 / 3) + 0.15 * 0.0)


def test_entity_overlap_returns_zero_when_either_side_empty():
    left = SimpleNamespace(tags=["entity:dex"])
    right = SimpleNamespace(tags=[])

    assert _entity_overlap(left, right) == 0.0


def test_render_pass2_prompt_marks_observations_and_claims_in_time_order():
    early = SimpleNamespace(kind="claim", content="Older claim.", created_at=NOW - timedelta(days=1))
    late = SimpleNamespace(kind="observation", content="Newer observation.", created_at=NOW)

    prompt = render_pass2_prompt([late, early])

    assert prompt.index("[claim] Older claim.") < prompt.index("[observation] Newer observation.")


def test_admin_endpoint_dispatches_pass_parameter():
    app = FastAPI()
    app.include_router(admin_memory_router)

    class _FakePatternFinder:
        async def run_pass1(self, *, window_days: int, scope: str, limit: int = 500):
            return SimpleNamespace(to_dict=lambda: {"pass": 1, "window_days": window_days, "scope": scope})

        async def run_pass2(self, *, window_days: int, scope: str, limit: int = 500):
            return PatternFinderPass2RunResult(
                window_days=window_days,
                scope=scope,
                observations_considered=2,
                existing_claims_considered=1,
                clusters_found=1,
                claims_written=1,
                claims_superseded=0,
                elapsed_ms=3,
            )

    app.dependency_overrides[require_pattern_finder] = lambda: _FakePatternFinder()
    client = TestClient(app)

    pass1 = client.post("/admin/memory/pattern-finder/run", json={"pass": 1, "window_days": 3, "scope": "user"})
    pass2 = client.post("/admin/memory/pattern-finder/run", json={"pass": 2, "window_days": 30, "scope": "user"})
    both = client.post("/admin/memory/pattern-finder/run", json={"pass": "both", "window_days": 30, "scope": "user"})

    assert pass1.json() == {"pass1": {"pass": 1, "window_days": 3, "scope": "user"}}
    assert pass2.json()["pass2"]["claims_written"] == 1
    assert set(both.json()) == {"pass1", "pass2"}
