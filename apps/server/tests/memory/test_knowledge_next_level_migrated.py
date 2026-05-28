from __future__ import annotations

import math
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.knowledge.evals import MemoryEvalCase, MemoryEvalSuite, run_memory_eval_suite
from ntrp.memory.activation import MemoryActivationBundle, MemoryActivationCandidate, MemoryActivationRequest
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.pattern_finder import PatternFinder
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite

TEST_EMBEDDING_DIM = 8
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)


class _FakeSummaryClient:
    def __init__(self, response: str):
        self.response = response

    async def __call__(self, prompt: str) -> str:
        return self.response


class _FakeEmbedder:
    def __init__(self, vector: np.ndarray | None = None):
        self.config = SimpleNamespace(dim=TEST_EMBEDDING_DIM)
        self.vector = vector if vector is not None else _vec(0)

    async def embed_one(self, text: str) -> np.ndarray:
        return self.vector


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
    embedding: np.ndarray | None = None,
    tags: list[str] | None = None,
    confidence: float = 0.6,
    scope: str = "user",
) -> str:
    return await MemoryItemsRepository(conn).insert_item(
        MemoryItemInsert(
            kind=kind,
            content=content,
            provenance="inferred",
            source_refs=[{"kind": "test", "ref": content, "captured_at": NOW.isoformat()}],
            confidence=confidence,
            status="active",
            scope=scope,
            tags=tags or [],
            embedding=embedding,
            valid_from=NOW,
        )
    )


