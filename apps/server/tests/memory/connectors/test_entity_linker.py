import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory.connectors.entity_linker import _parse_decisions, _parse_mentions, link_entities
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


async def _seed_claim(items: MemoryItemsRepository, content: str, embedding: np.ndarray) -> str:
    return await items.insert_item(
        MemoryItemInsert(
            kind="claim", content=content, provenance="inferred", source_refs=[], confidence=0.5, embedding=embedding
        )
    )


async def _seed_entity(items: MemoryItemsRepository, name: str, embedding: np.ndarray, *, content: str | None = None) -> str:
    return await items.insert_item(
        MemoryItemInsert(
            kind="entity",
            content=content or name,
            title=name,
            provenance="inferred",
            source_refs=[],
            confidence=0.6,
            embedding=embedding,
        )
    )


async def _entities(conn) -> list:
    return await conn.execute_fetchall("SELECT * FROM memory_items WHERE kind='entity' ORDER BY created_at, id")


async def _mentions_edges(conn, claim_id: str) -> list:
    return await conn.execute_fetchall(
        "SELECT parent_id, role FROM memory_item_parents WHERE child_id = ? AND role = 'mentions'", (claim_id,)
    )


# ---- pure parsing ---------------------------------------------------------


def test_parse_mentions_splits_and_strips():
    assert _parse_mentions("- Regina Lin\n2. Postgres\n") == ["Regina Lin", "Postgres"]


def test_parse_mentions_none_sentinel_is_empty():
    assert _parse_mentions("NONE") == []


def test_parse_decisions_length_mismatch_fails_open_to_new():
    decisions = _parse_decisions(json.dumps([{"action": "LINK"}]), 2)
    assert [d.action for d in decisions] == ["NEW", "NEW"]


def test_parse_decisions_garbage_fails_open_to_new():
    decisions = _parse_decisions("not json", 1)
    assert decisions[0].action == "NEW"


# ---- mention extraction ---------------------------------------------------


@pytest.mark.asyncio
async def test_no_mentions_links_nothing(conn):
    items = MemoryItemsRepository(conn)
    claim_id = await _seed_claim(items, "the deadline is friday", _vec(0))

    linked = await link_entities(
        claim_id=claim_id,
        claim_content="the deadline is friday",
        scope="user",
        items=items,
        embedder=MockEmbedder(),
        mention_client=AsyncMock(return_value="NONE"),
        adjudicate_client=AsyncMock(),
    )

    assert linked == []
    assert await _entities(conn) == []
    assert await _mentions_edges(conn, claim_id) == []


# ---- adjudication actions -------------------------------------------------


@pytest.mark.asyncio
async def test_new_mints_entity_with_mentions_edge_and_confidence_below_one(conn):
    items = MemoryItemsRepository(conn)
    claim_id = await _seed_claim(items, "Regina Lin mentors at MATS", _vec(0))

    linked = await link_entities(
        claim_id=claim_id,
        claim_content="Regina Lin mentors at MATS",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),  # mention embedding; no existing entity recalled
        mention_client=AsyncMock(return_value="Regina Lin"),
        adjudicate_client=AsyncMock(),  # no candidates -> not called
    )

    rows = await _entities(conn)
    assert len(rows) == 1
    assert rows[0]["title"] == "Regina Lin"
    assert rows[0]["provenance"] == "inferred"
    assert 0.0 < rows[0]["confidence"] < 1.0
    assert linked == [rows[0]["id"]]
    edges = await _mentions_edges(conn, claim_id)
    assert [(e["parent_id"], e["role"]) for e in edges] == [(rows[0]["id"], "mentions")]


