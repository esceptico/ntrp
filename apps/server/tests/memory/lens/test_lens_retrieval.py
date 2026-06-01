"""LensExpander — retrieval-by-lens, read-only Mode-2 egress.

Tmp in-memory SQLite ONLY — never ~/.ntrp/memory.db, never the network. The
expander takes (store, embed) only; no LLM client, no model id.

A lens is a VIEW: members come from `lens_membership_cache` (`in` decisions),
never a member_of edge. What these tests pin:
  - a `hint` resolving to a lens exposes its cached `page` for the 0-LLM verbatim-
    inject fast path;
  - the member-constrained fallback returns the active `in`-cache member set — a
    categorical existence predicate the caller RANKS, never a gate;
  - stale cache rows pointing at superseded/archived claims are filtered at read;
  - no hint / no matching lens → None (caller runs unconstrained recall);
  - an archived lens never resolves (deleted view);
  - the expander never writes and issues no LLM calls (read-only).
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio

from ntrp.memory.lens.expand import LensExpander
from ntrp.memory.models import (
    LensProvenance,
    LensRow,
    LensStatus,
    MembershipDecision,
    MembershipVerdict,
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
        content=content,
        canonical_subject="Tim",
        scope=scope,
        provenance=Provenance.RECORDED,
    )


def _lens(name: str, criterion: str, *, page: str | None = None, scope: Scope = USER) -> LensRow:
    return LensRow(
        id=str(uuid.uuid4()),
        name=name,
        criterion=criterion,
        scope=scope,
        provenance=LensProvenance.USER_AUTHORED,
        page=page,
    )


async def _member(store: MemoryStore, claim: MemoryItem, lens: LensRow) -> None:
    await store.create_item(claim)
    await store.put_membership(
        [MembershipVerdict(lens_id=lens.id, claim_id=claim.id, decision=MembershipDecision.IN)]
    )


@pytest.mark.asyncio
async def test_hint_resolves_by_exact_name_and_injects_page(store, fake_embedder):
    lens = _lens("Marathon Training", "anything about the user's marathon training",
                 page="# Marathon Training\n- Runs 5x a week. <!--claim:abc-->")
    await store.create_lens_row(lens)

    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint="Marathon Training", goal="how is training going", scopes=[USER])

    assert out is not None
    assert out.lens.id == lens.id
    assert out.page is not None and "Runs 5x a week" in out.page


@pytest.mark.asyncio
async def test_member_constrained_pool_is_active_members_only(store, fake_embedder):
    """Member pre-filter returns active members; cache rows to dead claims drop."""
    lens = _lens("Marathon Training", "marathon training")
    await store.create_lens_row(lens)

    live = _claim("Ran a 20-miler on Sunday.")
    stale = _claim("Old plan that was replaced.")
    await _member(store, live, lens)
    await _member(store, stale, lens)
    # The cache row persists, but the claim leaves active status.
    await store.invalidate(stale.id, status=Status.SUPERSEDED)

    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint=lens.id, goal="recent runs", scopes=[USER])

    assert out is not None
    assert out.member_ids == frozenset({live.id})  # stale cache row filtered at read
    assert out.page is None  # no cached page → caller falls back to member-constrained recall


@pytest.mark.asyncio
async def test_no_hint_returns_none(store, fake_embedder):
    await store.create_lens_row(_lens("Marathon Training", "marathon training"))
    expander = LensExpander(store, fake_embedder)
    # No structural hint → we never guess a lens from goal prose (no lexical decision).
    assert await expander.expand(hint=None, goal="marathon training plan", scopes=[USER]) is None


@pytest.mark.asyncio
async def test_unmatched_hint_returns_none(store, fake_embedder):
    await store.create_lens_row(_lens("Marathon Training", "marathon training"))
    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint="Quantum Chromodynamics", goal="qcd", scopes=[USER])
    assert out is None


@pytest.mark.asyncio
async def test_archived_lens_not_resolved(store, fake_embedder):
    lens = _lens("Marathon Training", "marathon training")
    await store.create_lens_row(lens)
    await store.update_lens(lens.id, status=LensStatus.ARCHIVED)  # deleted view

    expander = LensExpander(store, fake_embedder)
    assert await expander.expand(hint=lens.id, goal="x", scopes=[USER]) is None


@pytest.mark.asyncio
async def test_fts_recall_channel_resolves_when_no_exact_match(store, fake_embedder):
    """Channel B: FTS over lens text resolves a hint that is not the exact name."""
    if not store.has_fts:
        pytest.skip("FTS5 unavailable")
    lens = _lens("Running Log", "the user's marathon training and weekly mileage")
    await store.create_lens_row(lens)

    expander = LensExpander(store, fake_embedder)
    out = await expander.expand(hint="marathon training", goal="x", scopes=[USER])
    assert out is not None and out.lens.id == lens.id


@pytest.mark.asyncio
async def test_expander_is_read_only(store, fake_embedder):
    """No writes: the active claim + lens sets are unchanged after an expand call."""
    lens = _lens("Marathon Training", "marathon training", page="# page")
    await store.create_lens_row(lens)
    claim = _claim("Ran today.")
    await _member(store, claim, lens)

    before = await store.query(scope=USER, status=Status.ACTIVE, limit=100)
    lenses_before = await store.list_lenses(scope=USER)

    expander = LensExpander(store, fake_embedder)
    await expander.expand(hint=lens.id, goal="x", scopes=[USER])

    after = await store.query(scope=USER, status=Status.ACTIVE, limit=100)
    lenses_after = await store.list_lenses(scope=USER)
    assert {c.id for c in before} == {c.id for c in after}
    assert {le.id for le in lenses_before} == {le.id for le in lenses_after}
