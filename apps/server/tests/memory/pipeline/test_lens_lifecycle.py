"""Lens lifecycle / CRUD unit tests — the VIEW-layer LensRegistry.

Offline only: in-memory SQLite store, a FakeMembership double that records
coverage / cache-refresh calls. NEVER opens ~/.ntrp/memory.db, never the network,
never a real LLM. The registry makes no membership decision of its own — the
double stands in for the LLM judge — so there is no verdict to fake here.

A lens is a VIEW, not memory. These tests assert the locked model:
  - create -> one `lenses` registry row, ZERO claim writes, ZERO edges, NO backfill
  - edit_criterion -> in-place UPDATE (page nulled) + membership cache invalidated,
    NO supersede chain, NO edge mutation
  - delete -> drop the registry row + cache; claims are untouched
  - split/merge -> pure registry ops (create children/union, delete inputs);
    re-derive via the criterion, never inherit members
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio

from ntrp.memory.lens.registry import LensRegistry
from ntrp.memory.models import (
    LensProvenance,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
)
from ntrp.memory.pipeline.types import BackfillReport, CoverageAdvisory
from ntrp.memory.store import MemoryStore

USER = Scope(kind=ScopeKind.USER)


@pytest_asyncio.fixture
async def store(tmp_path):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await s.init_schema()
    yield s
    await conn.close()


class FakeMembership:
    """The membership judge stand-in for the registry's advisory consults.

    The registry never decides membership; it only asks for `coverage` (a pure
    COUNT advisory) when listing, and `refresh_lens_cache` when a view's members
    must re-derive (split/merge warm the cache). Records every call so tests can
    assert orchestration without an LLM.
    """

    def __init__(self, store: MemoryStore, *, ratio: float = 0.0):
        self.store = store
        self.ratio = ratio
        self.refreshed: list[str] = []
        self.coverage_calls: list[str] = []
        self.synth_calls: list[str] = []

    async def refresh_lens_cache(self, lens_id: str) -> BackfillReport:
        self.refreshed.append(lens_id)
        return BackfillReport(lens_id=lens_id, scanned=0, members_added=0, capped=False)

    async def synthesize_criterion(
        self, name: str, intent: str | None = None
    ) -> tuple[str, str, str]:
        # Stand-in for the LLM criterion author: deterministic, records nothing
        # about membership (this is text authoring only). Returns
        # (criterion, mode, entity_type).
        self.synth_calls.append(name)
        is_people = name.lower() in ("people", "persons", "contacts")
        mode = "grouped_by_subject" if is_people else "flat"
        entity_type = "person" if is_people else "thing"
        return f"this item is about {name}", mode, entity_type

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


def _registry(store, membership):
    return LensRegistry(store, membership, projector=None)


async def _claim(store, content, *, subject="alice"):
    item = MemoryItem(
        id=uuid.uuid4().hex,
        content=content,
        canonical_subject=subject,
        scope=USER,
        provenance=Provenance.RECORDED,
    )
    await store.create_item(item)
    return item


# --- create: one registry row, zero claims ---------------------------


@pytest.mark.asyncio
async def test_create_lens_inserts_registry_row_and_touches_zero_claims(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)

    lens = await reg.create_lens("Climbing", "about rock climbing", USER)

    assert lens.name == "Climbing"
    assert lens.criterion == "about rock climbing"
    assert lens.provenance is LensProvenance.USER_AUTHORED
    assert lens.page is None
    # Create does NO backfill (lazy projection) and writes no claims.
    assert mem.refreshed == []
    assert await store.query(scope=USER) == []

    persisted = await store.get_lens(lens.id)
    assert persisted is not None and persisted.id == lens.id


# --- create without a criterion: synthesize from the name -----------


@pytest.mark.asyncio
async def test_create_lens_without_criterion_synthesizes_from_name(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)

    lens = await reg.create_lens("Regina Volkov", scope=USER)

    assert mem.synth_calls == ["Regina Volkov"]
    assert lens.criterion == "this item is about Regina Volkov"
    # Still a view: no claims written.
    assert await store.query(scope=USER) == []
    persisted = await store.get_lens(lens.id)
    assert persisted is not None and persisted.criterion == lens.criterion


@pytest.mark.asyncio
async def test_create_lens_with_criterion_skips_synthesis(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)

    lens = await reg.create_lens("Bugs", "this item describes a software bug", USER)

    assert mem.synth_calls == []  # explicit criterion -> no synthesis
    assert lens.criterion == "this item describes a software bug"


# --- render mode: presentation dial, no membership impact -----------


@pytest.mark.asyncio
async def test_set_render_mode_flips_layout_without_touching_membership(store):
    from ntrp.memory.models import LensRenderMode

    mem = FakeMembership(store)
    reg = _registry(store, mem)
    c1 = await _claim(store, "alice climbs")
    lens = await reg.create_lens("People", "about people", USER)
    assert lens.render_mode is LensRenderMode.FLAT
    # Seed a cached (flat-format) page — what a prior projection would have stored.
    await store.update_lens(lens.id, page="# People\n## Profile\n- alice climbs.\n")
    assert (await store.get_lens(lens.id)).page is not None

    updated = await reg.set_render_mode(lens.id, LensRenderMode.GROUPED_BY_SUBJECT)

    assert updated.id == lens.id
    assert updated.render_mode is LensRenderMode.GROUPED_BY_SUBJECT
    # The mode-specific page cache MUST be nulled so the next read re-derives in the
    # new (grouped) format — serving the flat-format markdown through the grouped
    # path would misrender it as one bogus "Profile" group.
    assert (await store.get_lens(lens.id)).page is None
    # Membership cache untouched (no refresh), claims untouched.
    assert mem.refreshed == []
    assert (await store.get(c1.id)) is not None


@pytest.mark.asyncio
async def test_set_render_mode_rejects_unknown_lens(store):
    from ntrp.memory.models import LensRenderMode

    mem = FakeMembership(store)
    reg = _registry(store, mem)
    with pytest.raises(ValueError):
        await reg.set_render_mode(uuid.uuid4().hex, LensRenderMode.GROUPED_BY_SUBJECT)


# --- list with advisory ----------------------------------------------


@pytest.mark.asyncio
async def test_list_lenses_carries_coverage_advisory(store):
    mem = FakeMembership(store, ratio=0.3)
    reg = _registry(store, mem)
    a = await reg.create_lens("A", "crit a", USER)
    b = await reg.create_lens("B", "crit b", USER)

    rows = await reg.list_lenses(USER)
    ids = {lens.id for lens, _ in rows}
    assert {a.id, b.id} <= ids
    for lens, advisory in rows:
        assert advisory.lens_id == lens.id
        assert advisory.generic is False  # ratio 0.3 < 0.5
    assert set(mem.coverage_calls) >= {a.id, b.id}


# --- edit_criterion: in-place UPDATE + cache invalidated, no claim impact ---


@pytest.mark.asyncio
async def test_edit_criterion_updates_in_place_and_invalidates_cache(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    c1 = await _claim(store, "alice climbs")
    lens = await reg.create_lens("Climbing", "about climbing", USER)

    updated = await reg.edit_criterion(lens.id, "about indoor bouldering only")

    # In-place edit: same id, new criterion, page nulled (re-derive on next read).
    assert updated.id == lens.id
    assert updated.criterion == "about indoor bouldering only"
    assert updated.name == lens.name
    assert updated.page is None
    # No membership rows survive the criterion change.
    assert await store.get_membership(lens.id) == []
    # Claims are untouched.
    live = await store.get(c1.id)
    assert live is not None


@pytest.mark.asyncio
async def test_edit_criterion_rejects_unknown_lens(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    with pytest.raises(ValueError):
        await reg.edit_criterion(uuid.uuid4().hex, "whatever")


# --- delete: drop the view, claims survive ---------------------------


@pytest.mark.asyncio
async def test_delete_lens_drops_view_and_leaves_claims(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    c1 = await _claim(store, "fact one")
    c2 = await _claim(store, "fact two")
    lens = await reg.create_lens("Topic", "about a topic", USER)

    ok = await reg.delete_lens(lens.id)
    assert ok is True

    # The registry row is gone...
    assert await store.get_lens(lens.id) is None
    # ...but the claims are untouched and still present.
    for c in (c1, c2):
        live = await store.get(c.id)
        assert live is not None
    # ...and the lens no longer lists.
    assert lens.id not in {le.id for le in await store.list_lenses(scope=USER)}


# --- split: children created, parent optionally dropped --------------


@pytest.mark.asyncio
async def test_split_lens_creates_children_and_drops_parent(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    parent = await reg.create_lens("Sport", "about sport", USER)

    children = await reg.split_lens(
        parent.id,
        [("Climbing", "about climbing"), ("Running", "about running")],
    )

    assert [c.name for c in children] == ["Climbing", "Running"]
    # Parent dropped by default.
    assert await store.get_lens(parent.id) is None
    # Children are real registry rows in the same scope.
    for c in children:
        assert (await store.get_lens(c.id)) is not None
        assert c.scope.kind is ScopeKind.USER


@pytest.mark.asyncio
async def test_split_lens_can_keep_parent(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    parent = await reg.create_lens("Sport", "about sport", USER)
    await reg.split_lens(parent.id, [("Climbing", "about climbing")], archive_parent=False)
    kept = await store.get_lens(parent.id)
    assert kept is not None


# --- merge: union created, inputs dropped ----------------------------


@pytest.mark.asyncio
async def test_merge_lenses_creates_union_and_drops_inputs(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    a = await reg.create_lens("A", "crit a", USER)
    b = await reg.create_lens("B", "crit b", USER)

    union = await reg.merge_lenses([a.id, b.id], "AB", "crit a or crit b")

    assert union.name == "AB"
    assert union.criterion == "crit a or crit b"
    # Inputs dropped after the union exists; the union re-derives from its criterion.
    for lid in (a.id, b.id):
        assert await store.get_lens(lid) is None
    assert await store.get_lens(union.id) is not None


@pytest.mark.asyncio
async def test_merge_across_scopes_is_refused(store):
    # A union inherits ONE scope; recall is scope-isolated, so merging a user-scope
    # and a project-scope lens would silently drop the other scope's claims while
    # deleting that source lens. Refuse rather than produce a lossy phantom union.
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    a = await reg.create_lens("A", "crit a", USER)
    proj = Scope(kind=ScopeKind.PROJECT, key="alpha")
    b = await reg.create_lens("B", "crit b", proj)

    with pytest.raises(ValueError, match="across scopes"):
        await reg.merge_lenses([a.id, b.id], "AB", "crit a or crit b")

    # Both inputs survive — nothing was deleted on the rejected merge.
    assert await store.get_lens(a.id) is not None
    assert await store.get_lens(b.id) is not None


@pytest.mark.asyncio
async def test_merge_requires_two_lenses(store):
    mem = FakeMembership(store)
    reg = _registry(store, mem)
    a = await reg.create_lens("A", "crit a", USER)
    with pytest.raises(ValueError):
        await reg.merge_lenses([a.id], "Solo", "crit")
