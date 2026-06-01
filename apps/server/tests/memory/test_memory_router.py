"""Focused router tests for the Stage-5 memory UI endpoints.

Offline only. The store-backed routes (#1, #2, #5, #6 fts) run against a real
MemoryStore over a tmp_path SQLite DB. The lens/page/writeback/retrieve routes
(#3, #4, #6 retrieve, #7, #8) run against a hand-built fake `memory_retrieval`
that records calls and returns scripted pipeline dataclasses — no LLM, no
embedder, never ~/.ntrp/memory.db.

Memory is claims-only; lenses are a separate registry of VIEWS (never graph
nodes). The router is exercised end-to-end through FastAPI's TestClient with
`require_knowledge_runtime` overridden to a fake KnowledgeRuntime, so this
asserts the real serialization, validation, and 404 mapping the contract pins.
"""

import uuid

import aiosqlite
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ntrp.memory.models import (
    EdgeRole,
    Feedback,
    LensDetailLevel,
    LensProvenance,
    LensRenderMode,
    LensRow,
    LensStatus,
    MemoryEdge,
    MemoryItem,
    Provenance,
    Scope,
    ScopeKind,
    SourceRef,
    Status,
)
from ntrp.memory.pipeline.lens_generation import LensPageGenerator
from ntrp.memory.pipeline.types import (
    CoverageAdvisory,
    PageEditKind,
    ProjectedPage,
    RankedItem,
    RenderedClaim,
    RetrievedContext,
    WriteBackResult,
)
from ntrp.memory.store import MemoryStore
from ntrp.server.app import app
from ntrp.server.deps import require_knowledge_runtime

USER = Scope(kind=ScopeKind.USER)


# --- fakes -----------------------------------------------------------


class _FakeLensRegistry:
    """Stands in for LensRegistry (the view layer). Backed by the real store's
    `lenses` registry so lifecycle persistence is exercised end-to-end."""

    def __init__(self, store):
        self.store = store
        self.calls: list[tuple] = []

    async def list_lenses(self, scope):
        self.calls.append(("list_lenses", scope))
        lenses = await self.store.list_lenses(scope=scope)
        return [
            (
                lens,
                CoverageAdvisory(
                    lens_id=lens.id,
                    scope_pool=10,
                    member_count=3,
                    ratio=0.3,
                    generic=False,
                    suggestion="narrow",
                ),
            )
            for lens in lenses
        ]

    async def create_lens(self, name, criterion, scope, *, render_mode=None):
        self.calls.append(("create_lens", name, criterion, scope, render_mode))
        lens = LensRow(
            id=_lens_slug(),
            name=name,
            criterion=criterion,
            scope=scope,
            provenance=LensProvenance.USER_AUTHORED,
        )
        await self.store.create_lens_row(lens)
        return lens

    async def edit_criterion(self, lens_id, new_criterion):
        self.calls.append(("edit_criterion", lens_id, new_criterion))
        lens = await self.store.get_lens(lens_id)
        if lens is None:
            raise ValueError(f"not a lens: {lens_id}")
        await self.store.invalidate_lens_membership(lens_id)
        updated = await self.store.update_lens(lens_id, criterion=new_criterion, page=None)
        return updated

    async def split_lens(self, lens_id, into, *, archive_parent=True):
        self.calls.append(("split_lens", lens_id, into, archive_parent))
        parent = await self.store.get_lens(lens_id)
        if parent is None:
            raise ValueError(f"not a lens: {lens_id}")
        children = []
        for name, criterion in into:
            children.append(await self.create_lens(name, criterion, parent.scope))
        if archive_parent:
            await self.store.delete_lens(parent.id)
        return children

    async def merge_lenses(self, lens_ids, name, criterion):
        self.calls.append(("merge_lenses", lens_ids, name, criterion))
        inputs = []
        for lid in lens_ids:
            lens = await self.store.get_lens(lid)
            if lens is None:
                raise ValueError(f"not a lens: {lid}")
            inputs.append(lens)
        union = await self.create_lens(name, criterion, inputs[0].scope)
        for lens in inputs:
            await self.store.delete_lens(lens.id)
        return union

    async def delete_lens(self, lens_id):
        self.calls.append(("delete_lens", lens_id))
        return await self.store.delete_lens(lens_id)


