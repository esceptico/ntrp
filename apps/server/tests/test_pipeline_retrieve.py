"""Unit tests for the Stage-3 Retrieve component (CONTRACTS §9).

Tmp DBs only — never ~/.ntrp/memory.db. The embedder and cheap LLM are stubbed so
the tests are deterministic and offline. Coverage:
  - scope + validity + status hard filter (recall predicate, the only gate)
  - hybrid recall + transparent ordering (orders, never gates)
  - has_fts empty-vs-degraded resolution
  - also_scopes union
  - cheap verbatim compression to budget (no LLM) and LLM compression path
  - read-only invariant (no trust/recency writes)
"""

import uuid
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory import (
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    Status,
)
from ntrp.memory.pipeline.prompts_retrieve import CompressedClaim, CompressionResult
from ntrp.memory.pipeline.retrieve import Retriever
from ntrp.memory.pipeline.types import Retrieval
from ntrp.memory.store import MemoryStore

USER = Scope(ScopeKind.USER)
PROJECT = Scope(ScopeKind.PROJECT, "proj-1")


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db")  # tmp only
    store = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await store.init_schema()
    yield store
    await conn.close()


class FakeEmbedder:
    """Token-overlap pseudo-embeddings: deterministic, offline, monotone in
    lexical overlap with the goal so ordering is testable without a real model."""

    def __init__(self, vocab: list[str]):
        self.vocab = vocab

    def _vec(self, text: str) -> np.ndarray:
        toks = set(text.lower().split())
        v = np.array([1.0 if w in toks else 0.0 for w in self.vocab])
        n = np.linalg.norm(v)
        return v / n if n else v

    async def embed_one(self, text: str) -> np.ndarray:
        return self._vec(text)

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([])
        return np.stack([self._vec(t) for t in texts])


