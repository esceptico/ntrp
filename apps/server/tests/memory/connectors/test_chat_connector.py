import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.agent import Usage
from ntrp.events.internal import RunCompleted
from ntrp.knowledge.episodes import EpisodeBoundaryClassifier
from ntrp.memory.buffers_store import BufferCarry, EpisodeBufferRepository, TurnUpdate
from ntrp.memory.connectors._confidence import compute_confidence, confidence_bucket
from ntrp.memory.connectors.chat import ChatConnector
from ntrp.memory.connectors.idle_sweeper import IdleBufferSweeper
from ntrp.memory.items_store import MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase

TEST_EMBEDDING_DIM = 8


def _vec(index: int) -> np.ndarray:
    arr = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    arr[index] = 1.0
    return arr


def _near_vec() -> np.ndarray:
    arr = np.zeros(TEST_EMBEDDING_DIM, dtype=np.float32)
    arr[0] = 0.8
    arr[1] = 0.6
    return arr / np.linalg.norm(arr)


class MockEmbedder:
    def __init__(self, vectors: list[np.ndarray] | None = None, dim: int = TEST_EMBEDDING_DIM):
        self.config = SimpleNamespace(dim=dim)
        self._vectors = list(vectors or [])

    async def embed_one(self, text: str) -> np.ndarray:
        if self._vectors:
            return self._vectors.pop(0)
        return _vec(0)


class BarrierBufferRepository(EpisodeBufferRepository):
    def __init__(self, conn: aiosqlite.Connection):
        super().__init__(conn)
        self._waiting = 0
        self._release = asyncio.Event()
        self._barrier_done = False

    async def find_open(self, scope: str, source_kind: str):
        buffer = await super().find_open(scope, source_kind)
        if buffer is None and not self._barrier_done:
            self._waiting += 1
            if self._waiting == 2:
                self._barrier_done = True
                self._release.set()
            await self._release.wait()
        return buffer


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


def _event(
    *,
    run_id: str = "run-1",
    session_id: str = "session-1",
    user: str = "hello",
    assistant: str = "done",
    tokens: int = 10,
) -> RunCompleted:
    return RunCompleted(
        run_id=run_id,
        session_id=session_id,
        messages=(
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ),
        usage=Usage(prompt_tokens=tokens),
        result=assistant,
    )


def _ref(run_id: str) -> dict:
    return {"kind": "chat_msg", "ref": run_id, "captured_at": datetime.now(UTC).isoformat()}


def _connector(
    conn: aiosqlite.Connection,
    *,
    vectors: list[np.ndarray] | None = None,
    buffers: EpisodeBufferRepository | None = None,
    llm=None,
    dim: int = TEST_EMBEDDING_DIM,
) -> tuple[ChatConnector, EpisodeBufferRepository, AsyncMock]:
    items = MemoryItemsRepository(conn)
    buffers = buffers or EpisodeBufferRepository(conn)
    llm = llm or AsyncMock(return_value="fixed episode summary")
    connector = ChatConnector(
        items=items,
        buffers=buffers,
        embedder=MockEmbedder(vectors, dim=dim),
        llm_client=llm,
        boundary_classifier=EpisodeBoundaryClassifier(),
    )
    return connector, buffers, llm


