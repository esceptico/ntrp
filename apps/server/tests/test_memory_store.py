import uuid
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory import (
    EdgeRole,
    Feedback,
    LensDetailLevel,
    LensProvenance,
    LensRow,
    LensStatus,
    MembershipDecision,
    MembershipVerdict,
    MemoryEdge,
    MemoryItem,
    MemoryStore,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
    Status,
)


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    conn = await database.connect(tmp_path / "memory.db")
    store = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await store.init_schema()
    yield store
    await conn.close()


def _claim(content: str, scope: Scope, **kw) -> MemoryItem:
    return MemoryItem(
        id=str(uuid.uuid4()),
        content=content,
        canonical_subject=kw.pop("canonical_subject", "Tim"),
        scope=scope,
        provenance=kw.pop("provenance", Provenance.RECORDED),
        valid_from=kw.pop("valid_from", "2026-01-01T00:00:00+00:00"),
        source_refs=kw.pop("source_refs", [SourceRef(kind="chat_turn", ref="turn-1")]),
        **kw,
    )


def _lens(scope: Scope, **kw) -> LensRow:
    name = kw.pop("name", "Bugs")
    return LensRow(
        id=kw.pop("id", _slug(name)),
        name=name,
        criterion=kw.pop("criterion", "this item describes a software bug"),
        scope=scope,
        **kw,
    )


def _slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "lens"


