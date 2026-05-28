from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.database import serialize_embedding
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import aiosqlite

EMBEDDING_DIM = 1536
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.asyncio


class FakeEmbedder:
    def __init__(self, vectors: Mapping[str, np.ndarray] | None = None, default: np.ndarray | None = None):
        self.vectors = dict(vectors or {})
        self.default = default if default is not None else _vec(0)

    async def embed_one(self, text: str) -> np.ndarray:
        return self.vectors.get(text, self.default)


@pytest_asyncio.fixture
async def conn(tmp_path: Path):
    db_conn = await database.connect(tmp_path / "memory.db", vec=True)
    db = GraphDatabase(db_conn, EMBEDDING_DIM)
    await db.init_schema()
    try:
        yield db_conn
    finally:
        await db_conn.close()


def _vec(index: int, *, dim: int = EMBEDDING_DIM, scale: float = 1.0) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    vector[index] = scale
    return vector


def _halfway_vec() -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vector[0] = 1.0
    vector[1] = 1.0
    return vector / np.linalg.norm(vector)


async def _insert_item(
    conn: aiosqlite.Connection,
    item_id: str,
    content: str,
    *,
    kind: str = "claim",
    scope: str = "user",
    status: str = "active",
    confidence: float = 0.5,
    tags: list[str] | None = None,
    source_refs: list[dict] | None = None,
    usage: dict | None = None,
    valid_from: datetime | None = None,
    invalid_at: datetime | None = None,
    created_at: datetime | None = None,
    embedding: np.ndarray | None = None,
) -> None:
    created = created_at or NOW
    await conn.execute(
        """
        INSERT INTO memory_items (
            id, kind, content, provenance, source_refs, confidence, status,
            valid_from, invalid_at, scope, tags, artifact_ref, usage, feedback,
            created_at, updated_at
        )
        VALUES (?, ?, ?, 'user_authored', ?, ?, ?, ?, ?, ?, ?, NULL, ?, '{}', ?, ?)
        """,
        (
            item_id,
            kind,
            content,
            json.dumps(source_refs or []),
            confidence,
            status,
            (valid_from or created).isoformat(),
            invalid_at.isoformat() if invalid_at else None,
            scope,
            json.dumps(tags or []),
            json.dumps(usage or {"activated": 0, "helped": 0, "hurt": 0, "ignored": 0}),
            created.isoformat(),
            created.isoformat(),
        ),
    )
    if embedding is not None:
        await conn.execute(
            "INSERT INTO memory_items_vec (item_id, embedding) VALUES (?, ?)",
            (item_id, serialize_embedding(embedding)),
        )
    await conn.commit()


async def test_search_empty_returns_empty_bundle(conn: aiosqlite.Connection):
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="anything"), now=NOW)

    assert bundle.candidates == []
    assert bundle.omitted == []
    assert bundle.prompt_context == ""
    assert bundle.used_chars == 0
    assert bundle.skills_to_use == []


async def test_search_fts_only_match(conn: aiosqlite.Connection):
    await _insert_item(conn, "needle", "rare lexical memory token")
    await _insert_item(conn, "haystack-1", "ordinary unrelated text")
    await _insert_item(conn, "haystack-2", "another unrelated note")
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="rare lexical", limit=5), now=NOW)

    assert [candidate.item_id for candidate in bundle.candidates] == ["needle"]
    assert bundle.candidates[0].reasons == ["claim_match", "fts_match"]


async def test_search_vector_only_match(conn: aiosqlite.Connection):
    await _insert_item(conn, "a", "unrelated alpha", embedding=_vec(0))
    await _insert_item(conn, "b", "unrelated beta", embedding=_vec(1))
    await _insert_item(conn, "c", "unrelated gamma", embedding=_vec(2))
    retrieval = MemoryRetrieval(conn, FakeEmbedder({"semantic query": _vec(1)}))

    bundle = await retrieval.search(MemoryActivationRequest(query="semantic query", limit=3), now=NOW)

    assert bundle.candidates[0].item_id == "b"
    assert "vector_match" in bundle.candidates[0].reasons


