"""LensExpander — retrieval-by-lens, read-only Mode-2 egress (LENS_CONTRACTS §3.7, §10).

Tmp in-memory SQLite ONLY — never ~/.ntrp/memory.db, never the network. The
expander takes (store, embed) only; no LLM client, no model id (§3.7, §11.3).

What these tests pin:
  - `lens_hint` resolving to a lens exposes its cached `lens_page` for the
    0-LLM verbatim-inject fast path (§5);
  - the member-constrained fallback returns the active `member_of` member set —
    a categorical existence predicate that the caller RANKS, never a gate (§0);
  - stale edges to superseded/archived members are filtered out at read
    (§1.1: edges dangle harmlessly, reads filter by current status);
  - no hint / no matching lens → None (caller runs unconstrained recall);
  - the expander never writes and issues no LLM calls (read-only, §3.7).
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio

from ntrp.memory.lens.expand import LensExpander
from ntrp.memory.models import (
    EdgeRole,
    Kind,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    Status,
)
from ntrp.memory.store import MemoryStore

USER = Scope(kind=ScopeKind.USER)


@pytest_asyncio.fixture
async def store():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn)
    await s.init_schema()
    yield s
    await conn.close()


def _claim(content: str, *, scope: Scope = USER) -> MemoryItem:
    return MemoryItem(
        id=str(uuid.uuid4()),
        kind=Kind.CLAIM,
        content=content,
        scope=scope,
        provenance=Provenance.RECORDED,
    )


def _lens(name: str, criterion: str, *, page: str | None = None, scope: Scope = USER) -> MemoryItem:
    return MemoryItem(
        id=str(uuid.uuid4()),
        kind=Kind.LENS,
        content=name,
        scope=scope,
        provenance=Provenance.USER_AUTHORED,
        lens_name=name,
        lens_criterion=criterion,
        lens_kind="topic",
        lens_page=page,
    )


async def _member(store: MemoryStore, claim: MemoryItem, lens: MemoryItem) -> None:
    await store.create_item(claim)
    await store.add_edge(MemoryEdge(child_id=claim.id, parent_id=lens.id, role=EdgeRole.MEMBER_OF))


@pytest.mark.asyncio
async def test_hint_resolves_by_exact_name_and_injects_page(store, fake_embedder):
    lens = _lens("Marathon Training", "anything about the user's marathon training",
                 page="# Marathon Training\n- Runs 5x a week. <!--claim:abc-->")
    await store.create_item(lens)

    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint="Marathon Training", goal="how is training going", scopes=[USER])

    assert out is not None
    assert out.lens.id == lens.id
    assert out.page is not None and "Runs 5x a week" in out.page


@pytest.mark.asyncio
async def test_member_constrained_pool_is_active_members_only(store, fake_embedder):
    """Member pre-filter returns active members; stale edges to dead claims drop."""
    lens = _lens("Marathon Training", "marathon training")
    await store.create_item(lens)

    live = _claim("Ran a 20-miler on Sunday.")
    stale = _claim("Old plan that was replaced.")
    await _member(store, live, lens)
    await _member(store, stale, lens)
    # The edge persists (§1.1: no remove_edge) but the claim leaves active status.
    await store.invalidate(stale.id, status=Status.SUPERSEDED)

    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint=lens.id, goal="recent runs", scopes=[USER])

    assert out is not None
    assert out.member_ids == frozenset({live.id})  # stale edge dangles, filtered at read
    assert out.page is None  # no cached page → caller falls back to member-constrained recall


@pytest.mark.asyncio
async def test_no_hint_returns_none(store, fake_embedder):
    await store.create_item(_lens("Marathon Training", "marathon training"))
    expander = LensExpander(store, fake_embedder)
    # No structural hint → we never guess a lens from goal prose (no lexical decision).
    assert await expander.expand(hint=None, goal="marathon training plan", scopes=[USER]) is None


@pytest.mark.asyncio
async def test_unmatched_hint_returns_none(store, fake_embedder):
    await store.create_item(_lens("Marathon Training", "marathon training"))
    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint="Quantum Chromodynamics", goal="qcd", scopes=[USER])
    assert out is None


@pytest.mark.asyncio
async def test_archived_lens_not_resolved(store, fake_embedder):
    lens = _lens("Marathon Training", "marathon training")
    await store.create_item(lens)
    await store.invalidate(lens.id, status=Status.ARCHIVED)  # deleted view (§3.4)

    expander = LensExpander(store, fake_embedder)
    assert await expander.expand(hint=lens.id, goal="x", scopes=[USER]) is None


@pytest.mark.asyncio
async def test_fts_recall_channel_resolves_when_no_exact_match(store, fake_embedder):
    """Channel B: FTS over lens text resolves a hint that is not the exact name."""
    if not store.has_fts:
        pytest.skip("FTS5 unavailable")
    lens = _lens("Running Log", "the user's marathon training and weekly mileage")
    await store.create_item(lens)

    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint="marathon training", goal="x", scopes=[USER])
    assert out is not None and out.lens.id == lens.id


@pytest.mark.asyncio
async def test_expander_is_read_only(store, fake_embedder):
    """No writes: the active-item set is unchanged after an expand call."""
    lens = _lens("Marathon Training", "marathon training", page="# page")
    await store.create_item(lens)
    claim = _claim("Ran today.")
    await _member(store, claim, lens)

    before = await store.query(kind=Kind.CLAIM, scope=USER, status=Status.ACTIVE, limit=100)
    lenses_before = await store.query(kind=Kind.LENS, scope=USER, status=Status.ACTIVE, limit=100)

    expander = LensExpander(store, fake_embedder)
    await expander.expand(hint=lens.id, goal="x", scopes=[USER])

    after = await store.query(kind=Kind.CLAIM, scope=USER, status=Status.ACTIVE, limit=100)
    lenses_after = await store.query(kind=Kind.LENS, scope=USER, status=Status.ACTIVE, limit=100)
    assert {c.id for c in before} == {c.id for c in after}
    assert {le.id for le in lenses_before} == {le.id for le in lenses_after}
