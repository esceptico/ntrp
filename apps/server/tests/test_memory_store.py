import uuid
from pathlib import Path

import pytest
import pytest_asyncio

import ntrp.database as database
from ntrp.memory import (
    EdgeRole,
    Feedback,
    Kind,
    LensDetailLevel,
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
    store = MemoryStore(conn)
    await store.init_schema()
    yield store
    await conn.close()


def _claim(content: str, scope: Scope, **kw) -> MemoryItem:
    return MemoryItem(
        id=str(uuid.uuid4()),
        kind=Kind.CLAIM,
        content=content,
        scope=scope,
        provenance=kw.pop("provenance", Provenance.RECORDED),
        valid_from=kw.pop("valid_from", "2026-01-01T00:00:00+00:00"),
        source_refs=kw.pop(
            "source_refs", [SourceRef(kind="chat_turn", ref="turn-1")]
        ),
        **kw,
    )


@pytest.mark.asyncio
async def test_schema_creates_and_init_is_idempotent(tmp_path: Path):
    conn = await database.connect(tmp_path / "m.db")
    store = MemoryStore(conn)
    await store.init_schema()
    await store.init_schema()  # idempotent
    rows = await conn.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_items'"
    )
    assert rows
    await conn.close()


@pytest.mark.asyncio
async def test_claim_round_trips(store: MemoryStore):
    item = _claim("Tim prefers raw SQL", Scope(ScopeKind.USER))
    await store.create_item(item)
    got = await store.get(item.id)
    assert got is not None
    assert got.content == "Tim prefers raw SQL"
    assert got.scope.kind is ScopeKind.USER
    assert got.scope.key is None
    assert got.provenance is Provenance.RECORDED
    assert got.status is Status.ACTIVE
    assert got.source_refs[0].kind == "chat_turn"
    assert got.source_refs[0].ref == "turn-1"


@pytest.mark.asyncio
async def test_lens_round_trips(store: MemoryStore):
    lens = MemoryItem(
        id=str(uuid.uuid4()),
        kind=Kind.LENS,
        content="Things about Tim",
        scope=Scope(ScopeKind.USER),
        provenance=Provenance.INDUCED,
        lens_name="Tim",
        lens_criterion="claims whose subject is the person Tim",
        lens_kind="entity",
        lens_page="# Tim\n...",
        lens_detail_level=LensDetailLevel.DOSSIER,
        lens_exclusive=True,
    )
    await store.create_item(lens)
    got = await store.get(lens.id)
    assert got.kind is Kind.LENS
    assert got.lens_name == "Tim"
    assert got.lens_detail_level is LensDetailLevel.DOSSIER
    assert got.lens_exclusive is True
    assert got.source_refs == []


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
async def test_role_typed_edges(store: MemoryStore):
    claim = _claim("Tim prefers raw SQL", Scope(ScopeKind.USER))
    lens = MemoryItem(
        id=str(uuid.uuid4()),
        kind=Kind.LENS,
        content="Tim",
        scope=Scope(ScopeKind.USER),
        provenance=Provenance.INDUCED,
        lens_name="Tim",
        lens_criterion="about Tim",
    )
    await store.create_item(claim)
    await store.create_item(lens)

    assert await store.add_edge(
        MemoryEdge(child_id=claim.id, parent_id=lens.id, role=EdgeRole.MEMBER_OF)
    ) is True
    # duplicate ignored
    assert await store.add_edge(
        MemoryEdge(child_id=claim.id, parent_id=lens.id, role=EdgeRole.MEMBER_OF)
    ) is False

    members = await store.list_edges(lens.id, direction="to", role=EdgeRole.MEMBER_OF)
    assert len(members) == 1
    assert members[0].child_id == claim.id


@pytest.mark.asyncio
async def test_scope_filtering(store: MemoryStore):
    await store.create_item(_claim("user fact", Scope(ScopeKind.USER)))
    await store.create_item(_claim("proj fact", Scope(ScopeKind.PROJECT, "p1")))
    await store.create_item(_claim("other proj", Scope(ScopeKind.PROJECT, "p2")))

    user = await store.query(scope=Scope(ScopeKind.USER), kind=Kind.CLAIM)
    assert {i.content for i in user} == {"user fact"}

    p1 = await store.query(scope=Scope(ScopeKind.PROJECT, "p1"), kind=Kind.CLAIM)
    assert {i.content for i in p1} == {"proj fact"}


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
async def test_search_excludes_invalidated_by_default(store: MemoryStore):
    live = _claim("Tim prefers raw SQL over ORMs", Scope(ScopeKind.USER))
    stale = _claim("Tim prefers SQL stored procedures", Scope(ScopeKind.USER))
    await store.create_item(live)
    await store.create_item(stale)
    await store.invalidate(stale.id)  # archived

    # default: invalidated rows must not surface as live
    hits = await store.search("SQL")
    contents = {i.content for i in hits}
    assert live.content in contents
    assert stale.content not in contents

    # forensic mode can still reach them
    all_hits = await store.search("SQL", include_inactive=True)
    assert stale.content in {i.content for i in all_hits}


@pytest.mark.asyncio
async def test_feedback_and_corroboration(store: MemoryStore):
    item = _claim("x", Scope(ScopeKind.USER))
    await store.create_item(item)
    assert await store.set_feedback(item.id, Feedback.CONFIRMED) is True
    assert await store.bump_corroboration(item.id) is True
    got = await store.get(item.id)
    assert got.feedback is Feedback.CONFIRMED
    assert got.corroboration == 1
