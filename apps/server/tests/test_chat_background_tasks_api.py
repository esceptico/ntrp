from fastapi.testclient import TestClient

from ntrp.server.app import app
from ntrp.server.runtime import get_runtime


class _Store:
    def __init__(self):
        self.cancelled = []

    async def list_background_agent_runs(self, session_id, include_terminal=True):
        return [
            {
                "task_id": "bg-1",
                "child_run_id": "bg-1",
                "session_id": session_id,
                "parent_run_id": "run-1",
                "parent_tool_call_id": "call-background",
                "agent_type": "background_research",
                "wait": False,
                "status": "running",
                "command": "research",
                "detail": "read files",
                "result_ref": None,
                "created_at": "2026-05-15T00:00:00+00:00",
                "started_at": "2026-05-15T00:00:00+00:00",
                "updated_at": "2026-05-15T00:00:01+00:00",
                "ended_at": None,
                "cancel_requested_at": None,
                "notified_at": None,
            }
        ]

    async def request_background_agent_cancel(self, session_id, task_id):
        self.cancelled.append((session_id, task_id))
        return True


class _SessionService:
    def __init__(self):
        self.store = _Store()


class _Runtime:
    def __init__(self):
        self.session_service = _SessionService()

    @property
    def run_registry(self):
        return self

    def get_background_registry(self, session_id):
        return self

    def list_pending(self):
        return [("bg-1", "research")]

    def cancel(self, task_id):
        return None


def test_background_tasks_endpoint_returns_durable_snapshot():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).get("/chat/background-tasks?session_id=sess-1")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert response.json()["tasks"][0]["status"] == "running"
    assert response.json()["tasks"][0]["detail"] == "read files"
    assert response.json()["tasks"][0]["child_run_id"] == "bg-1"
    assert response.json()["tasks"][0]["parent_tool_call_id"] == "call-background"
    assert response.json()["tasks"][0]["agent_type"] == "background_research"
    assert response.json()["tasks"][0]["wait"] is False


def test_background_task_cancel_requests_durable_cancel():
    runtime = _Runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        response = TestClient(app).post("/chat/background-tasks/bg-1/cancel?session_id=sess-1")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert response.status_code == 200
    assert response.json()["status"] == "cancel_requested"
    assert runtime.session_service.store.cancelled == [("sess-1", "bg-1")]