class FakeLLM:
    """Records calls; returns a scripted CompressionResult as the parsed object."""

    def __init__(self, result: CompressionResult):
        self.result = result
        self.calls = 0

    async def completion(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs

        class _Msg:
            content = self.result

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


def _vocab(*phrases: str) -> list[str]:
    seen: list[str] = []
    for p in phrases:
        for w in p.lower().split():
            if w not in seen:
                seen.append(w)
    return seen


async def _add(store, content, scope, **kw):
    item = MemoryItem(
        id=kw.get("id", str(uuid.uuid4())),
        content=content,
        canonical_subject=kw.get("canonical_subject", "Timur"),
        scope=scope,
        provenance=kw.get("provenance", Provenance.RECORDED),
        status=kw.get("status", Status.ACTIVE),
        valid_from=kw.get("valid_from"),
        invalid_at=kw.get("invalid_at"),
        corroboration=kw.get("corroboration", 0),
        last_relevant_at=kw.get("last_relevant_at"),
    )
    await store.create_item(item)
    return item.id


@pytest.mark.asyncio
async def test_scope_filter_excludes_other_scopes(store):
    await _add(store, "user likes espresso", USER, id="u1")
    await _add(store, "project deadline is friday", PROJECT, id="p1")

    r = Retriever(store, FakeEmbedder(_vocab("user likes espresso project deadline friday")), FakeLLM(CompressionResult()))
    out = await r.retrieve(Retrieval(goal="espresso", scope=USER))
    assert {ri.item.id for ri in out.items} == {"u1"}


@pytest.mark.asyncio
async def test_also_scopes_union(store):
    await _add(store, "user likes espresso", USER, id="u1")
    await _add(store, "project espresso machine arrives", PROJECT, id="p1")

    r = Retriever(store, FakeEmbedder(_vocab("user likes espresso machine project arrives")), FakeLLM(CompressionResult()))
    out = await r.retrieve(Retrieval(goal="espresso", scope=USER, also_scopes=[PROJECT]))
    assert {ri.item.id for ri in out.items} == {"u1", "p1"}


@pytest.mark.asyncio
async def test_validity_filter_excludes_expired_and_superseded(store):
    await _add(store, "current address is oak street", USER, id="active1")
    await _add(
        store,
        "old address was elm street",
        USER,
        id="expired1",
        valid_from="2000-01-01T00:00:00+00:00",
        invalid_at="2001-01-01T00:00:00+00:00",
        status=Status.SUPERSEDED,
    )

    r = Retriever(store, FakeEmbedder(_vocab("current address oak street old was elm")), FakeLLM(CompressionResult()))
    out = await r.retrieve(Retrieval(goal="address", scope=USER))
    ids = {ri.item.id for ri in out.items}
    assert "active1" in ids
    assert "expired1" not in ids


@pytest.mark.asyncio
async def test_ordering_orders_never_gates(store):
    await _add(store, "timur prefers tea", USER, id="high", provenance=Provenance.USER_AUTHORED, corroboration=5)
    await _add(store, "timur prefers tea", USER, id="low", provenance=Provenance.INFERRED, corroboration=0)

    r = Retriever(store, FakeEmbedder(_vocab("timur prefers tea")), FakeLLM(CompressionResult()))
    out = await r.retrieve(Retrieval(goal="timur tea", scope=USER))
    ids = [ri.item.id for ri in out.items]
    assert set(ids) == {"high", "low"}  # neither gated out
    assert ids[0] == "high"  # higher provenance + corroboration orders first


@pytest.mark.asyncio
async def test_empty_pool_returns_empty_not_degraded(store):
    r = Retriever(store, FakeEmbedder(_vocab("anything")), FakeLLM(CompressionResult()))
    out = await r.retrieve(Retrieval(goal="nothing here", scope=USER))
    assert out.items == []
    assert out.rendered == ""
    assert out.degraded is False  # FTS available, just genuinely empty


@pytest.mark.asyncio
async def test_degraded_when_fts_unavailable(store):
    await _add(store, "user likes espresso", USER, id="u1")
    store._has_fts = False  # simulate FTS5 unavailable

    r = Retriever(store, FakeEmbedder(_vocab("user likes espresso")), FakeLLM(CompressionResult()))
    out = await r.retrieve(Retrieval(goal="espresso", scope=USER))
    assert out.degraded is True
    assert {ri.item.id for ri in out.items} == {"u1"}  # still recalled via query()


@pytest.mark.asyncio
async def test_cheap_compression_fits_budget_no_llm(store):
    await _add(store, "user likes espresso", USER, id="u1")
    llm = FakeLLM(CompressionResult())
    r = Retriever(store, FakeEmbedder(_vocab("user likes espresso")), llm, model="cheap")
    out = await r.retrieve(Retrieval(goal="espresso", scope=USER, token_budget=2000))
    assert "espresso" in out.rendered
    assert llm.calls == 0  # everything fit; no LLM compression


@pytest.mark.asyncio
async def test_llm_compression_path_selects_by_index(store):
    for i in range(12):
        await _add(store, f"timur fact number {i} about tea", USER, id=f"c{i}")

    llm = FakeLLM(CompressionResult(kept=[CompressedClaim(index=0, rendered="kept tea fact")]))
    r = Retriever(store, FakeEmbedder(_vocab("timur fact number about tea")), llm, model="cheap")
    out = await r.retrieve(Retrieval(goal="tea", scope=USER, token_budget=2))
    assert llm.calls == 1
    assert "kept tea fact" in out.rendered


@pytest.mark.asyncio
async def test_llm_compression_drops_out_of_range_indices(store):
    for i in range(12):
        await _add(store, f"timur fact number {i} about tea", USER, id=f"c{i}")

    llm = FakeLLM(
        CompressionResult(
            kept=[
                CompressedClaim(index=999, rendered="bogus"),
                CompressedClaim(index=1, rendered="valid kept"),
            ]
        )
    )
    r = Retriever(store, FakeEmbedder(_vocab("timur fact number about tea")), llm, model="cheap")
    out = await r.retrieve(Retrieval(goal="tea", scope=USER, token_budget=2))
    assert "valid kept" in out.rendered
    assert "bogus" not in out.rendered


@pytest.mark.asyncio
async def test_no_writes_during_retrieve(store):
    await _add(store, "user likes espresso", USER, id="u1", corroboration=3)
    r = Retriever(store, FakeEmbedder(_vocab("user likes espresso")), FakeLLM(CompressionResult()))
    await r.retrieve(Retrieval(goal="espresso", scope=USER))

    after = await store.get("u1")
    assert after.corroboration == 3  # untouched: Retrieve never bumps trust
    assert after.last_relevant_at is None  # untouched: no "mark recalled" write
    assert after.status is Status.ACTIVE
