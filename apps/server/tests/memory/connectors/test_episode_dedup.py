import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.buffers_store import EpisodeBufferRepository, TurnUpdate
from ntrp.memory.connectors.episode_close import (
    DedupCandidate,
    _containment,
    _legacy_decision,
    _parse_decision,
    _recall_candidates,
    finalize_buffer,
)
from ntrp.memory.items_store import MemoryItem, MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase

TEST_DIM = 8


def _vec(index: int, value: float = 1.0) -> np.ndarray:
    arr = np.zeros(TEST_DIM, dtype=np.float32)
    arr[index] = value
    return arr


class MockEmbedder:
    def __init__(self, vectors: list[np.ndarray] | None = None, dim: int = TEST_DIM):
        self.config = SimpleNamespace(dim=dim)
        self._vectors = list(vectors or [])

    async def embed_one(self, text: str) -> np.ndarray:
        if self._vectors:
            return self._vectors.pop(0)
        return _vec(0)


@pytest_asyncio.fixture
async def conn(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db", vec=True)
    await conn.execute("PRAGMA foreign_keys=ON")
    db = GraphDatabase(conn, TEST_DIM)
    await db.init_schema()
    try:
        yield conn
    finally:
        await conn.close()


async def _seed_episode(items: MemoryItemsRepository, content: str, embedding: np.ndarray) -> str:
    return await items.insert_item(
        MemoryItemInsert(kind="episode", content=content, source_refs=[], confidence=0.3, embedding=embedding)
    )


async def _seed_buffer(buffers: EpisodeBufferRepository, *, count: int = 3) -> "object":
    buffer = await buffers.create("user", "chat_msg")
    for i in range(count):
        buffer = await buffers.apply_turn(
            buffer.id,
            TurnUpdate(content=f"turn {i}", tokens=1, source_ref={"kind": "chat_msg", "ref": f"r{i}"}, embedding=_vec(0)),
        )
    return buffer


async def _episodes(conn) -> list:
    return await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind='episode' ORDER BY created_at, id")


# ---- pure functions -------------------------------------------------------


def test_containment_subset_is_one():
    assert _containment("apply to mats", "timur plans to apply to mats autumn 2026 empirical") == 1.0


def test_containment_disjoint_is_zero():
    assert _containment("totally unrelated words", "nothing in common here friend") == 0.0


def test_containment_partial():
    assert _containment("apply mats stripe", "apply mats only") == pytest.approx(2 / 3)


def test_parse_decision_strips_code_fences():
    raw = '```json\n{"action": "drop", "target_id": "abc", "reason": "subset"}\n```'
    decision = _parse_decision(raw)
    assert decision.action == "drop"
    assert decision.target_id == "abc"


def test_parse_decision_fails_open_to_keep():
    assert _parse_decision("not json at all").action == "keep"


def test_parse_decision_unknown_action_becomes_keep():
    assert _parse_decision(json.dumps({"action": "explode"})).action == "keep"


def _candidate(item_id: str, cosine: float) -> DedupCandidate:
    item = MemoryItem(
        id=item_id, kind="episode", content="x", title=None, provenance="inferred", source_refs=[],
        confidence=0.3, status="active", valid_from=None, invalid_at=None, scope="user", tags=[],
        artifact_ref=None, usage={}, feedback={}, created_at=None, updated_at=None, embedding=None,
    )
    return DedupCandidate(item=item, cosine=cosine, containment=0.0)


def test_legacy_decision_drops_above_high_threshold():
    assert _legacy_decision([_candidate("a", 0.95)]).action == "drop"


def test_legacy_decision_keeps_below_high_threshold():
    assert _legacy_decision([_candidate("a", 0.85)]).action == "keep"


# ---- recall ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_filters_below_threshold(conn):
    items = MemoryItemsRepository(conn)
    await _seed_episode(items, "near duplicate", _vec(0))  # cosine 1.0 vs new
    await _seed_episode(items, "unrelated", _vec(1))  # cosine 0.0 vs new

    candidates = await _recall_candidates(items, "user", "new summary", _vec(0))

    assert [c.item.content for c in candidates] == ["near duplicate"]


# ---- finalize decisions ---------------------------------------------------


@pytest.mark.asyncio
async def test_keep_with_no_candidates_skips_llm(conn):
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    await _seed_episode(items, "unrelated", _vec(1))
    buffer = await _seed_buffer(buffers)
    dedup = AsyncMock()

    await finalize_buffer(
        buffer=buffer, items=items, buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="brand new fact"),
        reason="idle_gap", dedup_client=dedup,
    )

    dedup.assert_not_called()
    assert len(await _episodes(conn)) == 2  # seed + new


