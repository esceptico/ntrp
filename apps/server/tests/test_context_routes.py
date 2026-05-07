from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ntrp.context.models import SessionData, SessionState
from ntrp.server.app import app
from ntrp.server.deps import require_session_service
from ntrp.server.runtime import get_runtime
from ntrp.server.state import RunRegistry, RunStatus
from ntrp.tools.executor import ToolExecutor


def test_context_routes_are_registered():
    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/context" in paths
    assert "/compact" in paths
    assert "/directives" in paths


class _Config:
    chat_model = "claude-sonnet-4-6"


class _Runtime:
    def __init__(self):
        self.config = _Config()
        self.executor = ToolExecutor()
        self.run_registry = RunRegistry()


class _SessionService:
    async def load(self, session_id: str | None = None):
        state = SessionState(session_id=session_id or "sess-1", started_at=datetime.now(UTC))
        return SessionData(state=state, messages=[{"role": "user", "content": "hi"}], last_input_tokens=123)

    async def list_episodes(self, session_id: str, limit: int = 100):
        return [
            {
                "session_id": session_id,
                "episode_id": f"{session_id}:0",
                "turn_index": 0,
                "user_message_id": "u-1",
                "message_start_id": "u-1",
                "message_end_id": "a-1",
                "message_start_seq": 1,
                "message_end_seq": 2,
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": "2026-01-01T00:00:01+00:00",
            }
        ][:limit]


def test_context_usage_reports_loaded_deferred_tool_counts():
    runtime = _Runtime()
    run = runtime.run_registry.create_run("sess-1")
    run.status = RunStatus.RUNNING
    run.messages = [{"role": "user", "content": "active"}]
    run.loaded_tools.add("set_directives")

    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[require_session_service] = lambda: _SessionService()
    try:
        response = TestClient(app).get("/context?session_id=sess-1")
    finally:
        app.dependency_overrides.pop(get_runtime, None)
        app.dependency_overrides.pop(require_session_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["message_count"] == 1
    assert data["loaded_tool_count"] == 1
    assert data["deferred_tool_count"] >= 1
    assert data["visible_tool_count"] < data["tool_count"]


def test_session_episodes_route_returns_durable_turn_ranges():
    app.dependency_overrides[require_session_service] = lambda: _SessionService()
    try:
        response = TestClient(app).get("/session/episodes?session_id=sess-1")
    finally:
        app.dependency_overrides.pop(require_session_service, None)

    assert response.status_code == 200
    assert response.json()["episodes"][0]["message_start_id"] == "u-1"
    assert response.json()["episodes"][0]["message_end_id"] == "a-1"