async def test_search_hybrid_fts_and_vector(conn: aiosqlite.Connection):
    await _insert_item(conn, "fts-only", "project zebra exact phrase", embedding=_vec(2))
    await _insert_item(conn, "vector-only", "semantic neighbor", embedding=_vec(0))
    await _insert_item(conn, "both", "project zebra exact phrase and semantic neighbor", embedding=_vec(0))
    retrieval = MemoryRetrieval(conn, FakeEmbedder({"project zebra": _vec(0)}), vec_top_k=2)

    bundle = await retrieval.search(MemoryActivationRequest(query="project zebra", limit=3), now=NOW)

    assert bundle.candidates[0].item_id == "both"
    assert set(bundle.candidates[0].reasons) == {"claim_match", "fts_match", "vector_match"}


async def test_search_status_filter_active_only(conn: aiosqlite.Connection):
    await _insert_item(conn, "active", "status token", status="active")
    await _insert_item(conn, "superseded", "status token", status="superseded")
    await _insert_item(conn, "archived", "status token", status="archived")
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="status token", limit=10), now=NOW)

    assert [candidate.item_id for candidate in bundle.candidates] == ["active"]


async def test_search_scope_filter_user_and_project(conn: aiosqlite.Connection):
    await _insert_item(conn, "user", "scope token", scope="user")
    await _insert_item(conn, "project", "scope token", scope="proj_abc")
    await _insert_item(conn, "other", "scope token", scope="proj_other")
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    project_bundle = await retrieval.search(MemoryActivationRequest(query="scope token", scope="proj_abc", limit=10), now=NOW)
    user_bundle = await retrieval.search(MemoryActivationRequest(query="scope token", limit=10), now=NOW)

    assert {candidate.item_id for candidate in project_bundle.candidates} == {"user", "project"}
    assert [candidate.item_id for candidate in user_bundle.candidates] == ["user"]


async def test_search_kind_filter_subset(conn: aiosqlite.Connection):
    await _insert_item(conn, "episode", "kind token", kind="episode")
    await _insert_item(conn, "claim", "kind token", kind="claim")
    await _insert_item(conn, "skill", "kind token", kind="skill")
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="kind token", kinds=["claim", "skill"], limit=10), now=NOW)

    assert {candidate.item_id for candidate in bundle.candidates} == {"claim", "skill"}
    skill = next(candidate for candidate in bundle.candidates if candidate.item_id == "skill")
    assert "skill_match" in skill.reasons


async def test_search_validity_window_excludes_future_valid_from(conn: aiosqlite.Connection):
    await _insert_item(conn, "current", "valid token", valid_from=NOW - timedelta(days=1))
    await _insert_item(conn, "future", "valid token", valid_from=NOW + timedelta(days=1))
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="valid token", limit=10), now=NOW)

    assert [candidate.item_id for candidate in bundle.candidates] == ["current"]


async def test_search_validity_window_excludes_expired_invalid_at(conn: aiosqlite.Connection):
    await _insert_item(conn, "expired", "expiry token", invalid_at=NOW - timedelta(seconds=1))
    await _insert_item(conn, "live", "expiry token", invalid_at=NOW + timedelta(days=1))
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="expiry token", limit=10), now=NOW)

    assert [candidate.item_id for candidate in bundle.candidates] == ["live"]


async def test_search_recency_decay_orders_newer_higher(conn: aiosqlite.Connection):
    await _insert_item(conn, "old", "same recency token", created_at=NOW - timedelta(days=90))
    await _insert_item(conn, "new", "same recency token", created_at=NOW - timedelta(days=7))
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="same recency token", limit=2), now=NOW)

    assert [candidate.item_id for candidate in bundle.candidates] == ["new", "old"]
    assert bundle.candidates[0].score_breakdown["recency"] > bundle.candidates[1].score_breakdown["recency"]


async def test_search_usage_feedback_boosts_helpful_items(conn: aiosqlite.Connection):
    await _insert_item(conn, "neutral", "same usage token", usage={"activated": 0, "helped": 0, "hurt": 0, "ignored": 0})
    await _insert_item(conn, "helpful", "same usage token", usage={"activated": 10, "helped": 8, "hurt": 1, "ignored": 1})
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="same usage token", limit=2), now=NOW)

    assert bundle.candidates[0].item_id == "helpful"
    assert bundle.candidates[0].score_breakdown["feedback"] > bundle.candidates[1].score_breakdown["feedback"]


