"""Hybrid transcript search — FTS fused with the semantic index via RRF
(ntrp/context/store.py::search_messages, spec §A.5/D).

A FAKE SearchIndex returns a scripted vector hit (no real embeddings, no
search.db). Attaching it must fuse the FTS ranking with the vector ranking so a
message the FTS query alone would MISS still surfaces. Without an attached index,
search_messages is FTS-only and byte-for-byte unchanged.
"""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.context.models import SessionState
from ntrp.context.store import SessionStore

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "sessions.db")
    read_conn = await database.connect(tmp_path / "sessions.db", readonly=True)
    s = SessionStore(conn, read_conn)
    await s.init_schema()
    yield s
    await read_conn.close()
    await conn.close()


def _state(session_id: str, name: str | None = None) -> SessionState:
    return SessionState(session_id=session_id, started_at=datetime.now(UTC), name=name)


async def _seed(store: SessionStore, session_id: str, texts: list[str], *, name=None):
    msgs = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": t}
        for i, t in enumerate(texts)
    ]
    await store.save_session(_state(session_id, name=name), msgs)


# --- Fake SearchIndex: the minimal surface _hybrid_search_messages touches. ---


class _FakeItem:
    def __init__(self, metadata: dict):
        self.metadata = metadata


class _FakeStore:
    """Maps item_id -> (session_id, seq); vector_search returns a scripted hit."""

    def __init__(self, hits: list[tuple[int, float]], items: dict[int, dict]):
        self._hits = hits
        self._items = items

    async def vector_search(self, embedding, *, sources, limit):
        assert sources == ["transcript"]
        return list(self._hits)

    async def get_by_id(self, item_id):
        meta = self._items.get(item_id)
        return _FakeItem(meta) if meta is not None else None


class _FakeEmbedder:
    async def embed_one(self, text):
        return np.ones(8, dtype=np.float32)


class _FakeSearchIndex:
    def __init__(self, store, embedder):
        self.store = store
        self.embedder = embedder


async def test_fts_only_when_no_index_attached(store: SessionStore):
    await _seed(store, "s1", ["how do I deploy with kubernetes", "use kubectl apply"])

    res = await store.search_messages("kubernetes")
    assert res["has_more"] is False
    assert len(res["hits"]) == 1
    assert res["hits"][0]["session_id"] == "s1"
    assert "kubernetes" in res["hits"][0]["snippet"].lower()


async def test_attached_index_surfaces_a_vector_only_hit(store: SessionStore):
    # seq 0 matches the FTS query "kubernetes"; seq 1 does NOT lexically match,
    # but the vector index ranks it for this query.
    await _seed(store, "s1", ["how do I deploy with kubernetes", "use kubectl apply"])

    # The vector index ranks the non-lexical neighbor (seq 1) highly.
    fake = _FakeSearchIndex(
        _FakeStore(
            hits=[(100, 0.99)],
            items={100: {"session_id": "s1", "seq": 1, "role": "assistant"}},
        ),
        _FakeEmbedder(),
    )
    store.attach_search_index(fake)

    res = await store.search_messages("kubernetes")
    keys = {(h["session_id"], h["seq"]) for h in res["hits"]}
    # FTS contributes seq 0; the vector index contributes seq 1. RRF fuses both.
    assert ("s1", 0) in keys
    assert ("s1", 1) in keys


async def test_vector_failure_degrades_to_fts(store: SessionStore):
    await _seed(store, "s1", ["how do I deploy with kubernetes", "use kubectl apply"])

    class _BoomStore(_FakeStore):
        async def vector_search(self, embedding, *, sources, limit):
            raise RuntimeError("index offline")

    fake = _FakeSearchIndex(_BoomStore([], {}), _FakeEmbedder())
    store.attach_search_index(fake)

    # A broken vector side must not break search; FTS hit still returns.
    res = await store.search_messages("kubernetes")
    keys = {(h["session_id"], h["seq"]) for h in res["hits"]}
    assert ("s1", 0) in keys


async def test_index_skips_hits_with_missing_metadata(store: SessionStore):
    await _seed(store, "s1", ["how do I deploy with kubernetes", "use kubectl apply"])

    # Vector returns an item whose metadata lacks session_id/seq -> skipped, and
    # one item id with no stored item at all -> skipped. FTS hit remains.
    fake = _FakeSearchIndex(
        _FakeStore(hits=[(7, 0.9), (8, 0.8)], items={7: {"role": "user"}}),
        _FakeEmbedder(),
    )
    store.attach_search_index(fake)

    res = await store.search_messages("kubernetes")
    keys = {(h["session_id"], h["seq"]) for h in res["hits"]}
    assert ("s1", 0) in keys  # FTS still surfaces
    # No phantom hit from the metadata-less vector rows.
    assert all(k[0] == "s1" for k in keys)