@pytest.mark.asyncio
async def test_drop_redundant_episode(conn):
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    target = await _seed_episode(items, "timur applies to mats autumn 2026 empirical deadline june 7", _vec(0))
    buffer = await _seed_buffer(buffers)
    dedup = AsyncMock(return_value=json.dumps({"action": "drop", "target_id": target, "reason": "subset"}))

    await finalize_buffer(
        buffer=buffer, items=items, buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="timur applies to mats"),
        reason="idle_gap", dedup_client=dedup,
    )

    assert len(await _episodes(conn)) == 1  # only the original survives


@pytest.mark.asyncio
async def test_supersede_response_is_coerced_to_keep_episodes_immutable(conn):
    # Episodes are immutable raw slices: a legacy "supersede" decision must NOT
    # retire or chain the prior episode. Both survive active; no supersedes edge.
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    old = await _seed_episode(items, "timur applies to mats", _vec(0))
    buffer = await _seed_buffer(buffers)
    dedup = AsyncMock(return_value=json.dumps({"action": "supersede", "target_id": old, "reason": "richer"}))

    await finalize_buffer(
        buffer=buffer, items=items, buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="timur applies to mats autumn 2026 empirical, deadline june 7, form url"),
        reason="idle_gap", dedup_client=dedup,
    )

    rows = {r["id"]: r for r in await _episodes(conn)}
    assert rows[old]["status"] == "active"  # prior episode untouched
    assert len(rows) == 2  # new episode stored as its own slice
    edges = await conn.execute_fetchall("SELECT role FROM memory_item_parents WHERE parent_id=? OR child_id=?", (old, old))
    assert [e["role"] for e in edges] == []  # never chained


@pytest.mark.asyncio
async def test_merge_response_is_coerced_to_keep_no_mutation(conn):
    # A legacy "merge" decision must NOT mutate the existing episode. The new
    # episode is stored as its own slice; the target's content is unchanged.
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    target = await _seed_episode(items, "timur applies to mats", _vec(0))
    buffer = await _seed_buffer(buffers)
    merged = "timur applies to mats autumn 2026, deadline june 7, form url"
    dedup = AsyncMock(
        return_value=json.dumps({"action": "merge", "target_id": target, "merged_content": merged, "reason": "both"})
    )

    await finalize_buffer(
        buffer=buffer, items=items, buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="deadline june 7 form url"),
        reason="idle_gap", dedup_client=dedup,
    )

    rows = {r["id"]: r for r in await _episodes(conn)}
    assert len(rows) == 2  # new slice stored, nothing merged
    assert rows[target]["content"] == "timur applies to mats"  # target unchanged


@pytest.mark.asyncio
async def test_learnings_injected_into_dedup_prompt(conn, tmp_path):
    from ntrp.memory.learnings import Correction, LearningsStore

    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    await _seed_episode(items, "timur applies to mats", _vec(0))
    buffer = await _seed_buffer(buffers)

    learnings = LearningsStore(base_dir=tmp_path / "learnings")
    learnings.record(Correction(adjudicator="dedup", action="edit", summary="MATS notes are never duplicates"))

    dedup = AsyncMock(return_value=json.dumps({"action": "keep"}))
    await finalize_buffer(
        buffer=buffer, items=items, buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="timur applies to mats"),
        reason="idle_gap", dedup_client=dedup, learnings=learnings,
    )

    prompt = dedup.call_args[0][0]
    assert "MATS notes are never duplicates" in prompt
    assert "honor them" in prompt


@pytest.mark.asyncio
async def test_parse_failure_keeps_episode(conn):
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    await _seed_episode(items, "timur applies to mats", _vec(0))
    buffer = await _seed_buffer(buffers)
    dedup = AsyncMock(return_value="the model rambled instead of returning json")

    await finalize_buffer(
        buffer=buffer, items=items, buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="timur applies to mats"),
        reason="idle_gap", dedup_client=dedup,
    )

    assert len(await _episodes(conn)) == 2  # fail-open: new episode still stored
