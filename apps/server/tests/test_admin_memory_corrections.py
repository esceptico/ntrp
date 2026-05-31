from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import ntrp.memory.learnings as learnings_mod
from ntrp.memory.learnings import LearningsStore
from ntrp.server.deps import require_memory, require_pattern_finder
from ntrp.server.routers.admin_memory import router as admin_memory_router


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setattr(learnings_mod, "NTRP_DIR", tmp_path)
    app = FastAPI()
    app.include_router(admin_memory_router)
    return app, LearningsStore(base_dir=tmp_path / "memory" / "learnings")


class _FakeWatcher:
    def __init__(self, result):
        self.result = result

    async def undo(self, *, child_id: str, parent_id: str):
        return self.result


def test_undo_records_not_same_correction(app_env):
    app, store = app_env
    watcher = _FakeWatcher({"already_undone": False, "restored": True, "cross_scope": False})
    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(contradiction_watcher=watcher)

    resp = TestClient(app).post("/admin/memory/contradictions/child1/parent1/undo")

    assert resp.status_code == 200
    assert store.load_not_same_pairs() == frozenset({frozenset({"child1", "parent1"})})


def test_undo_already_undone_records_nothing(app_env):
    app, store = app_env
    watcher = _FakeWatcher({"already_undone": True, "restored": False, "cross_scope": False})
    app.dependency_overrides[require_pattern_finder] = lambda: SimpleNamespace(contradiction_watcher=watcher)

    resp = TestClient(app).post("/admin/memory/contradictions/c/p/undo")

    assert resp.status_code == 200
    assert store.load_not_same_pairs() == frozenset()


class _FakeItem:
    def __init__(self, item_id, kind, content):
        self.id = item_id
        self.kind = kind
        self.content = content
        self.title = None
        self.provenance = "inferred"
        self.source_refs = []
        self.confidence = 0.5
        self.status = "active"
        self.valid_from = None
        self.invalid_at = None
        self.scope = "user"
        self.tags = []
        self.artifact_ref = None
        self.usage = None
        self.feedback = None
        self.created_at = None
        self.updated_at = None
        self.embedding = None


class _FakeRepo:
    def __init__(self, item):
        self.item_id = item.id
        self.kind = item.kind
        self.content = item.content

    async def get_item(self, item_id):
        if item_id != self.item_id:
            return None
        return _FakeItem(self.item_id, self.kind, self.content)

    async def update_item(self, item_id, *, content, **kwargs):
        self.content = content


class _FakeEmbedder:
    async def embed_one(self, text):
        return None


def _fake_memory(item):
    return SimpleNamespace(memory=SimpleNamespace(items=_FakeRepo(item), embedder=_FakeEmbedder()))


def test_claim_edit_records_dedup_learning(app_env):
    app, store = app_env
    item = _FakeItem("claim1", "claim", "old text")
    app.dependency_overrides[require_memory] = lambda: _fake_memory(item)

    resp = TestClient(app).put("/admin/memory/items/claim1", json={"content": "new text"})

    assert resp.status_code == 200
    assert "claim claim1" in store.load("dedup")
    assert store.load("entity_link") == ""


def test_entity_edit_records_entity_link_learning(app_env):
    app, store = app_env
    item = _FakeItem("ent1", "entity", "old name")
    app.dependency_overrides[require_memory] = lambda: _fake_memory(item)

    resp = TestClient(app).put("/admin/memory/items/ent1", json={"content": "new name"})

    assert resp.status_code == 200
    assert "entity ent1" in store.load("entity_link")


def test_unchanged_content_records_nothing(app_env):
    app, store = app_env
    item = _FakeItem("claim2", "claim", "same")
    app.dependency_overrides[require_memory] = lambda: _fake_memory(item)

    resp = TestClient(app).put("/admin/memory/items/claim2", json={"title": "t"})

    assert resp.status_code == 200
    assert store.load("dedup") == ""


def test_non_adjudicator_kind_records_nothing(app_env):
    app, store = app_env
    item = _FakeItem("ep1", "episode", "old body")
    app.dependency_overrides[require_memory] = lambda: _fake_memory(item)

    resp = TestClient(app).put("/admin/memory/items/ep1", json={"content": "new body"})

    assert resp.status_code == 200
    assert store.list_adjudicators() == []