@pytest.mark.asyncio
async def test_schema_creates_and_init_is_idempotent(tmp_path: Path):
    conn = await database.connect(tmp_path / "m.db")
    store = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await store.init_schema()
    await store.init_schema()  # idempotent
    names = {
        r["name"]
        for r in await conn.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "memory_items" in names
    # Lens definitions are files on disk, not a DB table.
    assert "lenses" not in names
    assert "lens_page_cache" in names
    assert "lens_membership_cache" in names
    # memory_items is claims-only: no kind / lens_* columns
    cols = {
        r["name"]
        for r in await conn.execute_fetchall("PRAGMA table_info(memory_items)")
    }
    assert "canonical_subject" in cols
    assert "kind" not in cols
    assert not any(c.startswith("lens_") for c in cols)
    await conn.close()


@pytest.mark.asyncio
async def test_claim_round_trips(store: MemoryStore):
    item = _claim("Tim prefers raw SQL", Scope(ScopeKind.USER), canonical_subject="Tim")
    await store.create_item(item)
    got = await store.get(item.id)
    assert got is not None
    assert got.content == "Tim prefers raw SQL"
    assert got.canonical_subject == "Tim"
    assert got.scope.kind is ScopeKind.USER
    assert got.scope.key is None
    assert got.provenance is Provenance.RECORDED
    assert got.status is Status.ACTIVE
    assert got.source_refs[0].kind == "chat_turn"
    assert got.source_refs[0].ref == "turn-1"


@pytest.mark.asyncio
async def test_invalidate_sets_status_and_invalid_at_never_deletes(store: MemoryStore):
    item = _claim("transient fact", Scope(ScopeKind.SESSION, "sess-1"))
    await store.create_item(item)

    assert await store.invalidate(item.id) is True
    got = await store.get(item.id)
    assert got is not None  # row still present
    assert got.status is Status.ARCHIVED
    assert got.invalid_at is not None

    # second invalidate is a no-op (already off active)
    assert await store.invalidate(item.id) is False


@pytest.mark.asyncio
async def test_supersede_closes_predecessor_and_links_edge(store: MemoryStore):
    old = _claim("Tim uses Postgres", Scope(ScopeKind.USER))
    await store.create_item(old)
    new = _claim("Tim uses SQLite", Scope(ScopeKind.USER))

    await store.supersede(old_id=old.id, new_item=new)

    old_got = await store.get(old.id)
    assert old_got is not None  # never deleted
    assert old_got.status is Status.SUPERSEDED
    assert old_got.invalid_at is not None

    new_got = await store.get(new.id)
    assert new_got.status is Status.ACTIVE

    edges = await store.list_edges(new.id, direction="from", role=EdgeRole.SUPERSEDES)
    assert len(edges) == 1
    assert edges[0].parent_id == old.id


@pytest.mark.asyncio
async def test_claim_to_claim_edges(store: MemoryStore):
    a = _claim("Tim shipped a fix", Scope(ScopeKind.USER))
    b = _claim("The bug is resolved", Scope(ScopeKind.USER))
    await store.create_item(a)
    await store.create_item(b)

    assert await store.add_edge(
        MemoryEdge(child_id=b.id, parent_id=a.id, role=EdgeRole.EVIDENCE)
    ) is True
    # duplicate ignored
    assert await store.add_edge(
        MemoryEdge(child_id=b.id, parent_id=a.id, role=EdgeRole.EVIDENCE)
    ) is False

    deps = await store.list_edges(a.id, direction="to", role=EdgeRole.EVIDENCE)
    assert len(deps) == 1
    assert deps[0].child_id == b.id


@pytest.mark.asyncio
async def test_scope_filtering(store: MemoryStore):
    await store.create_item(_claim("user fact", Scope(ScopeKind.USER)))
    await store.create_item(_claim("proj fact", Scope(ScopeKind.PROJECT, "p1")))
    await store.create_item(_claim("other proj", Scope(ScopeKind.PROJECT, "p2")))

    user = await store.query(scope=Scope(ScopeKind.USER))
    assert {i.content for i in user} == {"user fact"}

    p1 = await store.query(scope=Scope(ScopeKind.PROJECT, "p1"))
    assert {i.content for i in p1} == {"proj fact"}


@pytest.mark.asyncio
async def test_subject_filtering(store: MemoryStore):
    await store.create_item(
        _claim("Tim prefers raw SQL", Scope(ScopeKind.USER), canonical_subject="Tim")
    )
    await store.create_item(
        _claim("Tim takes venlafaxine", Scope(ScopeKind.USER), canonical_subject="Tim")
    )
    await store.create_item(
        _claim("Regina is CEO", Scope(ScopeKind.USER), canonical_subject="Regina")
    )

    tim = await store.query(scope=Scope(ScopeKind.USER), subject="Tim")
    assert {i.content for i in tim} == {"Tim prefers raw SQL", "Tim takes venlafaxine"}

    regina = await store.query(scope=Scope(ScopeKind.USER), subject="Regina")
    assert {i.content for i in regina} == {"Regina is CEO"}


@pytest.mark.asyncio
async def test_validity_window_filtering(store: MemoryStore):
    live = _claim("live", Scope(ScopeKind.USER), valid_from="2026-01-01T00:00:00+00:00")
    expired = _claim(
        "expired",
        Scope(ScopeKind.USER),
        valid_from="2025-01-01T00:00:00+00:00",
        invalid_at="2025-06-01T00:00:00+00:00",
    )
    await store.create_item(live)
    await store.create_item(expired)

    at = "2026-03-01T00:00:00+00:00"
    valid = await store.query(scope=Scope(ScopeKind.USER), status=None, valid_at=at)
    assert {i.content for i in valid} == {"live"}


@pytest.mark.asyncio
async def test_status_filtering_default_active_only(store: MemoryStore):
    a = _claim("a", Scope(ScopeKind.USER))
    b = _claim("b", Scope(ScopeKind.USER))
    await store.create_item(a)
    await store.create_item(b)
    await store.invalidate(b.id)

    active = await store.query(scope=Scope(ScopeKind.USER))
    assert {i.content for i in active} == {"a"}

    all_items = await store.query(scope=Scope(ScopeKind.USER), status=None)
    assert {i.content for i in all_items} == {"a", "b"}


@pytest.mark.asyncio
async def test_fts_search(store: MemoryStore):
    await store.create_item(_claim("Tim prefers raw SQL over ORMs", Scope(ScopeKind.USER)))
    await store.create_item(_claim("The sky is blue", Scope(ScopeKind.USER)))
    hits = await store.search("SQL")
    assert any("SQL" in i.content for i in hits)


@pytest.mark.asyncio
async def test_fts_search_by_subject(store: MemoryStore):
    await store.create_item(
        _claim("prefers raw SQL", Scope(ScopeKind.USER), canonical_subject="Regina Volkov")
    )
    hits = await store.search("Regina")
    assert any(i.canonical_subject == "Regina Volkov" for i in hits)


@pytest.mark.asyncio
async def test_search_excludes_invalidated_by_default(store: MemoryStore):
    live = _claim("Tim prefers raw SQL over ORMs", Scope(ScopeKind.USER))
    stale = _claim("Tim prefers SQL stored procedures", Scope(ScopeKind.USER))
    await store.create_item(live)
    await store.create_item(stale)
    await store.invalidate(stale.id)  # archived

    hits = await store.search("SQL")
    contents = {i.content for i in hits}
    assert live.content in contents
    assert stale.content not in contents

    all_hits = await store.search("SQL", include_inactive=True)
    assert stale.content in {i.content for i in all_hits}


@pytest.mark.asyncio
async def test_search_subjects_ranks_by_subject_name(store: MemoryStore):
    # A name/alias recall channel: matches the canonical_subject column, not the body.
    target = _claim("did unrelated work today", Scope(ScopeKind.USER), canonical_subject="Timur Ganiev")
    noise = _claim("Timur Ganiev was mentioned in passing", Scope(ScopeKind.USER), canonical_subject="Regina")
    await store.create_item(target)
    await store.create_item(noise)

    hits = await store.search_subjects("Timur Ganiev")
    subjects = {h.canonical_subject for h in hits}
    assert "Timur Ganiev" in subjects
    # The body-only mention under a different subject is not a subject-name match.
    assert "Regina" not in subjects


@pytest.mark.asyncio
async def test_feedback_and_corroboration(store: MemoryStore):
    item = _claim("x", Scope(ScopeKind.USER))
    await store.create_item(item)
    assert await store.set_feedback(item.id, Feedback.CONFIRMED) is True
    assert await store.bump_corroboration(item.id) is True
    got = await store.get(item.id)
    assert got.feedback is Feedback.CONFIRMED
    assert got.corroboration == 1


# --- lens registry (views; never memory) ---


@pytest.mark.asyncio
async def test_lens_round_trips_in_registry(store: MemoryStore):
    lens = _lens(
        Scope(ScopeKind.USER),
        name="Regina Volkov",
        criterion="this item is about Regina Volkov",
        detail_level=LensDetailLevel.DOSSIER,
        provenance=LensProvenance.INDUCED,
        entity_type="person",
    )
    await store.create_lens_row(lens)
    # The page is a derived cache (kept in the DB keyed by slug), not part of the
    # definition file — set it via update_lens.
    await store.update_lens(lens.id, page="# Regina\n...")
    got = await store.get_lens(lens.id)
    assert got is not None
    assert got.name == "Regina Volkov"
    assert got.entity_type == "person"
    assert got.detail_level is LensDetailLevel.DOSSIER
    assert got.provenance is LensProvenance.INDUCED
    assert got.status is LensStatus.ACTIVE
    assert got.page == "# Regina\n..."


@pytest.mark.asyncio
async def test_create_lens_touches_zero_claims_and_edges(store: MemoryStore):
    await store.create_item(_claim("Tim prefers raw SQL", Scope(ScopeKind.USER)))
    before_items = await store.query(scope=Scope(ScopeKind.USER), status=None)
    before_edges = await store.conn.execute_fetchall(
        "SELECT COUNT(*) AS n FROM memory_item_parents"
    )

    await store.create_lens_row(_lens(Scope(ScopeKind.USER)))

    after_items = await store.query(scope=Scope(ScopeKind.USER), status=None)
    after_edges = await store.conn.execute_fetchall(
        "SELECT COUNT(*) AS n FROM memory_item_parents"
    )
    assert len(after_items) == len(before_items)
    assert after_edges[0]["n"] == before_edges[0]["n"] == 0


@pytest.mark.asyncio
async def test_update_lens_in_place_nulls_page(store: MemoryStore):
    lens = _lens(Scope(ScopeKind.USER))
    await store.create_lens_row(lens)
    await store.update_lens(lens.id, page="# stale")
    updated = await store.update_lens(
        lens.id, criterion="bugs in the ntrp repo only", page=None
    )
    assert updated.criterion == "bugs in the ntrp repo only"
    assert updated.page is None


@pytest.mark.asyncio
async def test_list_and_delete_lens_leaves_claims_untouched(store: MemoryStore):
    claim = _claim("Tim prefers raw SQL", Scope(ScopeKind.USER))
    await store.create_item(claim)
    lens = _lens(Scope(ScopeKind.USER))
    await store.create_lens_row(lens)

    assert {ln.id for ln in await store.list_lenses(scope=Scope(ScopeKind.USER))} == {lens.id}

    assert await store.delete_lens(lens.id) is True
    assert await store.get_lens(lens.id) is None
    # claim survives
    assert await store.get(claim.id) is not None


@pytest.mark.asyncio
async def test_search_lenses(store: MemoryStore):
    await store.create_lens_row(
        _lens(Scope(ScopeKind.USER), name="Bugs", criterion="software bugs")
    )
    await store.create_lens_row(
        _lens(Scope(ScopeKind.USER), name="People", criterion="a person")
    )
    hits = await store.search_lenses("Bugs")
    assert any(ln.name == "Bugs" for ln in hits)


@pytest.mark.asyncio
async def test_membership_cache_is_a_cache(store: MemoryStore):
    claim = _claim("Tim prefers raw SQL", Scope(ScopeKind.USER))
    await store.create_item(claim)
    lens = _lens(Scope(ScopeKind.USER))
    await store.create_lens_row(lens)

    await store.put_membership(
        [
            MembershipVerdict(lens.id, claim.id, MembershipDecision.IN, rationale="matches"),
        ]
    )
    members = await store.get_membership(lens.id, decision=MembershipDecision.IN)
    assert [v.claim_id for v in members] == [claim.id]

    # cache is not an edge — no member_of rows anywhere
    edges = await store.conn.execute_fetchall("SELECT COUNT(*) AS n FROM memory_item_parents")
    assert edges[0]["n"] == 0

    # invalidation drops verdicts; claim is untouched
    await store.invalidate_lens_membership(lens.id)
    assert await store.get_membership(lens.id) == []
    assert await store.get(claim.id) is not None
