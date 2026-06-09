"""Memory router (`/admin/memory`) — the contract the desktop memory UI calls,
served from the live flat RecordStore + LensStore.

Hermetic: real tmp `memory.db` backs both records and lenses; FTS-only
(`search_index=None`) and `llm=None`, so membership degrades to raw hybrid
search and page synthesis to a raw bullet list — exercising the no-LLM bridge
paths end-to-end without a network. The KnowledgeRuntime dep is overridden with a
tiny holder exposing `_record_store` / `_lens_store`."""

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ntrp.memory.lenses import LensStore
from ntrp.memory.records import RecordStore
from ntrp.server.app import app
from ntrp.server.deps import require_knowledge_runtime


class _Knowledge:
    def __init__(self, records: RecordStore, lenses: LensStore):
        self._record_store = records
        self._lens_store = lenses


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    lenses = LensStore(tmp_path / "memory.db", records, llm=None, model=None)
    await records.add("Regina is allergic to penicillin", kind="fact")
    await records.add("Regina prefers tea over coffee", kind="preference")
    await records.add("ntrp uses FastAPI on the backend", kind="fact")

    app.dependency_overrides[require_knowledge_runtime] = lambda: _Knowledge(records, lenses)
    try:
        yield TestClient(app), records, lenses
    finally:
        app.dependency_overrides.pop(require_knowledge_runtime, None)
        await records.close()
        await lenses.close()


def test_routes_registered():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    for p in (
        "/admin/memory/scopes",
        "/admin/memory/items",
        "/admin/memory/lenses",
        "/admin/memory/lenses/{lens_id}/page",
        "/admin/memory/search",
        "/admin/memory/graph",
    ):
        assert p in paths


def test_scopes_empty(client):
    c, *_ = client
    assert c.get("/admin/memory/scopes").json() == {"scopes": []}


def test_list_items_shape(client):
    c, *_ = client
    body = c.get("/admin/memory/items").json()
    assert body["limit"] == 100
    assert len(body["items"]) == 3
    item = body["items"][0]
    for key in (
        "id", "content", "canonical_subject", "scope", "provenance", "status",
        "valid_from", "invalid_at", "source_refs", "corroboration",
        "last_relevant_at", "feedback", "created_at", "updated_at",
    ):
        assert key in item
    assert item["scope"] == {"kind": "user", "key": None}
    assert item["provenance"] in ("user_authored", "recorded", "inferred", "external")
    assert item["status"] == "active"


def test_get_item_no_edges(client):
    c, records, _ = client
    rid = c.get("/admin/memory/items").json()["items"][0]["id"]
    body = c.get(f"/admin/memory/items/{rid}").json()
    assert body["item"]["id"] == rid
    assert body["parents"] == [] and body["children"] == []
    assert c.get("/admin/memory/items/missing").status_code == 404


def test_create_lens_and_coverage(client):
    c, *_ = client
    created = c.post("/admin/memory/lenses", json={"name": "Regina", "criterion": "facts about Regina"})
    assert created.status_code == 200
    lens = created.json()["lens"]
    assert lens["render_mode"] == "grouped_by_subject"
    assert lens["provenance"] == "user_authored"
    lens_id = lens["id"]

    listed = c.get("/admin/memory/lenses").json()["lenses"]
    assert len(listed) == 1
    cov = listed[0]["coverage"]
    for key in ("lens_id", "scope_pool", "member_count", "ratio", "generic", "suggestion"):
        assert key in cov
    assert cov["scope_pool"] == 3
    assert cov["lens_id"] == lens_id


def test_create_lens_from_definition_markdown(client):
    c, *_ = client
    md = "# Health\n\n## Belongs\nMedical facts.\n"
    lens = c.post("/admin/memory/lenses", json={"definition_markdown": md}).json()["lens"]
    assert lens["name"] == "Health"
    assert "## Belongs" in lens["criterion"]


def test_lens_page_synchronous(client):
    c, *_ = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "Regina", "criterion": "Regina"}).json()["lens"]["id"]
    page = c.get(f"/admin/memory/lenses/{lens_id}/page").json()
    assert "status" not in page  # never the async-generation status
    for key in ("lens_id", "detail", "markdown", "blocks", "synthesized", "coverage", "groups"):
        assert key in page
    assert page["lens_id"] == lens_id
    if page["blocks"]:
        for key in ("claim_id", "content", "provenance", "corroboration", "feedback", "source_refs"):
            assert key in page["blocks"][0]


def test_page_status_idle(client):
    c, *_ = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "X", "criterion": "X"}).json()["lens"]["id"]
    status = c.get(f"/admin/memory/lenses/{lens_id}/page/status").json()
    assert status["status"] == "idle"
    assert status["lens_id"] == lens_id