async def _open_buffers(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall("SELECT * FROM episode_buffers WHERE closed_at IS NULL ORDER BY started_at, id")


async def _closed_buffers(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall("SELECT * FROM episode_buffers WHERE closed_at IS NOT NULL ORDER BY closed_at")


async def _items(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    return await conn.execute_fetchall("SELECT * FROM memory_items ORDER BY created_at, id")


async def _seed_buffer(
    buffers: EpisodeBufferRepository,
    *,
    count: int,
    tokens_per_turn: int = 1,
    embedding: np.ndarray | None = None,
):
    buffer = await buffers.create("user", "chat_msg")
    for index in range(count):
        buffer = await buffers.apply_turn(
            buffer.id,
            TurnUpdate(
                content=f"seed turn {index}",
                tokens=tokens_per_turn,
                source_ref=_ref(f"seed-{index}"),
                embedding=embedding if embedding is not None else _vec(0),
            ),
        )
    return buffer


@pytest.mark.asyncio
async def test_first_msg_creates_buffer(conn: aiosqlite.Connection):
    connector, _, _ = _connector(conn, vectors=[_vec(0)])

    await connector.on_run_completed(_event(run_id="run-1", user="hello", assistant="done", tokens=12))

    rows = await _open_buffers(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["scope"] == "user"
    assert row["source_kind"] == "chat_msg"
    assert row["turn_count"] == 1
    assert row["tokens"] == 12
    assert row["content_so_far"] == "User: hello\nAssistant: done"
    refs = json.loads(row["source_refs_so_far"])
    assert refs[0]["kind"] == "chat_msg"
    assert refs[0]["ref"] == "run-1"
    assert datetime.fromisoformat(refs[0]["captured_at"])


@pytest.mark.asyncio
async def test_subsequent_msg_updates_buffer(conn: aiosqlite.Connection):
    connector, _, _ = _connector(conn, vectors=[_vec(0), _near_vec()])

    await connector.on_run_completed(_event(run_id="run-1", user="first", tokens=5))
    await connector.on_run_completed(_event(run_id="run-2", user="second", tokens=7))

    rows = await _open_buffers(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["turn_count"] == 2
    assert row["tokens"] == 12
    assert "User: first" in row["content_so_far"]
    assert "User: second" in row["content_so_far"]
    refs = json.loads(row["source_refs_so_far"])
    assert [ref["ref"] for ref in refs] == ["run-1", "run-2"]
    centroid = np.frombuffer(row["running_centroid_vec"], dtype=np.float32)
    assert centroid[0] > 0.9
    assert centroid[1] > 0.2


@pytest.mark.asyncio
async def test_turn_budget_close(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    await _seed_buffer(buffers, count=49)

    await connector.on_run_completed(_event(run_id="run-50", user="budget", tokens=1))

    assert len(await _closed_buffers(conn)) == 1
    items = await _items(conn)
    assert len(items) == 1
    assert items[0]["kind"] == "episode"
    assert json.loads(items[0]["source_refs"])[-1]["ref"] == "seed-48"


@pytest.mark.asyncio
async def test_token_budget_close(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    await _seed_buffer(buffers, count=3, tokens_per_turn=2_500)

    await connector.on_run_completed(_event(run_id="run-token", user="cross token budget", tokens=500))

    assert len(await _closed_buffers(conn)) == 1
    items = await _items(conn)
    assert len(items) == 1
    assert items[0]["content"] == "fixed episode summary"


@pytest.mark.asyncio
async def test_idle_gap_close(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    buffer = await _seed_buffer(buffers, count=2)
    stale = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
    await conn.execute("UPDATE episode_buffers SET last_activity_at = ? WHERE id = ?", (stale, buffer.id))
    await conn.commit()

    await connector.on_run_completed(_event(run_id="run-idle", user="after idle", tokens=1))

    assert len(await _closed_buffers(conn)) == 1
    open_rows = await _open_buffers(conn)
    assert len(open_rows) == 1
    assert open_rows[0]["turn_count"] == 3
    assert json.loads(open_rows[0]["source_refs_so_far"])[-1]["ref"] == "run-idle"


@pytest.mark.asyncio
async def test_topic_shift_close(conn: aiosqlite.Connection):
    connector, _, _ = _connector(conn, vectors=[_vec(0), _vec(1), _vec(0)])

    await connector.on_run_completed(_event(run_id="run-1", user="memory work"))
    await connector.on_run_completed(_event(run_id="run-2", user="orthogonal subject"))

    assert len(await _closed_buffers(conn)) == 1
    items = await _items(conn)
    assert len(items) == 1
    assert json.loads(items[0]["source_refs"])[0]["ref"] == "run-1"


@pytest.mark.asyncio
async def test_explicit_close_marker(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    await _seed_buffer(buffers, count=1)

    await connector.on_run_completed(_event(run_id="run-switch", user="switching topic to deployments"))

    assert len(await _closed_buffers(conn)) == 1
    assert len(await _items(conn)) == 1


@pytest.mark.asyncio
async def test_overlap_carry(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    await _seed_buffer(buffers, count=7)

    await connector.on_run_completed(_event(run_id="run-close", user="new topic: carry me"))

    open_rows = await _open_buffers(conn)
    assert len(open_rows) == 1
    refs = json.loads(open_rows[0]["source_refs_so_far"])
    assert [ref["ref"] for ref in refs] == ["seed-2", "seed-3", "seed-4", "seed-5", "seed-6", "run-close"]
    assert "seed turn 1" not in open_rows[0]["content_so_far"]
    assert "seed turn 2" in open_rows[0]["content_so_far"]
    assert "User: new topic: carry me" in open_rows[0]["content_so_far"]


@pytest.mark.asyncio
async def test_unique_open_buffer_per_scope(conn: aiosqlite.Connection):
    buffers = BarrierBufferRepository(conn)
    llm = AsyncMock(return_value="fixed episode summary")
    connector = ChatConnector(
        items=MemoryItemsRepository(conn),
        buffers=buffers,
        embedder=MockEmbedder([_vec(0), _near_vec()]),
        llm_client=llm,
        boundary_classifier=EpisodeBoundaryClassifier(),
    )

    await asyncio.gather(
        connector.on_run_completed(_event(run_id="run-a", user="first")),
        connector.on_run_completed(_event(run_id="run-b", user="second")),
    )

    rows = await _open_buffers(conn)
    assert len(rows) == 1
    assert rows[0]["turn_count"] == 2
    refs = json.loads(rows[0]["source_refs_so_far"])
    assert sorted(ref["ref"] for ref in refs) == ["run-a", "run-b"]


@pytest.mark.asyncio
async def test_episode_item_has_valid_confidence_in_range(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    await _seed_buffer(buffers, count=49)

    await connector.on_run_completed(_event(run_id="run-confidence", user="close it"))

    items = await _items(conn)
    confidence = items[0]["confidence"]
    assert 0.0 <= confidence <= 1.0
    assert confidence_bucket(confidence) == "low"
    assert (
        compute_confidence(
            provenance="inferred",
            parent_confidences=[],
            contradiction_count=0,
            age_days=0,
            last_used_days=0,
            helped=0,
            hurt=0,
            ignored=0,
        )
        == pytest.approx(0.31875, abs=1e-9)
    )


@pytest.mark.asyncio
async def test_episode_item_source_refs_shape(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0), _vec(0)])
    await _seed_buffer(buffers, count=49)

    await connector.on_run_completed(_event(run_id="run-shape", user="close it"))

    refs = json.loads((await _items(conn))[0]["source_refs"])
    assert refs
    assert set(refs[0]) == {"kind", "ref", "captured_at"}
    assert refs[0]["kind"] == "chat_msg"
    assert refs[0]["ref"] == "seed-0"
    assert datetime.fromisoformat(refs[0]["captured_at"])


@pytest.mark.asyncio
async def test_connector_swallows_errors(conn: aiosqlite.Connection):
    llm = AsyncMock(side_effect=RuntimeError("summary failed"))
    connector, buffers, _ = _connector(conn, vectors=[_vec(0)], llm=llm)
    await _seed_buffer(buffers, count=49)

    result = await connector.on_run_completed(_event(run_id="run-error", user="close it"))

    assert result is None
    assert await _items(conn) == []


@pytest.mark.asyncio
async def test_idle_sweeper_closes_stale_buffers(conn: aiosqlite.Connection):
    connector, buffers, _ = _connector(conn, vectors=[_vec(0)])
    await buffers.create(
        "user",
        "chat_msg",
        carry=BufferCarry(
            content="stale carried content",
            source_refs=[_ref("stale-run")],
            centroid=_vec(0),
            turn_count=1,
            tokens=3,
        ),
    )
    stale = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
    await conn.execute("UPDATE episode_buffers SET last_activity_at = ?", (stale,))
    await conn.commit()

    await IdleBufferSweeper(connector).sweep_once()

    assert len(await _closed_buffers(conn)) == 1
    assert len(await _items(conn)) == 1