async def _claim_rows(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind = 'claim' ORDER BY created_at, id")


async def _run_pass2(conn: aiosqlite.Connection, response: str = "User prefers runtime-first debugging."):
    finder = PatternFinder(
        repo=MemoryItemsRepository(conn),
        summary_client=_FakeSummaryClient(response),
        embedder=_FakeEmbedder(),
    )
    return await finder.run_pass2(window_days=30, scope="user", now=NOW)


@pytest.mark.asyncio
async def test_knowledge_next_level_backfilled_memory_item_embedding_is_retrievable(conn: aiosqlite.Connection):
    item_id = await _insert_item(
        conn,
        "Old knowledge should receive a vector during production backfill.",
        kind="claim",
        embedding=None,
        tags=["backfill"],
        confidence=0.8,
    )
    assert await conn.execute_fetchall("SELECT * FROM memory_items_vec WHERE item_id = ?", (item_id,)) == []

    await conn.execute("INSERT INTO memory_items_vec (item_id, embedding) VALUES (?, ?)", (item_id, database.serialize_embedding(_vec(0))))
    await conn.commit()
    bundle = await MemoryRetrieval(conn, _FakeEmbedder(_vec(0))).search(
        MemoryActivationRequest(query="Old knowledge vector", kinds=["claim"], scope="user", limit=1, budget_chars=500),
        now=NOW,
    )

    assert [candidate.item_id for candidate in bundle.candidates] == [item_id]


@pytest.mark.asyncio
async def test_knowledge_next_level_procedure_candidate_promotes_to_claim_not_skill(conn: aiosqlite.Connection):
    await _insert_item(conn, "When debugging production, inspect the real run before static reasoning.", embedding=_vec(0), tags=["procedure"])
    await _insert_item(conn, "For production incidents, inspect runtime evidence before reasoning.", embedding=_cos_vec(0.9), tags=["procedure"])

    result = await _run_pass2(conn, "User should inspect real production runtime evidence before static reasoning.")

    assert result.claims_written == 1
    claims = await _claim_rows(conn)
    assert claims[0]["kind"] == "claim"
    assert await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind = 'skill'") == []


@pytest.mark.asyncio
@pytest.mark.skip(reason="slice 6: contradiction watcher owns semantic conflict routing")
async def test_knowledge_next_level_semantic_conflict_routing_deferred_to_slice_6(conn: aiosqlite.Connection):
    assert conn


@pytest.mark.asyncio
async def test_knowledge_next_level_model_proposed_supersession_requires_evidence_superset(conn: aiosqlite.Connection):
    old_evidence = await _insert_item(conn, "Dex deploys used stable release channel.", embedding=_vec(0), tags=["dex"])
    old_claim = await _insert_item(conn, "Dex deploys use stable.", kind="claim", embedding=_vec(0), tags=["dex"])
    await MemoryItemsRepository(conn).insert_parent_edge(old_claim, old_evidence, "evidence")
    await _insert_item(conn, "Dex deploys now use canary release channel.", embedding=_cos_vec(0.9), tags=["dex"])

    result = await _run_pass2(conn, "Dex deploys now use canary release channel.")

    old_row = next(row for row in await _claim_rows(conn) if row["id"] == old_claim)
    assert result.claims_superseded == 1
    assert old_row["status"] == "superseded"


@pytest.mark.asyncio
async def test_knowledge_next_level_model_proposed_supersession_rejects_unrelated_objects(conn: aiosqlite.Connection):
    old_evidence = await _insert_item(conn, "Dex deploys use stable.", embedding=_vec(0), tags=["dex"])
    old_claim = await _insert_item(conn, "Dex deploys use stable.", kind="claim", embedding=_vec(0), tags=["dex"])
    await MemoryItemsRepository(conn).insert_parent_edge(old_claim, old_evidence, "evidence")
    await _insert_item(conn, "Prime pods use H100 GPUs.", embedding=_vec(3), tags=["prime"])
    await _insert_item(conn, "Prime GPU work prefers H100 pods.", embedding=_vec(3), tags=["prime"])

    result = await _run_pass2(conn, "Prime GPU work prefers H100 pods.")

    old_row = next(row for row in await _claim_rows(conn) if row["id"] == old_claim)
    assert result.claims_written == 1
    assert result.claims_superseded == 0
    assert old_row["status"] == "active"


@pytest.mark.asyncio
async def test_knowledge_next_level_fact_consolidation_duplicate_fact_supersedes_old_claim(conn: aiosqlite.Connection):
    first = await _insert_item(conn, "User prefers concise status updates.", embedding=_vec(0), tags=["style"])
    old_claim = await _insert_item(conn, "User prefers concise updates.", kind="claim", embedding=_vec(0), tags=["style"])
    await MemoryItemsRepository(conn).insert_parent_edge(old_claim, first, "evidence")
    second = await _insert_item(conn, "User asked for dense short updates.", embedding=_cos_vec(0.9), tags=["style"])

    await _run_pass2(conn, "User prefers concise, information-dense updates.")

    new_claim = next(row for row in await _claim_rows(conn) if row["id"] != old_claim)
    edges = await MemoryItemsRepository(conn).list_parent_edges(new_claim["id"])
    assert {(edge.parent_id, edge.role) for edge in edges} >= {
        (first, "evidence"),
        (second, "evidence"),
        (old_claim, "supersedes"),
    }


@pytest.mark.asyncio
async def test_knowledge_next_level_source_trace_keeps_evidence_and_superseded_claim(conn: aiosqlite.Connection):
    first = await _insert_item(conn, "Trace source one.", embedding=_vec(0), tags=["trace"])
    old_claim = await _insert_item(conn, "Old trace claim.", kind="claim", embedding=_vec(0), tags=["trace"])
    await MemoryItemsRepository(conn).insert_parent_edge(old_claim, first, "evidence")
    second = await _insert_item(conn, "Trace source two.", embedding=_cos_vec(0.9), tags=["trace"])

    await _run_pass2(conn, "User keeps related source trace claims.")

    new_claim = next(row for row in await _claim_rows(conn) if row["id"] != old_claim)
    edges = await MemoryItemsRepository(conn).list_parent_edges(new_claim["id"])
    assert {edge.parent_id for edge in edges if edge.role == "evidence"} == {first, second}
    assert [edge.parent_id for edge in edges if edge.role == "supersedes"] == [old_claim]


@pytest.mark.asyncio
async def test_knowledge_next_level_claim_retrieval_suppresses_superseded_old_claim(conn: aiosqlite.Connection):
    first = await _insert_item(conn, "Runtime evidence first.", embedding=_vec(0), tags=["runtime"])
    old_claim = await _insert_item(conn, "Old runtime claim.", kind="claim", embedding=_vec(0), tags=["runtime"])
    await MemoryItemsRepository(conn).insert_parent_edge(old_claim, first, "evidence")
    await _insert_item(conn, "Runtime evidence second.", embedding=_cos_vec(0.9), tags=["runtime"])
    await _run_pass2(conn, "User prefers new runtime evidence claims.")

    bundle = await MemoryRetrieval(conn, _FakeEmbedder(_vec(0))).search(
        MemoryActivationRequest(query="runtime", kinds=["claim"], scope="user", limit=5, budget_chars=1000),
        now=NOW,
    )

    assert old_claim not in [candidate.item_id for candidate in bundle.candidates]
    assert any(candidate.content == "User prefers new runtime evidence claims." for candidate in bundle.candidates)


@pytest.mark.asyncio
async def test_knowledge_next_level_claim_confidence_uses_parent_confidence_mean(conn: aiosqlite.Connection):
    await _insert_item(conn, "Confidence high.", embedding=_vec(0), tags=["confidence"], confidence=0.8)
    await _insert_item(conn, "Confidence low.", embedding=_cos_vec(0.9), tags=["confidence"], confidence=0.4)

    await _run_pass2(conn, "User has confidence-weighted evidence.")

    claim = (await _claim_rows(conn))[0]
    assert claim["confidence"] == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_memory_eval_suite_reports_precision_recall_against_memory_items():
    class _Inspector:
        async def search(self, request):
            candidate = MemoryActivationCandidate(
                item_id="good",
                kind="claim",
                content="Good memory",
                score=1.0,
                score_breakdown={},
                reasons=["claim_match"],
                confidence=0.8,
                scope=request.scope or "user",
                tags=[],
                source_refs=[],
                valid_from=NOW.isoformat(),
                invalid_at=None,
                created_at=NOW.isoformat(),
            )
            return MemoryActivationBundle(
                query=request.query,
                scope=request.scope,
                kinds=["claim"],
                budget_chars=request.budget_chars,
                used_chars=11,
                candidates=[candidate],
                omitted=[],
                prompt_context="Good memory",
            )

    result = await run_memory_eval_suite(
        _Inspector(),
        MemoryEvalSuite(
            name="tiny-memory-items",
            cases=[MemoryEvalCase(name="case", query="good", expected_object_ids={"good"}, forbidden_object_ids={"bad"})],
        ),
    )

    assert result.passed
    assert result.precision == 1.0
    assert result.recall == 1.0
