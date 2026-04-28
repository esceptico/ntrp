from fastapi.testclient import TestClient

from ntrp.server.app import app
from ntrp.server.runtime import get_runtime


class _Config:
    has_any_model = True
    api_key_hash = None


class _Runtime:
    connected = True
    config = _Config()

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


def test_health_includes_outbox_summary():
    app.dependency_overrides[get_runtime] = lambda: _Runtime()
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
    app.dependency_overrides[get_runtime] = lambda: _Runtime()
    try:
        response = TestClient(app).get("/outbox/status")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert response.json()["events"]["by_status"]["dead"] == 1
    assert response.json()["worker"]["worker_id"] == "test-worker"