def test_edit_criterion_by_id(client):
    c, *_ = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "Regina", "criterion": "old"}).json()["lens"]["id"]
    res = c.put(f"/admin/memory/lenses/{lens_id}/criterion", json={"criterion": "new criterion"})
    assert res.status_code == 200
    assert res.json()["lens"]["criterion"] == "new criterion"


def test_delete_lens_by_id(client):
    c, *_ = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "Temp", "criterion": "x"}).json()["lens"]["id"]
    assert c.delete(f"/admin/memory/lenses/{lens_id}").json() == {"deleted": True}
    assert c.get("/admin/memory/lenses").json()["lenses"] == []


def test_draft_lens_template(client):
    c, *_ = client
    md = c.post("/admin/memory/lenses/draft", json={"name": "Travel"}).json()["markdown"]
    assert "# Travel" in md and "## Belongs" in md


def test_search_fts(client):
    c, *_ = client
    body = c.get("/admin/memory/search", params={"q": "Regina"}).json()
    assert body["mode"] == "fts"
    assert body["degraded"] is True  # search_index=None
    assert all("content" in i for i in body["items"])


def test_whole_graph_nodes_only(client):
    c, *_ = client
    body = c.get("/admin/memory/graph").json()
    assert len(body["nodes"]) == 3
    assert body["edges"] == []
    assert body["scope"] == {"kind": "user", "key": None}


def test_item_graph_single_node(client):
    c, *_ = client
    rid = c.get("/admin/memory/items").json()["items"][0]["id"]
    body = c.get(f"/admin/memory/items/{rid}/graph").json()
    assert body["root_id"] == rid
    assert len(body["nodes"]) == 1 and body["edges"] == []


@pytest.mark.asyncio
async def test_writeback_include_reject_accept_edit(client):
    c, records, lenses = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "Regina", "criterion": "Regina"}).json()["lens"]["id"]
    ntrp_id = next(r.id for r in await records.list(limit=10) if "FastAPI" in r.text)

    # include
    res = c.post(f"/admin/memory/lenses/{lens_id}/writeback", json={"ops": [{"kind": "include", "claim_id": ntrp_id}]}).json()
    assert res["applied"] == [{"kind": "include", "id": ntrp_id}]
    assert res["rederive_triggered"] is True
    assert ntrp_id in {r.id for r in await lenses.members("Regina", limit=50)}

    # reject (removes from lens, record survives)
    res = c.post(f"/admin/memory/lenses/{lens_id}/writeback", json={"ops": [{"kind": "reject", "claim_id": ntrp_id}]}).json()
    assert res["applied"] == [{"kind": "reject", "id": ntrp_id}]
    assert await records.get(ntrp_id) is not None

    # accept (confirm)
    res = c.post(f"/admin/memory/lenses/{lens_id}/writeback", json={"ops": [{"kind": "accept", "claim_id": ntrp_id}]}).json()
    assert res["applied"] == [{"kind": "accept", "id": ntrp_id}]

    # edit (supersede with new text -> successor id, original survives the lineage)
    res = c.post(
        f"/admin/memory/lenses/{lens_id}/writeback",
        json={"ops": [{"kind": "edit", "claim_id": ntrp_id, "new_text": "ntrp uses FastAPI and SQLite"}]},
    ).json()
    assert len(res["applied"]) == 1 and res["applied"][0]["kind"] == "edit"
    successor_id = res["applied"][0]["id"]
    assert successor_id != ntrp_id
    assert (await records.get(successor_id)).text == "ntrp uses FastAPI and SQLite"


def test_create_and_pin_record(client):
    c, *_ = client
    created = c.post("/admin/memory/record", json={"text": "pinned fact", "kind_tag": "note"})
    assert created.status_code == 200
    rid = created.json()["record"]["id"]
    assert c.post(f"/admin/memory/record/{rid}/pin", json={"pinned": True}).json() == {
        "ok": True,
        "pinned": True,
    }
    # pinned record reads back as user_authored / confirmed
    item = c.get(f"/admin/memory/items/{rid}").json()["item"]
    assert item["provenance"] == "user_authored" and item["feedback"] == "confirmed"
    assert c.post("/admin/memory/record/missing/pin", json={"pinned": True}).status_code == 404


def test_writeback_rejects_bad_ops(client):
    c, *_ = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "Regina", "criterion": "Regina"}).json()["lens"]["id"]
    res = c.post(
        f"/admin/memory/lenses/{lens_id}/writeback",
        json={"ops": [{"kind": "edit", "claim_id": "x"}, {"kind": "include", "claim_id": "missing"}]},
    ).json()
    assert len(res["rejected"]) == 2
