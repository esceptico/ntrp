"""Memory router (`/admin/memory`) — the contract the desktop memory UI calls,
served from the live flat RecordStore + LensStore.

Hermetic: real tmp `memory.db` backs both records and lenses; FTS-only
(`search_index=None`) and `llm=None`, so membership degrades to raw hybrid
search and page synthesis to a raw bullet list — exercising the no-LLM bridge
paths end-to-end without a network. The KnowledgeRuntime dep is overridden with a
tiny holder exposing `_record_store` / `_lens_store`.

The client is a CONTEXT-MANAGED TestClient on a bare FastAPI app (no real
lifespan): lens create/edit KICK background tasks onto the request's event
loop, so the loop must outlive the request — starlette's per-request portal
(plain `TestClient(app)`) tears the loop down mid-task and strands the
aiosqlite worker, deadlocking the next DB call. Teardown drains in-flight
kicks ON the portal loop before the stores close."""

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ntrp.memory.lenses import LensStore
from ntrp.memory.records import RecordStore
from ntrp.server.app import app
from ntrp.server.deps import require_knowledge_runtime
from ntrp.server.routers.memory import router as memory_router


class _Knowledge:
    def __init__(self, records: RecordStore, lenses: LensStore):
        self._record_store = records
        self._lens_store = lenses


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    records = RecordStore(tmp_path / "memory.db", search_index=None)
    lenses = LensStore(tmp_path / "memory.db", records, llm=None, model=None)
    allergy = await records.add("Regina is allergic to penicillin", kind="fact")
    tea = await records.add("Regina prefers tea over coffee", kind="preference")
    fastapi = await records.add("ntrp uses FastAPI on the backend", kind="fact")
    await records.set_labels(allergy.id, ["Regina", "health"])
    await records.set_labels(tea.id, ["Regina"])
    await records.set_labels(fastapi.id, ["ntrp"])

    test_app = FastAPI()
    test_app.include_router(memory_router)
    test_app.dependency_overrides[require_knowledge_runtime] = lambda: _Knowledge(records, lenses)
    with TestClient(test_app) as c:
        yield c, records, lenses
        c.portal.call(lenses.wait)  # drain kicked tasks on THEIR loop
    await records.close()
    await lenses.close()


def test_routes_registered():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    for p in (
        "/admin/memory/scopes",
        "/admin/memory/items",
        "/admin/memory/lenses",
        "/admin/memory/lenses/{lens_id}/page",
        "/admin/memory/lenses/{lens_id}/promote",
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
        "id", "content", "canonical_subject", "labels", "scope", "provenance",
        "status", "valid_from", "invalid_at", "source_refs", "corroboration",
        "last_relevant_at", "feedback", "created_at", "updated_at",
    ):
        assert key in item
    assert item["scope"] == {"kind": "user", "key": None}
    assert item["provenance"] in ("user_authored", "recorded", "inferred", "external")
    assert item["status"] == "active"
    # Labels are batch-hydrated onto every item.
    by_content = {i["content"]: i for i in body["items"]}
    assert by_content["Regina is allergic to penicillin"]["labels"] == ["Regina", "health"]
    assert by_content["ntrp uses FastAPI on the backend"]["labels"] == ["ntrp"]


def test_get_item_no_edges(client):
    c, _, _ = client
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
    # Heading lines are template structure, never criterion text.
    assert lens["criterion"] == "Medical facts."


def test_lens_page_served_from_cache_after_background_kick(client):
    c, _, lenses = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "Regina", "criterion": "Regina"}).json()["lens"]["id"]
    c.portal.call(lenses.wait)  # let the kicked evaluate+render land
    page = c.get(f"/admin/memory/lenses/{lens_id}/page").json()
    assert "status" not in page  # cache hit -> a real ProjectedPage
    for key in ("lens_id", "detail", "markdown", "blocks", "synthesized", "coverage", "groups"):
        assert key in page
    assert page["lens_id"] == lens_id
    assert page["blocks"]  # llm=None degrades to raw search members, never empty here
    for key in ("claim_id", "content", "provenance", "corroboration", "feedback", "source_refs"):
        assert key in page["blocks"][0]

    # refresh=true kicks a background re-derive and answers with the status shape.
    refreshed = c.get(f"/admin/memory/lenses/{lens_id}/page", params={"refresh": "true"}).json()
    assert refreshed["status"] == "generating"
    c.portal.call(lenses.wait)


