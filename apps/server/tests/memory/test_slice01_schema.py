from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.activation import MemoryActivationRequest
from ntrp.memory.retrieval import MemoryRetrieval
from ntrp.memory.store.base import GraphDatabase
from ntrp.memory.store.migrations import CURRENT_VERSION, run_migrations
from tests.conftest import TEST_EMBEDDING_DIM

KINDS = ("episode", "observation", "claim", "skill", "proposal", "artifact_ref")
ROLES = ("step", "evidence", "contradicts", "supersedes", "similar_to")


async def _connect_v30(tmp_path: Path) -> aiosqlite.Connection:
    conn = await database.connect(tmp_path / "memory.db", vec=True)
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '30');
    """)
    await run_migrations(conn)
    await GraphDatabase(conn, 1536).init_schema()
    return conn


class _FakeEmbedder:
    async def embed_one(self, text: str):
        import numpy as np

        vector = np.zeros(1536, dtype=np.float32)
        vector[0] = 1.0
        return vector


@pytest_asyncio.fixture
async def v31_conn(tmp_path: Path):
    conn = await _connect_v30(tmp_path)
    try:
        yield conn
    finally:
        await conn.close()


async def _insert_item(conn: aiosqlite.Connection, item_id: str, kind: str = "claim", content: str = "content") -> None:
    await conn.execute(
        """
        INSERT INTO memory_items (id, kind, content, provenance)
        VALUES (?, ?, ?, 'user_authored')
        """,
        (item_id, kind, content),
    )


@pytest.mark.asyncio
async def test_memory_items_round_trips_each_kind(v31_conn: aiosqlite.Connection):
    for kind in KINDS:
        await _insert_item(v31_conn, f"item-{kind}", kind, f"{kind} content")

    rows = await v31_conn.execute_fetchall("SELECT id, kind, content FROM memory_items ORDER BY id")
    assert [(row["id"], row["kind"], row["content"]) for row in rows] == [
        (f"item-{kind}", kind, f"{kind} content") for kind in sorted(KINDS)
    ]


@pytest.mark.asyncio
async def test_memory_item_parents_round_trips_each_role(v31_conn: aiosqlite.Connection):
    await _insert_item(v31_conn, "child")
    await _insert_item(v31_conn, "parent")

    for index, role in enumerate(ROLES):
        await v31_conn.execute(
            """
            INSERT INTO memory_item_parents (child_id, parent_id, role, "order")
            VALUES ('child', 'parent', ?, ?)
            """,
            (role, index),
        )

    rows = await v31_conn.execute_fetchall(
        'SELECT child_id, parent_id, role, "order" FROM memory_item_parents ORDER BY "order"'
    )
    assert [(row["child_id"], row["parent_id"], row["role"], row["order"]) for row in rows] == [
        ("child", "parent", role, index) for index, role in enumerate(ROLES)
    ]


@pytest.mark.asyncio
async def test_check_constraints_reject_invalid_kind_confidence_and_role(v31_conn: aiosqlite.Connection):
    await _insert_item(v31_conn, "child")
    await _insert_item(v31_conn, "parent")

    with pytest.raises(aiosqlite.IntegrityError):
        await _insert_item(v31_conn, "bad-kind", "nonsense")

    with pytest.raises(aiosqlite.IntegrityError):
        await v31_conn.execute(
            """
            INSERT INTO memory_items (id, kind, content, provenance, confidence)
            VALUES ('bad-confidence', 'claim', 'bad confidence', 'user_authored', 1.5)
            """
        )

    with pytest.raises(aiosqlite.IntegrityError):
        await v31_conn.execute(
            """
            INSERT INTO memory_item_parents (child_id, parent_id, role)
            VALUES ('child', 'parent', 'nonsense')
            """
        )


@pytest.mark.asyncio
async def test_memory_item_parent_edges_cascade_when_parent_or_child_is_deleted(v31_conn: aiosqlite.Connection):
    await _insert_item(v31_conn, "child-a")
    await _insert_item(v31_conn, "parent-a")
    await _insert_item(v31_conn, "child-b")
    await _insert_item(v31_conn, "parent-b")
    await v31_conn.executemany(
        "INSERT INTO memory_item_parents (child_id, parent_id, role) VALUES (?, ?, 'evidence')",
        [("child-a", "parent-a"), ("child-b", "parent-b")],
    )

    await v31_conn.execute("DELETE FROM memory_items WHERE id = 'parent-a'")
    await v31_conn.execute("DELETE FROM memory_items WHERE id = 'child-b'")

    rows = await v31_conn.execute_fetchall("SELECT child_id, parent_id FROM memory_item_parents")
    assert rows == []


@pytest.mark.asyncio
async def test_episode_buffers_allow_one_open_buffer_per_scope_and_source(v31_conn: aiosqlite.Connection):
    await v31_conn.execute(
        "INSERT INTO episode_buffers (id, scope, source_kind) VALUES ('buffer-1', 'user', 'chat_msg')"
    )

    with pytest.raises(aiosqlite.IntegrityError):
        await v31_conn.execute(
            "INSERT INTO episode_buffers (id, scope, source_kind) VALUES ('buffer-2', 'user', 'chat_msg')"
        )

    await v31_conn.execute("UPDATE episode_buffers SET closed_at = CURRENT_TIMESTAMP WHERE id = 'buffer-1'")
    await v31_conn.execute(
        "INSERT INTO episode_buffers (id, scope, source_kind) VALUES ('buffer-2', 'user', 'chat_msg')"
    )
    rows = await v31_conn.execute_fetchall("SELECT id FROM episode_buffers ORDER BY id")
    assert [row["id"] for row in rows] == ["buffer-1", "buffer-2"]


@pytest.mark.asyncio
async def test_memory_items_fts_round_trip_returns_matching_item(v31_conn: aiosqlite.Connection):
    await _insert_item(v31_conn, "needle", content="raretoken_zzzz lives here")
    await _insert_item(v31_conn, "haystack", content="ordinary unrelated text")

    rows = await v31_conn.execute_fetchall(
        """
        SELECT memory_items.id
        FROM memory_items_fts
        JOIN memory_items ON memory_items.id = memory_items_fts.item_id
        WHERE memory_items_fts MATCH 'raretoken_zzzz'
        """
    )
    assert [row["id"] for row in rows] == ["needle"]


@pytest.mark.asyncio
async def test_v31_migration_is_idempotent(v31_conn: aiosqlite.Connection):
    await run_migrations(v31_conn)
    await run_migrations(v31_conn)

    version = await v31_conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
    assert version[0][0] == str(CURRENT_VERSION)


@pytest.mark.asyncio
async def test_retrieval_handles_v31_schema_without_legacy_knowledge_tables(v31_conn: aiosqlite.Connection):
    bundle = await MemoryRetrieval(v31_conn, _FakeEmbedder()).search(
        MemoryActivationRequest(query="hello world", record_access=True)
    )

    assert bundle.candidates == []
    assert bundle.prompt_context == ""


@pytest.mark.asyncio
async def test_fresh_schema_reaches_v31_and_creates_new_tables(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db", vec=True)
    db = GraphDatabase(conn, TEST_EMBEDDING_DIM)
    try:
        await db.init_schema()

        version = await conn.execute_fetchall("SELECT value FROM meta WHERE key = 'schema_version'")
        assert version[0][0] == str(CURRENT_VERSION)
        tables = {
            row["name"] for row in await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"memory_items", "memory_item_parents", "episode_buffers", "memory_items_vec"}.issubset(tables)
        assert not {"observations_vec", "facts_vec", "knowledge_objects_vec"} & tables
    finally:
        await conn.close()
