from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.buffers_store import BufferCarry, EpisodeBufferRepository
from ntrp.memory.connectors.base import BufferingConnector
from ntrp.memory.connectors.episode_close import TriggerConfig
from ntrp.memory.connectors.idle_sweeper import IdleBufferSweeper
from ntrp.memory.items_store import MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase

TEST_EMBEDDING_DIM = 8


def _vec(index: int) -> np.ndarray:
    arr = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    arr[index] = 1.0
    return arr


class MockEmbedder:
    def __init__(self, vectors: list[np.ndarray] | None = None, dim: int = TEST_EMBEDDING_DIM):
        self.config = SimpleNamespace(dim=dim)
        self._vectors = list(vectors or [])

    async def embed_one(self, text: str) -> np.ndarray:
        if self._vectors:
            return self._vectors.pop(0)
        return _vec(0)


class EmailConnector(BufferingConnector):
    source_kind = "email"
    triggers = TriggerConfig(turn_budget=2, idle_gap=timedelta(hours=24))


@pytest_asyncio.fixture
async def conn(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db", vec=True)
    await conn.execute("PRAGMA foreign_keys=ON")
    db = GraphDatabase(conn, TEST_EMBEDDING_DIM)
    await db.init_schema()
    try:
        yield conn
    finally:
        await conn.close()


def _connector(conn, *, vectors: list[np.ndarray] | None = None, llm=None) -> EmailConnector:
    return EmailConnector(
        items=MemoryItemsRepository(conn),
        buffers=EpisodeBufferRepository(conn),
        embedder=MockEmbedder(vectors),
        llm_client=llm or AsyncMock(return_value="durable email summary"),
    )


def _ref(ref: str) -> dict:
    return {"kind": "email", "ref": ref, "captured_at": datetime.now(UTC).isoformat()}


async def _items(conn):
    return await conn.execute_fetchall("SELECT * FROM memory_items ORDER BY created_at, id")


async def _buffers(conn, *, closed: bool):
    op = "IS NOT NULL" if closed else "IS NULL"
    return await conn.execute_fetchall(f"SELECT * FROM episode_buffers WHERE closed_at {op}")


@pytest.mark.asyncio
async def test_non_chat_source_flows_through_shared_pipeline(conn):
    connector = _connector(conn, vectors=[_vec(0), _vec(0), _vec(0)])

    for i in range(3):
        await connector.ingest(scope="user", content=f"email body {i}", source_ref=_ref(f"msg-{i}"))

    # turn_budget=2 closes the buffer mid-stream, emitting exactly one episode.
    open_rows = await _buffers(conn, closed=False)
    assert len(open_rows) == 1
    assert open_rows[0]["source_kind"] == "email"
    episodes = [row for row in await _items(conn) if row["kind"] == "episode"]
    assert len(episodes) == 1


@pytest.mark.asyncio
async def test_idle_sweep_is_source_isolated(conn):
    buffers = EpisodeBufferRepository(conn)
    for source_kind in ("email", "chat_msg"):
        await buffers.create(
            "user",
            source_kind,
            carry=BufferCarry(
                content=f"stale {source_kind}",
                source_refs=[_ref(f"{source_kind}-run")],
                centroid=_vec(0),
                turn_count=1,
                tokens=3,
            ),
        )
    stale = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    await conn.execute("UPDATE episode_buffers SET last_activity_at = ?", (stale,))
    await conn.commit()

    connector = _connector(conn, vectors=[_vec(0)])
    await IdleBufferSweeper(lambda: [connector]).sweep_once()

    # Only the email buffer is swept; the chat buffer is left for its own connector.
    closed = await _buffers(conn, closed=True)
    assert [row["source_kind"] for row in closed] == ["email"]
    open_kinds = sorted(row["source_kind"] for row in await _buffers(conn, closed=False))
    assert open_kinds == ["chat_msg", "email"]  # chat untouched; email carry-forward reopened
