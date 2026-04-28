from fastapi.testclient import TestClient

from ntrp.server.app import app
from ntrp.server.runtime import get_runtime


class _Config:
    has_any_model = True
    api_key_hash = None


class _Runtime:
    connected = True
    config = _Config()
    replayed_event_ids = None
    pruned = None

    async def get_outbox_health(self):
        return {
            "worker_running": True,
            "pending": 2,
            "ready": 1,
            "running": 0,
            "dead": 1,
        }

    async def get_outbox_status(self):
        return {
            "status": "running",
            "worker": {
                "running": True,
                "worker_id": "test-worker",
            },
            "events": {
                "total": 3,
                "ready": 1,
                "scheduled": 1,
                "by_status": {
                    "pending": 2,
                    "running": 0,
                    "completed": 0,
                    "dead": 1,
                },
                "recent_dead": [],
            },
        }

    async def replay_outbox_dead_events(self, event_ids):
        self.replayed_event_ids = event_ids
        return {
            "status": "queued",
            "requested": event_ids,
            "replayed": event_ids,
            "missing": [],
            "skipped": [],
        }

    async def prune_outbox_completed(self, *, before, limit):
        self.pruned = {"before": before, "limit": limit}
        return {
            "status": "deleted",
            "deleted": 7,
            "before": before.isoformat(),
            "limit": limit,
        }


def test_health_includes_outbox_summary():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert response.json()["outbox"] == {
        "worker_running": True,
        "pending": 2,
        "ready": 1,
        "running": 0,
        "dead": 1,
    }


def test_outbox_status_endpoint_returns_detailed_state():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).get("/outbox/status")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert response.json()["events"]["by_status"]["dead"] == 1
    assert response.json()["worker"]["worker_id"] == "test-worker"


def test_replay_outbox_dead_events_requires_explicit_ids():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).post("/outbox/dead/replay", json={"event_ids": [3, 5]})
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert runtime.replayed_event_ids == [3, 5]
    assert response.json()["replayed"] == [3, 5]


def test_replay_outbox_dead_events_rejects_empty_id_list():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).post("/outbox/dead/replay", json={"event_ids": []})
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 422
    assert runtime.replayed_event_ids is None


def test_prune_outbox_completed_passes_cutoff_and_limit():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).delete("/outbox/completed?older_than_days=14&limit=25")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert response.json()["deleted"] == 7
    assert response.json()["older_than_days"] == 14
    assert response.json()["limit"] == 25
    assert runtime.pruned["limit"] == 25
