from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import ntrp.memory.learnings as learnings_mod
from ntrp.server.routers.learnings import router as learnings_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(learnings_mod, "NTRP_DIR", tmp_path)
    app = FastAPI()
    app.include_router(learnings_router)
    return TestClient(app)


def test_record_and_read_roundtrip(client):
    resp = client.post(
        "/admin/memory/learnings/entity_link",
        json={
            "action": "not_same",
            "summary": "Regina Lin is not Regina Volkov",
            "subjects": ["a", "b"],
            "proposed": "merge(a, b)",
            "correct": "not_same",
        },
    )
    assert resp.status_code == 200
    assert "Regina Lin is not Regina Volkov" in resp.json()["markdown"]

    got = client.get("/admin/memory/learnings/entity_link")
    assert got.status_code == 200
    assert "- subjects: a, b" in got.json()["markdown"]

    listing = client.get("/admin/memory/learnings")
    assert listing.status_code == 200
    assert "entity_link" in listing.json()["present"]
    assert "dedup" in listing.json()["adjudicators"]


def test_put_overwrites(client):
    client.post("/admin/memory/learnings/dedup", json={"action": "edit", "summary": "first"})
    resp = client.put("/admin/memory/learnings/dedup", json={"markdown": "# custom\nhand written rule\n"})
    assert resp.status_code == 200
    assert client.get("/admin/memory/learnings/dedup").json()["markdown"] == "# custom\nhand written rule\n"


def test_unknown_adjudicator_404(client):
    assert client.get("/admin/memory/learnings/bogus").status_code == 404
    assert client.post("/admin/memory/learnings/bogus", json={"action": "x", "summary": "y"}).status_code == 404
    assert client.put("/admin/memory/learnings/bogus", json={"markdown": "z"}).status_code == 404
