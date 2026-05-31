from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.items_store import (
    MemoryItemInsert,
    MemoryItemsRepository,
    OutcomeEventInsert,
    UsageEventInsert,
)
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


async def test_update_item_edits_fields_and_reembeds(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "original")

    await repo.update_item(
        item_id,
        content="edited content",
        title="New title",
        confidence=0.3,
        tags=["curated"],
        scope="user",
        status="archived",
        invalid_at=None,
        embedding=np.full(TEST_EMBEDDING_DIM, 0.5, dtype=np.float32),
    )

    item = await repo.get_item(item_id)
    assert item.content == "edited content"
    assert item.title == "New title"
    assert item.confidence == 0.3
    assert item.tags == ["curated"]
    assert item.status == "archived"
    assert item.embedding is not None
    assert float(item.embedding[0]) == pytest.approx(0.5)


async def test_update_item_keeps_embedding_when_none(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "keep embedding")

    await repo.update_item(
        item_id, content="keep embedding", title=None, confidence=0.8,
        tags=[], scope="user", status="active", invalid_at=None, embedding=None,
    )

    item = await repo.get_item(item_id)
    assert item.embedding is not None
    # np.ones(4) is L2-normalized on store → each component 0.5; unchanged when embedding=None
    assert float(item.embedding[0]) == pytest.approx(0.5)


async def test_update_item_syncs_fts(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "alpha aaaunique")
    await repo.update_item(
        item_id, content="beta bbbunique", title=None, confidence=0.8,
        tags=[], scope="user", status="active", invalid_at=None, embedding=None,
    )
    rows = await conn.execute_fetchall(
        "SELECT item_id FROM memory_items_fts WHERE memory_items_fts MATCH ?", ("bbbunique",)
    )
    assert [r["item_id"] for r in rows] == [item_id]
    rows = await conn.execute_fetchall(
        "SELECT item_id FROM memory_items_fts WHERE memory_items_fts MATCH ?", ("aaaunique",)
    )
    assert rows == []


async def test_delete_item_cascades_edges(conn):
    repo = MemoryItemsRepository(conn)
    child = await _item(repo, "child")
    parent = await _item(repo, "parent")
    await repo.insert_parent_edge(child, parent, "evidence")

    await repo.delete_item(parent)

    assert await repo.get_item(parent) is None
    assert await repo.get_item(child) is not None
    assert await repo.list_parent_edges(child) == []


async def test_insert_usage_event_persists_row_and_returns_id(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "usage event target")

    event_id = await repo.insert_usage_event(
        UsageEventInsert(
            item_id=item_id,
            bundle_id="bundle-1",
            surface="prompt",
            rank=0,
            score=0.42,
            selection_role="advisory",
            reason="claim is advisory guidance",
            run_id="run-1",
            session_scope="proj_abc",
        )
    )

    assert isinstance(event_id, int)
    rows = await conn.execute_fetchall(
        "SELECT * FROM memory_usage_events WHERE id = ?", (event_id,)
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["item_id"] == item_id
    assert row["bundle_id"] == "bundle-1"
    assert row["surface"] == "prompt"
    assert row["rank"] == 0
    assert row["score"] == pytest.approx(0.42)
    assert row["selection_role"] == "advisory"
    assert row["run_id"] == "run-1"
    assert row["session_scope"] == "proj_abc"
    assert row["created_at"]


@pytest.mark.parametrize(
    "outcome,usage_key",
    [("helpful", "helped"), ("harmful", "hurt"), ("irrelevant", "ignored")],
)
async def test_record_outcome_increments_usage_counter(conn, outcome, usage_key):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "outcome target")

    event_id = await repo.record_outcome(
        OutcomeEventInsert(item_id=item_id, outcome=outcome, source="api", run_id="run-1")
    )

    assert isinstance(event_id, int)
    rows = await conn.execute_fetchall(
        "SELECT * FROM memory_outcome_events WHERE id = ?", (event_id,)
    )
    assert len(rows) == 1
    assert rows[0]["item_id"] == item_id
    assert rows[0]["outcome"] == outcome
    assert rows[0]["source"] == "api"
    assert rows[0]["run_id"] == "run-1"

    item = await repo.get_item(item_id)
    assert item.usage[usage_key] == 1
    for other in {"helped", "hurt", "ignored"} - {usage_key}:
        assert item.usage[other] == 0


async def test_record_outcome_non_counter_outcome_logs_without_moving_usage(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "non-counter outcome target")

    event_id = await repo.record_outcome(
        OutcomeEventInsert(item_id=item_id, outcome="task_success", source="run")
    )

    rows = await conn.execute_fetchall(
        "SELECT * FROM memory_outcome_events WHERE id = ?", (event_id,)
    )
    assert rows[0]["outcome"] == "task_success"
    item = await repo.get_item(item_id)
    assert item.usage == {"activated": 0, "helped": 0, "hurt": 0, "ignored": 0}


async def test_record_outcome_accumulates_across_calls(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "accumulate target")

    await repo.record_outcome(OutcomeEventInsert(item_id=item_id, outcome="helpful", source="api"))
    await repo.record_outcome(OutcomeEventInsert(item_id=item_id, outcome="helpful", source="api"))
    await repo.record_outcome(OutcomeEventInsert(item_id=item_id, outcome="harmful", source="api"))

    item = await repo.get_item(item_id)
    assert item.usage["helped"] == 2
    assert item.usage["hurt"] == 1


async def test_increment_usage_counter_rejects_unknown_key(conn):
    repo = MemoryItemsRepository(conn)
    item_id = await _item(repo, "bad key target")
    with pytest.raises(ValueError):
        await repo.increment_usage_counter(item_id, "bogus")