@pytest.mark.asyncio
async def test_link_attaches_to_existing_entity_without_minting_or_rewriting(conn):
    # "Regina" links to the stored "Regina Lin" (hybrid recall, not title-exact) and
    # the existing profile is left untouched — linking never rewrites.
    items = MemoryItemsRepository(conn)
    entity_id = await _seed_entity(items, "Regina Lin", _vec(1), content="Regina Lin — MATS mentor")
    claim_id = await _seed_claim(items, "Regina lives in Berkeley", _vec(0))

    adjudicate = AsyncMock(
        return_value=json.dumps([{"action": "LINK", "target_id": entity_id, "reason": "same person"}])
    )
    linked = await link_entities(
        claim_id=claim_id,
        claim_content="Regina lives in Berkeley",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),  # recalls the Regina Lin entity
        mention_client=AsyncMock(return_value="Regina"),
        adjudicate_client=adjudicate,
    )

    rows = await _entities(conn)
    assert len(rows) == 1  # nothing minted
    assert rows[0]["content"] == "Regina Lin — MATS mentor"  # profile untouched
    assert linked == [entity_id]
    edges = await _mentions_edges(conn, claim_id)
    assert [(e["parent_id"], e["role"]) for e in edges] == [(entity_id, "mentions")]
    # the recalled candidate was offered to the adjudicator
    assert entity_id in adjudicate.call_args[0][0]


@pytest.mark.asyncio
async def test_none_action_skips_mention(conn):
    items = MemoryItemsRepository(conn)
    existing = await _seed_entity(items, "Postgres", _vec(1))
    claim_id = await _seed_claim(items, "the user prefers things", _vec(0))

    linked = await link_entities(
        claim_id=claim_id,
        claim_content="the user prefers things",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),  # recalls Postgres so the adjudicator is invoked
        mention_client=AsyncMock(return_value="the user"),
        adjudicate_client=AsyncMock(
            return_value=json.dumps([{"action": "NONE", "target_id": None, "reason": "not a durable entity"}])
        ),
    )

    assert linked == []
    assert len(await _entities(conn)) == 1  # only the pre-existing one, nothing minted
    assert await _mentions_edges(conn, claim_id) == []
    assert existing  # referenced


@pytest.mark.asyncio
async def test_under_merge_mints_new_when_adjudicator_says_new_despite_recall(conn):
    # A different Regina is recalled but the adjudicator judges them distinct -> mint,
    # never collapse two people.
    items = MemoryItemsRepository(conn)
    other = await _seed_entity(items, "Regina Spektor", _vec(1))
    claim_id = await _seed_claim(items, "Regina Lin mentors at MATS", _vec(0))

    linked = await link_entities(
        claim_id=claim_id,
        claim_content="Regina Lin mentors at MATS",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(1)]),  # recalls Regina Spektor
        mention_client=AsyncMock(return_value="Regina Lin"),
        adjudicate_client=AsyncMock(
            return_value=json.dumps([{"action": "NEW", "target_id": None, "reason": "different Regina"}])
        ),
    )

    rows = await _entities(conn)
    assert len(rows) == 2  # the other Regina plus a freshly minted Regina Lin
    minted = [r for r in rows if r["id"] != other]
    assert len(minted) == 1
    assert minted[0]["title"] == "Regina Lin"
    assert linked == [minted[0]["id"]]


@pytest.mark.asyncio
async def test_recall_is_not_title_exact(conn):
    # Directly exercise the recall: a partial mention surfaces a longer-titled entity.
    items = MemoryItemsRepository(conn)
    entity_id = await _seed_entity(items, "Regina Lin", _vec(1))

    recalled = await items.recall_entities(query="Regina", embedding=_vec(1), scope="user", limit=10)
    assert any(item.id == entity_id for item in recalled)


@pytest.mark.asyncio
async def test_link_then_new_in_one_batch(conn):
    items = MemoryItemsRepository(conn)
    postgres = await _seed_entity(items, "Postgres", _vec(1))
    claim_id = await _seed_claim(items, "Timur runs the app on Postgres", _vec(0))

    linked = await link_entities(
        claim_id=claim_id,
        claim_content="Timur runs the app on Postgres",
        scope="user",
        items=items,
        embedder=MockEmbedder([_vec(2), _vec(1)]),  # "Timur" recalls nothing, "Postgres" recalls postgres
        mention_client=AsyncMock(return_value="Timur\nPostgres"),
        adjudicate_client=AsyncMock(
            return_value=json.dumps(
                [
                    {"action": "NEW", "target_id": None, "reason": "new person"},
                    {"action": "LINK", "target_id": postgres, "reason": "same db"},
                ]
            )
        ),
    )

    rows = await _entities(conn)
    assert len(rows) == 2  # postgres + new Timur
    assert postgres in linked
    edges = {e["parent_id"] for e in await _mentions_edges(conn, claim_id)}
    assert postgres in edges
    assert len(edges) == 2
