import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.buffers_store import EpisodeBufferRepository, TurnUpdate
from ntrp.memory.connectors.claim_writer import (
    _claim_confidence,
    _parse_claims,
    _parse_decisions,
    write_claims,
)
from ntrp.memory.connectors.episode_close import finalize_buffer
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
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


async def _seed_claim(items: MemoryItemsRepository, content: str, embedding: np.ndarray) -> str:
    return await items.insert_item(
        MemoryItemInsert(
            kind="claim", content=content, provenance="inferred", source_refs=[], confidence=0.5, embedding=embedding
        )
    )


async def _seed_buffer(buffers: EpisodeBufferRepository, *, count: int = 3):
    buffer = await buffers.create("user", "chat_msg")
    for i in range(count):
        buffer = await buffers.apply_turn(
            buffer.id,
            TurnUpdate(content=f"turn {i}", tokens=1, source_ref={"kind": "chat_msg", "ref": f"r{i}"}, embedding=_vec(0)),
        )
    return buffer


async def _claims(conn) -> list:
    return await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind='claim' ORDER BY created_at, id")


# ---- pure parsing ---------------------------------------------------------


def test_parse_claims_splits_lines_and_strips_bullets():
    assert _parse_claims("- one fact\n2. another fact\n") == ["one fact", "another fact"]


def test_parse_claims_none_sentinel_is_empty():
    assert _parse_claims("NONE") == []


def test_parse_decisions_length_mismatch_fails_open_to_add():
    decisions = _parse_decisions(json.dumps([{"action": "NOOP"}]), 2)
    assert [d.action for d in decisions] == ["ADD", "ADD"]


def test_parse_decisions_garbage_fails_open_to_add():
    decisions = _parse_decisions("not json", 1)
    assert decisions[0].action == "ADD"


# ---- extraction -----------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_adds_claims_with_evidence_edge_and_confidence_below_one(conn):
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))

    added = await write_claims(
        episode_id=episode_id,
        summary="timur switched to postgres because sqlite locked under concurrent writes",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),
        extract_client=AsyncMock(return_value="timur uses postgres for concurrent writes"),
        adjudicate_client=AsyncMock(),  # no candidates -> not called
    )

    rows = await _claims(conn)
    assert len(rows) == 1
    assert len(added) == 1
    claim_id = added[0]
    assert 0.0 < rows[0]["confidence"] < 1.0
    assert rows[0]["provenance"] == "inferred"
    edges = await conn.execute_fetchall(
        "SELECT parent_id, role FROM memory_item_parents WHERE child_id = ?", (claim_id,)
    )
    assert [(e["parent_id"], e["role"]) for e in edges] == [(episode_id, "evidence")]


@pytest.mark.asyncio
async def test_none_extraction_writes_no_claims(conn):
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))

    added = await write_claims(
        episode_id=episode_id,
        summary="just chit chat",
        scope="user",
        items=items,
        embedder=MockEmbedder(),
        extract_client=AsyncMock(return_value="NONE"),
        adjudicate_client=AsyncMock(),
    )

    assert added == []
    assert await _claims(conn) == []


# ---- adjudication actions -------------------------------------------------


@pytest.mark.asyncio
async def test_update_rewrites_in_place_no_new_row_no_supersedes(conn):
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))
    target = await _seed_claim(items, "timur uses sqlite", _vec(1))

    added = await write_claims(
        episode_id=episode_id,
        summary="timur now uses postgres",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),  # claim embedding recalls the target
        extract_client=AsyncMock(return_value="timur uses postgres"),
        adjudicate_client=AsyncMock(
            return_value=json.dumps([{"action": "UPDATE", "target_id": target, "reason": "same fact"}])
        ),
    )

    rows = await _claims(conn)
    assert len(rows) == 1  # rewritten in place, no new row
    assert rows[0]["id"] == target
    assert rows[0]["content"] == "timur uses postgres"
    assert added == []
    edges = await conn.execute_fetchall("SELECT parent_id, role FROM memory_item_parents")
    # the corroborating episode is linked as fresh evidence; never a supersedes edge
    assert [(e["parent_id"], e["role"]) for e in edges] == [(episode_id, "evidence")]
    # confidence is recomputed from the refreshed parent set, not the stale 0.5 literal
    expected = _claim_confidence([0.3])
    assert rows[0]["confidence"] == pytest.approx(expected)
    assert rows[0]["confidence"] != 0.5


@pytest.mark.asyncio
async def test_noop_does_nothing(conn):
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))
    target = await _seed_claim(items, "timur uses postgres", _vec(1))

    added = await write_claims(
        episode_id=episode_id,
        summary="timur uses postgres",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),
        extract_client=AsyncMock(return_value="timur uses postgres"),
        adjudicate_client=AsyncMock(
            return_value=json.dumps([{"action": "NOOP", "target_id": target, "reason": "already known"}])
        ),
    )

    rows = await _claims(conn)
    assert len(rows) == 1
    assert rows[0]["content"] == "timur uses postgres"  # unchanged
    assert added == []


