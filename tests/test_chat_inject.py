import json

from ntrp.events.sse import MessageIngestedEvent
from ntrp.server.schemas import ChatRequest


def test_message_ingested_event_serialization():
    event = MessageIngestedEvent(client_id="abc-123", run_id="cool-otter")
    sse = event.to_sse_string()
    assert "event: message_ingested" in sse
    payload = json.loads(sse.split("data: ", 1)[1].strip())
    assert payload == {
        "type": "message_ingested",
        "client_id": "abc-123",
        "run_id": "cool-otter",
    }


def test_chat_request_accepts_client_id():
    req = ChatRequest(message="hi", client_id="abc-123")
    assert req.client_id == "abc-123"


def test_chat_request_client_id_optional():
    req = ChatRequest(message="hi")
    assert req.client_id is None


import pytest
from fastapi.testclient import TestClient

from ntrp.server.app import app, _get_bus_registry
from ntrp.server.bus import BusRegistry
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.server.state import RunRegistry, RunStatus


@pytest.fixture
def client_with_active_run():
    """Spin up the FastAPI app with a stub Runtime that already has an active run."""
    runtime = Runtime.__new__(Runtime)
    runtime.run_registry = RunRegistry()
    runtime.config = type("C", (), {"has_any_model": True, "api_key_hash": None})()
    run = runtime.run_registry.create_run("sess-1")
    run.status = RunStatus.RUNNING

    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[_get_bus_registry] = lambda: BusRegistry()

    yield TestClient(app), run

    app.dependency_overrides.pop(get_runtime, None)
    app.dependency_overrides.pop(_get_bus_registry, None)


def test_post_chat_message_stores_client_id_when_run_active(client_with_active_run):
    c, run = client_with_active_run
    resp = c.post(
        "/chat/message",
        json={"message": "follow-up", "session_id": "sess-1", "client_id": "cid-1"},
    )
    assert resp.status_code == 200
    assert len(run.inject_queue) == 1
    entry = run.inject_queue[0]
    assert entry["role"] == "user"
    assert entry["client_id"] == "cid-1"
    assert entry["content"] == "follow-up"