class _FakeProjector:
    """A projector whose page is whatever `self.page` is set to. `cached_page`
    serves it synchronously (the cache-hit fast path); `project` also serves it and
    records the call (the background-generation path drives this one)."""

    def __init__(self, page: ProjectedPage | None = None):
        self.page = page
        self.calls: list[tuple] = []

    def _page(self, lens_id, detail) -> ProjectedPage:
        if self.page is not None:
            return self.page
        return ProjectedPage(
            lens_id=lens_id,
            detail=detail or LensDetailLevel.STRUCTURED,
            markdown="",
            blocks=[],
            synthesized=False,
            coverage=None,
        )

    async def cached_page(self, lens_id, *, detail=None):
        return self._page(lens_id, detail) if self.page is not None else None

    async def project(self, lens_id, *, detail=None, refresh=False, progress=None):
        self.calls.append((lens_id, detail, refresh))
        return self._page(lens_id, detail)


class _FakeWriteBack:
    def __init__(self, result: WriteBackResult):
        self.result = result
        self.calls: list[tuple] = []

    async def apply(self, lens_id, ops):
        self.calls.append((lens_id, ops))
        return self.result


class _FakePipeline:
    def __init__(self, store, *, ctx: RetrievedContext | None = None):
        self.store = store
        self.lens_registry = _FakeLensRegistry(store)
        self.lens_projector = _FakeProjector()
        self.lens_generator = LensPageGenerator(self.lens_projector)
        self.lens_writeback = _FakeWriteBack(
            WriteBackResult(applied=[], rejected=[], rederive_triggered=False)
        )
        self.ctx = ctx
        self.retrieve_calls: list = []

    async def retrieve(self, req):
        self.retrieve_calls.append(req)
        if self.ctx is not None:
            return self.ctx
        return RetrievedContext(rendered="", items=[], degraded=False, diagnostics={})


class _FakeKnowledge:
    def __init__(self, store, pipeline, *, ready=True):
        self.memory = store
        self.memory_retrieval = pipeline
        self._ready = ready

    @property
    def memory_ready(self):
        return self._ready


# --- fixtures --------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path):
    conn = await aiosqlite.connect(str(tmp_path / "mem.db"))
    conn.row_factory = aiosqlite.Row
    s = MemoryStore(conn, lenses_dir=tmp_path / "lenses")
    await s.init_schema()
    yield s
    await conn.close()


_slug_n = 0


def _lens_slug() -> str:
    global _slug_n
    _slug_n += 1
    return f"lens-{_slug_n}"


@pytest.fixture
def pipeline(store):
    return _FakePipeline(store)


@pytest.fixture
def client(store, pipeline):
    knowledge = _FakeKnowledge(store, pipeline)
    app.dependency_overrides[require_knowledge_runtime] = lambda: knowledge
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_knowledge_runtime, None)


async def _claim(store, content, **kw):
    item = MemoryItem(
        id=uuid.uuid4().hex,
        content=content,
        canonical_subject=kw.pop("canonical_subject", "Tim"),
        scope=USER,
        provenance=kw.pop("provenance", Provenance.RECORDED),
        **kw,
    )
    await store.create_item(item)
    return item


async def _lens(store, name, criterion):
    lens = LensRow(
        id=_lens_slug(),
        name=name,
        criterion=criterion,
        scope=USER,
        provenance=LensProvenance.USER_AUTHORED,
    )
    await store.create_lens_row(lens)
    return lens


# --- guard / mount ---------------------------------------------------


def test_routes_registered():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    for p in (
        "/admin/memory/items",
        "/admin/memory/items/{item_id}",
        "/admin/memory/items/{item_id}/graph",
        "/admin/memory/lenses",
        "/admin/memory/lenses/{lens_id}/page",
        "/admin/memory/lenses/{lens_id}/writeback",
        "/admin/memory/lenses/merge",
        "/admin/memory/lenses/{lens_id}/criterion",
        "/admin/memory/lenses/{lens_id}/split",
        "/admin/memory/lenses/{lens_id}",
        "/admin/memory/search",
    ):
        assert p in paths