@pytest.mark.asyncio
async def test_not_same_guard_keeps_distinct_attributes_separate(conn):
    # Two new claims about the same subject but different attributes -> both ADD,
    # never merged onto the existing claim.
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))
    await _seed_claim(items, "the mats deadline is june 7", _vec(1))

    adjudicate = AsyncMock(
        return_value=json.dumps(
            [
                {"action": "ADD", "target_id": None, "reason": "different attribute: venue"},
                {"action": "ADD", "target_id": None, "reason": "different attribute: format"},
            ]
        )
    )
    added = await write_claims(
        episode_id=episode_id,
        summary="mats venue and format",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1), _vec(1)]),
        extract_client=AsyncMock(return_value="the mats venue is berkeley\nthe mats program is in person"),
        adjudicate_client=adjudicate,
    )

    rows = await _claims(conn)
    assert len(rows) == 3  # original + two new, nothing merged
    assert len(added) == 2
    prompt = adjudicate.call_args[0][0]
    assert "different attributes" in prompt  # not_same guard present


@pytest.mark.asyncio
async def test_recorded_not_same_pair_demotes_update_to_add(conn, tmp_path):
    # The user has marked two existing claims as distinct. Both are live candidates for a
    # new claim; the adjudicator nonetheless asks to UPDATE one of them. The checked hard
    # rule demotes that UPDATE to ADD so neither existing claim is collapsed.
    from ntrp.memory.learnings import Correction, LearningsStore

    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))
    target = await _seed_claim(items, "timur uses sqlite", _vec(1))
    partner = await _seed_claim(items, "timur uses postgres", _vec(1))

    learnings = LearningsStore(base_dir=tmp_path / "learnings")
    learnings.record(
        Correction(
            adjudicator="dedup",
            action="not_same",
            summary="distinct DBs",
            subjects=(target, partner),
        )
    )

    added = await write_claims(
        episode_id=episode_id,
        summary="timur db preference",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),  # recalls both target and partner
        extract_client=AsyncMock(return_value="timur uses a database"),
        adjudicate_client=AsyncMock(
            return_value=json.dumps([{"action": "UPDATE", "target_id": target, "reason": "merge"}])
        ),
        learnings=learnings,
    )

    rows = await _claims(conn)
    assert len(rows) == 3  # nothing rewritten; the new claim is ADDed instead
    assert len(added) == 1
    assert (await items.get_item(target)).content == "timur uses sqlite"  # untouched


# ---- contradiction watcher wiring -----------------------------------------


@pytest.mark.asyncio
async def test_write_claims_scans_each_added_claim(conn):
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))

    class _SpyWatcher:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        async def scan_for_new_claim(self, claim_id: str, *, scope: str):
            self.calls.append((claim_id, scope))
            return []

    watcher = _SpyWatcher()
    added = await write_claims(
        episode_id=episode_id,
        summary="timur switched to postgres",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),
        extract_client=AsyncMock(return_value="timur uses postgres"),
        adjudicate_client=AsyncMock(),
        watcher=watcher,
    )

    assert len(added) == 1
    assert watcher.calls == [(added[0], "user")]


@pytest.mark.asyncio
async def test_write_claims_isolates_watcher_failure(conn):
    items = MemoryItemsRepository(conn)
    episode_id = await _seed_episode(items, "episode body", _vec(0))

    class _BoomWatcher:
        async def scan_for_new_claim(self, claim_id: str, *, scope: str):
            raise RuntimeError("watcher boom")

    added = await write_claims(
        episode_id=episode_id,
        summary="timur switched to postgres",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),
        extract_client=AsyncMock(return_value="timur uses postgres"),
        adjudicate_client=AsyncMock(),
        watcher=_BoomWatcher(),
    )

    # The claim is still written; the watcher error never propagates.
    assert len(added) == 1
    assert len(await _claims(conn)) == 1


# ---- finalize integration (hermetic) --------------------------------------


@pytest.mark.asyncio
async def test_finalize_without_claim_client_stores_episode_but_no_claims(conn):
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    buffer = await _seed_buffer(buffers)

    await finalize_buffer(
        buffer=buffer,
        items=items,
        buffers=buffers,
        embedder=MockEmbedder([_vec(0)]),
        llm_client=AsyncMock(return_value="durable fact"),
        reason="idle_gap",
        dedup_client=AsyncMock(),
    )

    episodes = await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind='episode'")
    assert len(episodes) == 1  # episode stored
    assert await _claims(conn) == []  # no claim client -> no claims


@pytest.mark.asyncio
async def test_finalize_with_claim_clients_extracts_claims(conn):
    items = MemoryItemsRepository(conn)
    buffers = EpisodeBufferRepository(conn)
    buffer = await _seed_buffer(buffers)

    await finalize_buffer(
        buffer=buffer,
        items=items,
        buffers=buffers,
        embedder=MockEmbedder([_vec(0), _vec(1)]),  # episode summary, then claim
        llm_client=AsyncMock(return_value="timur switched to postgres"),
        reason="idle_gap",
        dedup_client=AsyncMock(),
        claim_extract_client=AsyncMock(return_value="timur uses postgres"),
        claim_adjudicate_client=AsyncMock(),  # no existing claims -> not called
    )

    episodes = await conn.execute_fetchall("SELECT id FROM memory_items WHERE kind='episode'")
    claims = await _claims(conn)
    assert len(episodes) == 1
    assert len(claims) == 1
    edges = await conn.execute_fetchall(
        "SELECT parent_id, role FROM memory_item_parents WHERE child_id = ?", (claims[0]["id"],)
    )
    assert [(e["parent_id"], e["role"]) for e in edges] == [(episodes[0]["id"], "evidence")]
