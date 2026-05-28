from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.items_store import MemoryItemInsert, MemoryItemsRepository
from ntrp.memory.store.base import GraphDatabase

if TYPE_CHECKING:
    from pathlib import Path


TEST_EMBEDDING_DIM = 4
pytestmark = pytest.mark.asyncio


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


async def _item(repo: MemoryItemsRepository, content: str) -> str:
    return await repo.insert_item(
        MemoryItemInsert(
            kind="claim",
            content=content,
            source_refs=[],
            confidence=0.8,
            scope="user",
            embedding=np.ones(TEST_EMBEDDING_DIM, dtype=np.float32),
        )
    )


async def test_parent_graph_rejects_self_edge(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "self")

    with pytest.raises(ValueError, match="acyclic"):
        await repo.insert_parent_edge(item_id, item_id, "evidence")


async def test_parent_graph_rejects_direct_cycle(conn):
    repo = MemoryItemsRepository(conn)
    child = await _item(repo, "child")
    parent = await _item(repo, "parent")
    await repo.insert_parent_edge(child, parent, "evidence")

    with pytest.raises(ValueError, match="acyclic"):
        await repo.insert_parent_edge(parent, child, "evidence")


async def test_parent_graph_rejects_transitive_cycle(conn):
    repo = MemoryItemsRepository(conn)
    leaf = await _item(repo, "leaf")
    middle = await _item(repo, "middle")
    root = await _item(repo, "root")
    await repo.insert_parent_edge(leaf, middle, "evidence")
    await repo.insert_parent_edge(middle, root, "evidence")

    with pytest.raises(ValueError, match="acyclic"):
        await repo.insert_parent_edge(root, leaf, "evidence")


async def test_parent_graph_allows_valid_dag(conn):
    repo = MemoryItemsRepository(conn)
    child = await _item(repo, "child")
    parent_a = await _item(repo, "parent a")
    parent_b = await _item(repo, "parent b")

    await repo.insert_parent_edge(child, parent_a, "evidence")
    await repo.insert_parent_edge(child, parent_b, "similar_to")

    edges = await repo.list_parent_edges(child)
    assert {(edge.parent_id, edge.role) for edge in edges} == {(parent_a, "evidence"), (parent_b, "similar_to")}
