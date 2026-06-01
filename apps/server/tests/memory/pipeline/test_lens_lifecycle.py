"""Lens lifecycle / CRUD unit tests — LENS_CONTRACTS §3.4, §3.5, §6, §10.

Offline only: in-memory SQLite store, a FakeMembership double that records
backfill/coverage calls. NEVER opens ~/.ntrp/memory.db, never the network, never
a real LLM. Lifecycle makes no membership decision of its own — the double stands
in for the LLM judge — so there is no verdict to fake here.

These tests assert the frozen store invariants this layer must honor:
  - create -> backfill (Mode 3, once per new lens, §3.6)
  - edit_criterion -> supersede + dirty watermark, NO edge mutation (§6)
  - delete -> archive the view; claims + member_of edges survive (§1.1, §3.4)
  - merge -> re-derive via backfill_lens, NEVER _inherit_members (§3.5)
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio

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
from ntrp.memory.pipeline.lens import LENS_DIRTY_PREFIX, LensService
from ntrp.memory.pipeline.types import BackfillReport, CoverageAdvisory
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


class FakeMembership:
    """The membership judge stand-in. Records every backfill/coverage call so
    tests can assert the add-only re-derive contract (§3.4/§3.5) without an LLM.

    `backfill_lens` mints one canned member_of edge per call (so create/merge can
    be observed to attach members) and records the lens it was asked to derive.
    `coverage` returns a scripted advisory. It never decides membership beyond the
    scripted edge — the real judge does that; here we only verify orchestration.
    """

    def __init__(self, store: MemoryStore, *, ratio: float = 0.0):
        self.store = store
        self.ratio = ratio
        self.backfilled: list[str] = []
        self.coverage_calls: list[str] = []
        self._seed: dict[str, list[str]] = {}

    def seed_pool(self, lens_id: str, claim_ids: list[str]) -> None:
        self._seed[lens_id] = claim_ids

    async def backfill_lens(self, lens_id: str) -> BackfillReport:
        self.backfilled.append(lens_id)
        claim_ids = self._seed.get(lens_id, [])
        for cid in claim_ids:
            await self.store.add_edge(
                MemoryEdge(child_id=cid, parent_id=lens_id, role=EdgeRole.MEMBER_OF)
            )
        return BackfillReport(
            lens_id=lens_id,
            scanned=len(claim_ids),
            members_added=len(claim_ids),
            capped=False,
        )

    async def coverage(self, lens_id: str, scope: Scope) -> CoverageAdvisory:
        self.coverage_calls.append(lens_id)
        return CoverageAdvisory(
            lens_id=lens_id,
            scope_pool=10,
            member_count=int(self.ratio * 10),
            ratio=self.ratio,
            generic=self.ratio >= 0.5,
            suggestion="split" if self.ratio >= 0.5 else "narrow",
        )


def _service(store, membership):
    # projector/writeback are held but not exercised by any lifecycle verb.
    return LensService(store, membership, projector=None, writeback=None)


async def _claim(store, content):
    item = MemoryItem(
        id=uuid.uuid4().hex,
        kind=Kind.CLAIM,
        content=content,
        scope=USER,
        provenance=Provenance.RECORDED,
    )
    await store.create_item(item)
    return item


# --- create -> backfill ---------------------------------------------


@pytest.mark.asyncio
async def test_create_lens_mints_topic_lens_and_backfills_once(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)

    lens = await svc.create_lens("Climbing", "about rock climbing", USER)

    assert lens.kind is Kind.LENS
    assert lens.lens_kind == "topic"
    assert lens.lens_exclusive is False
    assert lens.lens_name == "Climbing"
    assert lens.lens_criterion == "about rock climbing"
    assert lens.provenance is Provenance.USER_AUTHORED
    # Mode 3: exactly one backfill per new lens.
    assert mem.backfilled == [lens.id]

    persisted = await store.get(lens.id)
    assert persisted is not None and persisted.status is Status.ACTIVE


@pytest.mark.asyncio
async def test_create_user_lens_kind_passthrough(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    lens = await svc.create_lens("Me", "about the user", USER, lens_kind="user")
    assert lens.lens_kind == "user"
    assert lens.lens_exclusive is False


# --- list with advisory ---------------------------------------------


@pytest.mark.asyncio
async def test_list_lenses_carries_coverage_advisory(store):
    mem = FakeMembership(store, ratio=0.3)
    svc = _service(store, mem)
    a = await svc.create_lens("A", "crit a", USER)
    b = await svc.create_lens("B", "crit b", USER)

    rows = await svc.list_lenses(USER)
    ids = {lens.id for lens, _ in rows}
    assert {a.id, b.id} <= ids
    for lens, advisory in rows:
        assert advisory.lens_id == lens.id
        assert advisory.generic is False  # ratio 0.3 < 0.5
    assert set(mem.coverage_calls) >= {a.id, b.id}


# --- edit_criterion: supersede + dirty, NO edge mutation (§6) -------


@pytest.mark.asyncio
async def test_edit_criterion_supersedes_and_marks_dirty_without_touching_edges(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    c1 = await _claim(store, "alice climbs")
    lens = await svc.create_lens("Climbing", "about climbing", USER)
    mem.seed_pool(lens.id, [c1.id])
    # simulate a member attached during the initial backfill
    await store.add_edge(
        MemoryEdge(child_id=c1.id, parent_id=lens.id, role=EdgeRole.MEMBER_OF)
    )
    edges_before = await store.list_edges(
        lens.id, direction="to", role=EdgeRole.MEMBER_OF
    )

    successor = await svc.edit_criterion(lens.id, "about indoor bouldering only")

    # New row with the new criterion; predecessor superseded, not deleted.
    assert successor.id != lens.id
    assert successor.lens_criterion == "about indoor bouldering only"
    assert successor.lens_name == lens.lens_name
    old = await store.get(lens.id)
    assert old is not None and old.status is Status.SUPERSEDED

    # §6 / §1.1: criterion edit mutates NO membership edge. The stale member edge
    # still points at the OLD lens id and is untouched (re-validate-at-read, not
    # edge removal, resolves it at the next project).
    edges_after = await store.list_edges(
        lens.id, direction="to", role=EdgeRole.MEMBER_OF
    )
    assert [e.child_id for e in edges_after] == [e.child_id for e in edges_before]
    assert c1.id in {e.child_id for e in edges_after}

    # dirty watermark recorded in meta (§6) under the SUCCESSOR id.
    rows = await store.conn.execute_fetchall(
        "SELECT value FROM meta WHERE key = ?",
        (f"{LENS_DIRTY_PREFIX}:{successor.id}",),
    )
    assert rows and rows[0]["value"] == successor.id


@pytest.mark.asyncio
async def test_edit_criterion_rejects_non_lens(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    c = await _claim(store, "not a lens")
    with pytest.raises(ValueError):
        await svc.edit_criterion(c.id, "whatever")


# --- delete: archive the view, claims + edges survive (§1.1, §3.4) --


@pytest.mark.asyncio
async def test_delete_lens_leaves_claims_and_member_edges(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    c1 = await _claim(store, "fact one")
    c2 = await _claim(store, "fact two")
    lens = await svc.create_lens("Topic", "about a topic", USER)
    for c in (c1, c2):
        await store.add_edge(
            MemoryEdge(child_id=c.id, parent_id=lens.id, role=EdgeRole.MEMBER_OF)
        )

    ok = await svc.delete_lens(lens.id)
    assert ok is True

    # View archived...
    archived = await store.get(lens.id)
    assert archived is not None and archived.status is Status.ARCHIVED
    # ...but the claims are untouched and still ACTIVE...
    for c in (c1, c2):
        live = await store.get(c.id)
        assert live is not None and live.status is Status.ACTIVE
    # ...and the member_of edges still dangle (no edge delete path, §1.1).
    edges = await store.list_edges(lens.id, direction="to", role=EdgeRole.MEMBER_OF)
    assert {e.child_id for e in edges} == {c1.id, c2.id}
    # Active-lens reads skip the archived lens.
    active = await store.query(kind=Kind.LENS, scope=USER, status=Status.ACTIVE)
    assert lens.id not in {le.id for le in active}


# --- split: children backfill, parent optionally archived -----------


@pytest.mark.asyncio
async def test_split_lens_creates_children_each_backfilled_and_archives_parent(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    parent = await svc.create_lens("Sport", "about sport", USER)
    mem.backfilled.clear()

    children = await svc.split_lens(
        parent.id,
        [("Climbing", "about climbing"), ("Running", "about running")],
    )

    assert [c.lens_name for c in children] == ["Climbing", "Running"]
    # Each child re-derives its own members via backfill (§3.4).
    assert mem.backfilled == [children[0].id, children[1].id]
    # Parent archived by default; its claims/edges untouched.
    archived = await store.get(parent.id)
    assert archived is not None and archived.status is Status.ARCHIVED
    # children inherit the parent's lens_kind
    assert all(c.lens_kind == "topic" for c in children)


@pytest.mark.asyncio
async def test_split_lens_can_keep_parent(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    parent = await svc.create_lens("Sport", "about sport", USER)
    await svc.split_lens(
        parent.id, [("Climbing", "about climbing")], archive_parent=False
    )
    kept = await store.get(parent.id)
    assert kept is not None and kept.status is Status.ACTIVE


# --- merge: re-derive via backfill, NEVER _inherit_members (§3.5) ---


@pytest.mark.asyncio
async def test_merge_lenses_rederives_union_via_backfill_not_inherit(store, monkeypatch):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    c1 = await _claim(store, "member of a")
    c2 = await _claim(store, "member of b")
    a = await svc.create_lens("A", "crit a", USER)
    b = await svc.create_lens("B", "crit b", USER)
    await store.add_edge(MemoryEdge(child_id=c1.id, parent_id=a.id, role=EdgeRole.MEMBER_OF))
    await store.add_edge(MemoryEdge(child_id=c2.id, parent_id=b.id, role=EdgeRole.MEMBER_OF))
    mem.backfilled.clear()

    # §3.5 guard: _inherit_members must NOT be invoked for a lens merge. Trip it
    # if anyone wires it in.
    import ntrp.memory.pipeline.consolidate as consolidate_mod

    called = {"inherit": False}
    if hasattr(consolidate_mod, "ConsolidateLint") and hasattr(
        consolidate_mod.ConsolidateLint, "_inherit_members"
    ):
        orig = consolidate_mod.ConsolidateLint._inherit_members

        async def _trip(self, *args, **kwargs):
            called["inherit"] = True
            return await orig(self, *args, **kwargs)

        monkeypatch.setattr(consolidate_mod.ConsolidateLint, "_inherit_members", _trip)

    # the union re-derives members from the pool against the merged criterion
    mem.seed_pool("__pending__", [])  # union id unknown until created
    union = await svc.merge_lenses([a.id, b.id], "AB", "crit a or crit b")

    assert union.lens_name == "AB"
    assert union.lens_criterion == "crit a or crit b"
    # union was backfilled (re-derive), the only membership move on merge.
    assert mem.backfilled == [union.id]
    assert called["inherit"] is False
    # inputs archived after the union exists.
    for lid in (a.id, b.id):
        archived = await store.get(lid)
        assert archived is not None and archived.status is Status.ARCHIVED
    # the original member edges still dangle on the archived inputs (§1.1).
    a_edges = await store.list_edges(a.id, direction="to", role=EdgeRole.MEMBER_OF)
    assert {e.child_id for e in a_edges} == {c1.id}


@pytest.mark.asyncio
async def test_merge_requires_two_lenses(store):
    mem = FakeMembership(store)
    svc = _service(store, mem)
    a = await svc.create_lens("A", "crit a", USER)
    with pytest.raises(ValueError):
        await svc.merge_lenses([a.id], "Solo", "crit")