def test_page_status_idle_after_kick_lands(client):
    c, _, lenses = client
    lens_id = c.post("/admin/memory/lenses", json={"name": "X", "criterion": "X"}).json()["lens"]["id"]
    c.portal.call(lenses.wait)
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


def test_whole_graph_is_the_derivation_dag(client):
    c, records, _ = client
    # Empty until something is inferred — the graph IS the epistemic structure.
    assert c.get("/admin/memory/graph").json()["nodes"] == []

    items = c.get("/admin/memory/items").json()["items"]
    allergy = next(i for i in items if "allergic" in i["content"])
    tea = next(i for i in items if "tea" in i["content"])
    derived = c.portal.call(
        lambda: records.add_derived(
            "Regina has documented medical preferences",
            premise_ids=[allergy["id"], tea["id"]], mode="induction", question="q",
        )
    )

    body = c.get("/admin/memory/graph").json()
    assert body["scope"] == {"kind": "user", "key": None}
    nodes = {n["id"]: n for n in body["nodes"]}
    assert set(nodes) == {derived.id, allergy["id"], tea["id"]}
    assert nodes[derived.id]["provenance"] == "inferred"
    assert nodes[derived.id]["depth"] == 1
    edges = {(e["child_id"], e["parent_id"]) for e in body["edges"]}
    assert edges == {(derived.id, allergy["id"]), (derived.id, tea["id"])}
    assert all(e["role"] == "evidence" for e in body["edges"])
    # Record nodes still carry their labels as metadata.
    assert nodes[allergy["id"]]["labels"] == ["Regina", "health"]


def test_item_graph_walks_justifications(client):
    c, records, _ = client
    items = c.get("/admin/memory/items").json()["items"]
    allergy = next(i for i in items if "allergic" in i["content"])
    tea = next(i for i in items if "tea" in i["content"])
    derived = c.portal.call(
        lambda: records.add_derived(
            "Regina has documented medical preferences",
            premise_ids=[allergy["id"], tea["id"]], mode="induction", question="q",
        )
    )
    body = c.get(f"/admin/memory/items/{allergy['id']}/graph").json()
    assert body["root_id"] == allergy["id"]
    # root -> its dependent inference -> the inference's other premise.
    assert {n["id"] for n in body["nodes"]} == {allergy["id"], derived.id, tea["id"]}
    edges = {(e["child_id"], e["parent_id"]) for e in body["edges"]}
    assert edges == {(derived.id, allergy["id"]), (derived.id, tea["id"])}
    assert c.get("/admin/memory/items/missing/graph").status_code == 404


def test_promote_lens_to_label(client):
    c, records, lenses = client
    lens_id = c.post(
        "/admin/memory/lenses", json={"name": "Regina", "criterion": "Regina"}
    ).json()["lens"]["id"]
    c.portal.call(lenses.wait)  # promote tags the CACHED membership — let the kick land

    res = c.post(f"/admin/memory/lenses/{lens_id}/promote", json={"label": "regina-circle"})
    assert res.status_code == 200
    assert res.json() == {"promoted": 2, "label": "regina-circle"}

    # The label is now in vocabulary, counting the tagged members.
    tagged = c.portal.call(lambda: records.records_for_label("regina-circle"))
    assert len(tagged) == 2
    # The lens stays viewable, marked promoted.
    listed = c.get("/admin/memory/lenses").json()["lenses"]
    assert listed[0]["lens"]["promoted_to"] == "regina-circle"

    assert c.post(f"/admin/memory/lenses/{lens_id}/promote", json={"label": "  "}).status_code == 422
    assert c.post("/admin/memory/lenses/missing/promote", json={"label": "x"}).status_code == 404


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