def test_not_ready_returns_503(store, pipeline):
    knowledge = _FakeKnowledge(store, pipeline, ready=False)
    app.dependency_overrides[require_knowledge_runtime] = lambda: knowledge
    try:
        resp = TestClient(app).get("/admin/memory/items")
    finally:
        app.dependency_overrides.pop(require_knowledge_runtime, None)
    assert resp.status_code == 503


# --- 1: list items ---------------------------------------------------


@pytest.mark.asyncio
async def test_list_items_serializes_claims(store, client):
    await _claim(store, "alice climbs", feedback=Feedback.CONFIRMED, corroboration=2)
    resp = client.get("/admin/memory/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 100
    assert len(body["items"]) == 1
    m = body["items"][0]
    assert m["content"] == "alice climbs"
    assert m["canonical_subject"] == "Tim"
    assert m["scope"] == {"kind": "user", "key": None}
    assert m["feedback"] == "confirmed"
    assert m["corroboration"] == 2
    # No confidence/title/tags/kind in the new claims-only model.
    assert "confidence" not in m and "title" not in m and "tags" not in m
    assert "kind" not in m


@pytest.mark.asyncio
async def test_list_items_empty_status_returns_all(store, client):
    c = await _claim(store, "live")
    await store.invalidate(c.id, status=Status.ARCHIVED)
    # default status=active -> excluded
    assert client.get("/admin/memory/items").json()["items"] == []
    # empty status -> all
    body = client.get("/admin/memory/items", params={"status": ""}).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "archived"


def test_list_items_project_scope_missing_key_422(client):
    # Scope(project) without a key -> Scope raises -> 422.
    assert client.get(
        "/admin/memory/items", params={"scope_kind": "project"}
    ).status_code == 422


# --- 2: get item + edges ---------------------------------------------


@pytest.mark.asyncio
async def test_get_item_with_parent_and_child_edges(store, client):
    parent = await _claim(store, "evidence claim")
    child = await _claim(store, "derived claim")
    await store.add_edge(
        MemoryEdge(child_id=child.id, parent_id=parent.id, role=EdgeRole.EVIDENCE)
    )
    resp = client.get(f"/admin/memory/items/{child.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"]["id"] == child.id
    # direction=from: child -> parent
    assert body["parents"] == [
        {
            "child_id": child.id,
            "parent_id": parent.id,
            "role": "evidence",
            "position": 0,
            "created_at": body["parents"][0]["created_at"],
        }
    ]
    assert body["children"] == []
    # the parent sees the child as a dependent (direction=to)
    pbody = client.get(f"/admin/memory/items/{parent.id}").json()
    assert pbody["children"][0]["child_id"] == child.id


def test_get_item_404(client):
    assert client.get("/admin/memory/items/nope").status_code == 404


# --- 3: list lenses --------------------------------------------------


@pytest.mark.asyncio
async def test_list_lenses_with_coverage(store, client, pipeline):
    lens = await _lens(store, "Climbing", "about climbing")
    resp = client.get("/admin/memory/lenses")
    assert resp.status_code == 200
    rows = resp.json()["lenses"]
    assert len(rows) == 1
    assert rows[0]["lens"]["id"] == lens.id
    assert rows[0]["lens"]["name"] == "Climbing"
    assert rows[0]["coverage"]["lens_id"] == lens.id
    assert rows[0]["coverage"]["ratio"] == 0.3
    assert rows[0]["coverage"]["generic"] is False


# --- 4: lens page ----------------------------------------------------


@pytest.mark.asyncio
async def test_lens_page_serializes_blocks(store, client, pipeline):
    lens = await _lens(store, "Topic", "about topic")
    block = RenderedClaim(
        claim_id="c1",
        content="a claim",
        provenance=Provenance.RECORDED,
        corroboration=1,
        feedback=Feedback.NONE,
        source_refs=[SourceRef(kind="chat_turn", ref="t1")],
    )
    pipeline.lens_projector.page = ProjectedPage(
        lens_id=lens.id,
        detail=LensDetailLevel.STRUCTURED,
        markdown="# Topic\n- a claim <!--claim:c1-->",
        blocks=[block],
        synthesized=True,
        coverage=CoverageAdvisory(lens.id, 5, 1, 0.2, False, "narrow"),
    )
    resp = client.get(f"/admin/memory/lenses/{lens.id}/page")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lens_id"] == lens.id
    assert body["detail"] == "structured"
    assert body["synthesized"] is True
    assert body["blocks"][0]["claim_id"] == "c1"
    assert body["blocks"][0]["source_refs"][0]["kind"] == "chat_turn"
    assert body["coverage"]["ratio"] == 0.2


@pytest.mark.asyncio
async def test_lens_page_passes_detail_and_refresh(store, client, pipeline):
    lens = await _lens(store, "T", "c")
    # No cached page -> 202 + background generation; the GET does not block on it.
    resp = client.get(
        f"/admin/memory/lenses/{lens.id}/page", params={"detail": "gist", "refresh": "true"}
    )
    assert resp.status_code == 202
    assert resp.json()["status"] in ("creating", "scoring", "synthesizing", "ready")
    # Generation runs in the background; drain it, then assert it drove the projector
    # with the requested detail + refresh.
    await pipeline.lens_generator.drain()
    assert pipeline.lens_projector.calls[-1] == (lens.id, LensDetailLevel.GIST, True)


def test_lens_page_invalid_detail_422(client):
    assert client.get(
        "/admin/memory/lenses/x/page", params={"detail": "huge"}
    ).status_code == 422


def test_lens_page_empty_and_missing_is_404(client):
    # projector default returns empty page; store has no such id -> 404.
    assert client.get("/admin/memory/lenses/ghost/page").status_code == 404


@pytest.mark.asyncio
async def test_lens_page_active_lens_zero_members_not_404(store, client, pipeline):
    lens = await _lens(store, "Empty", "about nothing")
    pipeline.lens_projector.page = ProjectedPage(
        lens_id=lens.id,
        detail=LensDetailLevel.STRUCTURED,
        markdown="# Empty\n## Profile\n_No members yet._",
        blocks=[],
        synthesized=True,
        coverage=None,
    )
    resp = client.get(f"/admin/memory/lenses/{lens.id}/page")
    assert resp.status_code == 200
    assert resp.json()["blocks"] == []


# --- 5: graph BFS ----------------------------------------------------


@pytest.mark.asyncio
async def test_graph_both_directions(store, client):
    a = await _claim(store, "a")
    b = await _claim(store, "b")
    c = await _claim(store, "c")
    # b --evidence--> a ; c --supersedes--> b
    await store.add_edge(MemoryEdge(child_id=b.id, parent_id=a.id, role=EdgeRole.EVIDENCE))
    await store.add_edge(MemoryEdge(child_id=c.id, parent_id=b.id, role=EdgeRole.SUPERSEDES))
    resp = client.get(f"/admin/memory/items/{b.id}/graph")
    assert resp.status_code == 200
    body = resp.json()
    ids = {n["id"] for n in body["nodes"]}
    assert ids == {a.id, b.id, c.id}
    assert body["direction"] == "both"
    assert len(body["edges"]) == 2


@pytest.mark.asyncio
async def test_graph_role_filter_and_depth_clamp(store, client):
    a = await _claim(store, "a")
    b = await _claim(store, "b")
    await store.add_edge(MemoryEdge(child_id=b.id, parent_id=a.id, role=EdgeRole.EVIDENCE))
    await store.add_edge(MemoryEdge(child_id=b.id, parent_id=a.id, role=EdgeRole.CONTRADICTS))
    body = client.get(
        f"/admin/memory/items/{b.id}/graph",
        params={"direction": "parents", "roles": "evidence", "depth": 99},
    ).json()
    assert body["depth"] == 5  # clamped to _MAX_GRAPH_DEPTH
    assert [e["role"] for e in body["edges"]] == ["evidence"]


def test_graph_404_and_bad_direction(client):
    assert client.get("/admin/memory/items/x/graph").status_code == 404


@pytest.mark.asyncio
async def test_graph_bad_direction_422(store, client):
    a = await _claim(store, "a")
    assert client.get(
        f"/admin/memory/items/{a.id}/graph", params={"direction": "sideways"}
    ).status_code == 422


# --- 6: search -------------------------------------------------------


@pytest.mark.asyncio
async def test_search_fts(store, client):
    await _claim(store, "kubernetes operator pattern")
    await _claim(store, "completely unrelated")
    body = client.get("/admin/memory/search", params={"q": "kubernetes"}).json()
    assert body["mode"] == "fts"
    assert body["degraded"] is False
    assert any("kubernetes" in m["content"] for m in body["items"])


@pytest.mark.asyncio
async def test_search_retrieve_mode(store, client, pipeline):
    claim = await _claim(store, "ranked claim")
    pipeline.ctx = RetrievedContext(
        rendered="- ranked claim",
        items=[
            RankedItem(
                item=claim,
                fts_rank=1.0,
                vector_rank=0.5,
                rrf=0.8,
                freshness=0.9,
                provenance_ord=1,
                corroboration=0,
                order_score=1.23,
            )
        ],
        degraded=False,
        diagnostics={"fts_hits": 1, "vector_hits": 1, "ranked": 1},
    )
    body = client.get(
        "/admin/memory/search", params={"q": "ranked", "mode": "retrieve"}
    ).json()
    assert body["mode"] == "retrieve"
    assert body["rendered"] == "- ranked claim"
    assert body["items"][0]["order_score"] == 1.23
    assert body["items"][0]["item"]["id"] == claim.id
    assert body["diagnostics"]["fts_hits"] == 1
    assert len(pipeline.retrieve_calls) == 1
    assert pipeline.retrieve_calls[0].goal == "ranked"


def test_search_invalid_mode_422(client):
    assert client.get(
        "/admin/memory/search", params={"q": "x", "mode": "bogus"}
    ).status_code == 422


def test_search_requires_q(client):
    assert client.get("/admin/memory/search").status_code == 422


# --- 7: writeback ----------------------------------------------------


@pytest.mark.asyncio
async def test_writeback_serializes_result(store, client, pipeline):
    lens = await _lens(store, "L", "c")
    from ntrp.memory.pipeline.types import PageEditOp

    pipeline.lens_writeback.result = WriteBackResult(
        applied=[(PageEditKind.ACCEPT, "c1"), (PageEditKind.ADD, "c2")],
        rejected=[(PageEditOp(kind=PageEditKind.EDIT, claim_id="dead"), "claim moved")],
        rederive_triggered=True,
    )
    resp = client.post(
        f"/admin/memory/lenses/{lens.id}/writeback",
        json={
            "ops": [
                {"kind": "accept", "claim_id": "c1"},
                {"kind": "add", "new_text": "new claim"},
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] == [
        {"kind": "accept", "id": "c1"},
        {"kind": "add", "id": "c2"},
    ]
    assert body["rejected"][0]["op"]["kind"] == "edit"
    assert body["rejected"][0]["reason"] == "claim moved"
    assert body["rederive_triggered"] is True
    assert pipeline.lens_writeback.calls[0][0] == lens.id


@pytest.mark.asyncio
async def test_writeback_validates_required_fields(store, client):
    lens = await _lens(store, "L", "c")
    # accept without claim_id -> 422
    r1 = client.post(
        f"/admin/memory/lenses/{lens.id}/writeback",
        json={"ops": [{"kind": "accept"}]},
    )
    assert r1.status_code == 422
    # add without new_text -> 422
    r2 = client.post(
        f"/admin/memory/lenses/{lens.id}/writeback",
        json={"ops": [{"kind": "add"}]},
    )
    assert r2.status_code == 422


def test_writeback_404_on_missing_lens(client):
    assert client.post(
        "/admin/memory/lenses/ghost/writeback",
        json={"ops": [{"kind": "accept", "claim_id": "c1"}]},
    ).status_code == 404


@pytest.mark.asyncio
async def test_writeback_404_on_deleted_lens(store, client):
    lens = await _lens(store, "L", "c")
    await store.delete_lens(lens.id)  # deleting the file removes the view
    assert client.post(
        f"/admin/memory/lenses/{lens.id}/writeback",
        json={"ops": [{"kind": "accept", "claim_id": "c1"}]},
    ).status_code == 404


# --- 8: lifecycle ----------------------------------------------------


@pytest.mark.asyncio
async def test_create_lens(store, client, pipeline):
    resp = client.post(
        "/admin/memory/lenses",
        json={"name": "Cooking", "criterion": "about cooking"},
    )
    assert resp.status_code == 200
    lens = resp.json()["lens"]
    assert lens["name"] == "Cooking"
    assert lens["criterion"] == "about cooking"
    assert pipeline.lens_registry.calls[-1] == (
        "create_lens",
        "Cooking",
        "about cooking",
        USER,
        LensRenderMode.FLAT,
    )


@pytest.mark.asyncio
async def test_edit_criterion(store, client):
    lens = await _lens(store, "L", "old criterion")
    resp = client.put(
        f"/admin/memory/lenses/{lens.id}/criterion",
        json={"criterion": "new criterion"},
    )
    assert resp.status_code == 200
    assert resp.json()["lens"]["criterion"] == "new criterion"
    # in-place update keeps the same id, active.
    updated = await store.get_lens(lens.id)
    assert updated.criterion == "new criterion"
    assert updated.status is LensStatus.ACTIVE


def test_edit_criterion_404_on_non_lens(client):
    assert client.put(
        "/admin/memory/lenses/ghost/criterion", json={"criterion": "x"}
    ).status_code == 404


@pytest.mark.asyncio
async def test_split_lens(store, client):
    parent = await _lens(store, "Sport", "about sport")
    resp = client.post(
        f"/admin/memory/lenses/{parent.id}/split",
        json={
            "into": [
                {"name": "Climbing", "criterion": "about climbing"},
                {"name": "Running", "criterion": "about running"},
            ]
        },
    )
    assert resp.status_code == 200
    children = resp.json()["children"]
    assert [c["name"] for c in children] == ["Climbing", "Running"]
    # parent dropped by default.
    assert await store.get_lens(parent.id) is None


@pytest.mark.asyncio
async def test_split_lens_keep_parent(store, client):
    parent = await _lens(store, "Sport", "about sport")
    client.post(
        f"/admin/memory/lenses/{parent.id}/split",
        json={
            "into": [{"name": "Climbing", "criterion": "c"}],
            "archive_parent": False,
        },
    )
    assert await store.get_lens(parent.id) is not None


@pytest.mark.asyncio
async def test_merge_lenses(store, client):
    a = await _lens(store, "A", "crit a")
    b = await _lens(store, "B", "crit b")
    resp = client.post(
        "/admin/memory/lenses/merge",
        json={"lens_ids": [a.id, b.id], "name": "AB", "criterion": "a or b"},
    )
    assert resp.status_code == 200
    assert resp.json()["lens"]["name"] == "AB"
    for lid in (a.id, b.id):
        assert await store.get_lens(lid) is None


def test_merge_requires_two(client):
    assert client.post(
        "/admin/memory/lenses/merge",
        json={"lens_ids": ["only-one"], "name": "X", "criterion": "c"},
    ).status_code == 422  # pydantic min_length=2


@pytest.mark.asyncio
async def test_delete_lens(store, client):
    lens = await _lens(store, "L", "c")
    resp = client.delete(f"/admin/memory/lenses/{lens.id}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    # the view is gone; claims (none here) would be untouched.
    assert await store.get_lens(lens.id) is None


def test_delete_lens_404_when_nothing_deleted(client):
    assert client.delete("/admin/memory/lenses/ghost").status_code == 404