async def test_search_confidence_factor_pulls_high_confidence_up(conn: aiosqlite.Connection):
    await _insert_item(conn, "low", "same confidence token", confidence=0.2)
    await _insert_item(conn, "high", "same confidence token", confidence=0.9)
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="same confidence token", limit=2), now=NOW)

    assert bundle.candidates[0].item_id == "high"
    assert bundle.candidates[0].score_breakdown["confidence"] > bundle.candidates[1].score_breakdown["confidence"]


async def test_search_respects_limit(conn: aiosqlite.Connection):
    for index in range(10):
        await _insert_item(conn, f"item-{index}", f"limit token {index}")
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="limit token", limit=3), now=NOW)

    assert len(bundle.candidates) == 3
    assert len(bundle.omitted) == 7


async def test_search_respects_budget_chars(conn: aiosqlite.Connection):
    for index in range(5):
        await _insert_item(conn, f"item-{index}", f"budget token {'x' * 500} {index}")
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="budget token", limit=5, budget_chars=600), now=NOW)

    assert len(bundle.candidates) == 1
    assert len(bundle.omitted) == 4
    assert bundle.used_chars <= 600
    assert len(bundle.prompt_context) <= 600


async def test_score_breakdown_shape_and_components(conn: aiosqlite.Connection):
    await _insert_item(conn, "a", "formula token", confidence=0.8, embedding=_halfway_vec())
    retrieval = MemoryRetrieval(
        conn,
        FakeEmbedder({"formula token": _vec(0)}),
        w_fts=0.35,
        w_vec=0.35,
        w_recency=0.10,
        w_feedback=0.10,
        w_confidence=0.10,
    )

    bundle = await retrieval.search(MemoryActivationRequest(query="formula token"), now=NOW)

    candidate = bundle.candidates[0]
    assert set(candidate.score_breakdown) == {"fts", "vector", "recency", "feedback", "confidence"}
    assert all(0.0 <= value <= 1.0 for value in candidate.score_breakdown.values())
    # vec0 cosine distance for unit vectors at 45 degrees is 1 - cos(theta).
    # Retrieval must convert distance to similarity with: similarity = 1.0 - distance.
    assert candidate.score_breakdown["vector"] == pytest.approx(1.0 / math.sqrt(2), abs=1e-5)
    expected = (
        0.35 * candidate.score_breakdown["fts"]
        + 0.35 * candidate.score_breakdown["vector"]
        + 0.10 * candidate.score_breakdown["recency"]
        + 0.10 * candidate.score_breakdown["feedback"]
        + 0.10 * candidate.score_breakdown["confidence"]
    )
    assert candidate.score == pytest.approx(expected)


async def test_prompt_context_format_includes_kind_and_confidence_bucket(conn: aiosqlite.Connection):
    await _insert_item(conn, "claim", "bucket token high", kind="claim", confidence=0.9)
    await _insert_item(conn, "skill", "bucket token med", kind="skill", confidence=0.5)
    await _insert_item(conn, "episode", "bucket token low", kind="episode", confidence=0.2)
    retrieval = MemoryRetrieval(conn, FakeEmbedder())

    bundle = await retrieval.search(MemoryActivationRequest(query="bucket token", limit=3), now=NOW)

    assert "[claim · conf=high]" in bundle.prompt_context
    assert "[skill · conf=med]" in bundle.prompt_context
    assert "[episode · conf=low]" in bundle.prompt_context


async def test_search_handles_no_vec_rows_gracefully(conn: aiosqlite.Connection):
    await _insert_item(conn, "fts", "no vector token")
    retrieval = MemoryRetrieval(conn, FakeEmbedder({"no vector token": _vec(0)}))

    bundle = await retrieval.search(MemoryActivationRequest(query="no vector token"), now=NOW)

    assert [candidate.item_id for candidate in bundle.candidates] == ["fts"]
    assert bundle.candidates[0].score_breakdown["vector"] == 0.0


async def test_search_vector_dim_mismatch_raises_clear_error(conn: aiosqlite.Connection):
    await _insert_item(conn, "fts", "dimension token")
    retrieval = MemoryRetrieval(conn, FakeEmbedder({"dimension token": _vec(0, dim=768)}))

    with pytest.raises(ValueError, match="query embedding dimension 768 does not match memory_items_vec dimension 1536"):
        await retrieval.search(MemoryActivationRequest(query="dimension token"), now=NOW)
