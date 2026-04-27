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


import asyncio

from ntrp.events.sse import MessageIngestedEvent
from ntrp.server.bus import SessionBus
from ntrp.server.state import RunState


def _drain_factory(bus: SessionBus, run: RunState):
    """Mirror the closure built inside services.chat.run_chat for testing."""
    pending_messages: list[dict] = []
    run.inject_queue = pending_messages

    from ntrp.services.chat import _build_get_pending  # to be added in Step 3

    return pending_messages, _build_get_pending(pending_messages, bus, run)


@pytest.mark.asyncio
async def test_drain_emits_ingested_for_entries_with_client_id():
    bus = SessionBus(session_id="sess-1")
    run = RunState(run_id="cool-otter", session_id="sess-1")
    pending, get_pending = _drain_factory(bus, run)
    queue = bus.subscribe()

    pending.append({"role": "user", "content": "first", "client_id": "cid-1"})
    pending.append({"role": "user", "content": "second"})  # background task, no client_id
    pending.append({"role": "user", "content": "third", "client_id": "cid-3"})

    drained = await get_pending()

    # client_id is stripped before delivery to the LLM
    assert drained == [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    # Two ingestion events emitted, in order
    events = [queue.get_nowait() for _ in range(2)]
    assert all(isinstance(e, MessageIngestedEvent) for e in events)
    assert [e.client_id for e in events] == ["cid-1", "cid-3"]
    assert all(e.run_id == "cool-otter" for e in events)
    assert queue.empty()


@pytest.mark.asyncio
async def test_drain_no_events_when_queue_empty():
    bus = SessionBus(session_id="sess-1")
    run = RunState(run_id="cool-otter", session_id="sess-1")
    _, get_pending = _drain_factory(bus, run)
    queue = bus.subscribe()

    drained = await get_pending()

    assert drained == []
    assert queue.empty()


# --- DELETE /chat/inject/{client_id} ---


@pytest.fixture
def client_no_active_run():
    """Spin up the FastAPI app with a stub Runtime that has no active run."""
    runtime = Runtime.__new__(Runtime)
    runtime.run_registry = RunRegistry()
    runtime.config = type("C", (), {"has_any_model": True, "api_key_hash": None})()
    # No run created → get_active_run always returns None

    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[_get_bus_registry] = lambda: BusRegistry()

    yield TestClient(app)

    app.dependency_overrides.pop(get_runtime, None)
    app.dependency_overrides.pop(_get_bus_registry, None)


def test_delete_inject_returns_200_when_entry_present(client_with_active_run):
    c, run = client_with_active_run
    run.inject_queue.append({"role": "user", "content": "x", "client_id": "cid-1"})

    resp = c.delete("/chat/inject/cid-1?session_id=sess-1")

    assert resp.status_code == 200
    assert run.inject_queue == []


def test_delete_inject_returns_409_when_already_drained(client_with_active_run):
    c, run = client_with_active_run
    # Active run, but the client_id was already drained → not in queue
    assert run.inject_queue == []

    resp = c.delete("/chat/inject/cid-missing?session_id=sess-1")

    assert resp.status_code == 409


def test_delete_inject_returns_404_when_no_active_run(client_no_active_run):
    resp = client_no_active_run.delete("/chat/inject/cid-x?session_id=sess-none")
    assert resp.status_code == 404


# --- Full chain: agent.stream + real closure + real bus + mid-run inject ---


@pytest.mark.asyncio
async def test_full_chain_inject_during_run_emits_ingested_and_lands_in_messages():
    """Simulate the production chain: an agent is mid-iteration, a user message
    is appended to inject_queue (as POST /chat/message would do), and the next
    iteration's drain must (a) emit a MessageIngestedEvent on the bus and
    (b) extend the message list so the LLM sees the injected text."""
    from ntrp.agent import AgentHooks, ToolResult
    from ntrp.services.chat import _build_get_pending
    from tests.test_agent_lib import FakeExecutor, FakeLLM, _make_agent, _msgs, _response, _tc

    bus = SessionBus(session_id="sess-inj")
    run = RunState(run_id="cool-otter", session_id="sess-inj")
    pending: list[dict] = []
    run.inject_queue = pending

    sub = bus.subscribe()

    # LLM produces: tool_call → (drain happens) → text response.
    # We inject between iterations 1 and 2.
    llm = FakeLLM(
        [
            _response(tool_calls=[_tc("c1", "noop", {})]),
            _response(text="acknowledged"),
        ]
    )
    executor = FakeExecutor({"noop": ToolResult(content="ok", preview="ok")})
    agent = _make_agent(
        llm,
        executor,
        hooks=AgentHooks(get_pending_messages=_build_get_pending(pending, bus, run)),
    )

    messages = _msgs()

    # Append BEFORE running so the drain at top of iter 2 sees it.
    # (In production, POST runs concurrently with the agent loop; appending
    # before iter 2's drain is the same observable state.)
    pending.append({"role": "user", "content": "follow-up", "client_id": "cid-XYZ"})

    result = await agent.run(messages)

    # The agent must have observed the injected user turn.
    assert any(m.get("content") == "follow-up" for m in messages), \
        f"injected message not in messages: {messages}"
    assert result.text == "acknowledged"

    # The bus must have received a MessageIngestedEvent with the right client_id.
    received: list = []
    while not sub.empty():
        received.append(sub.get_nowait())
    ingested = [e for e in received if isinstance(e, MessageIngestedEvent)]
    assert len(ingested) == 1, f"expected 1 ingestion event, got {len(ingested)}: {received}"
    assert ingested[0].client_id == "cid-XYZ"
    assert ingested[0].run_id == "cool-otter"

    # The forwarded user message in `messages` MUST NOT carry client_id (stripped).
    injected_msg = next(m for m in messages if m.get("content") == "follow-up")
    assert "client_id" not in injected_msg, f"client_id leaked to LLM: {injected_msg}"


@pytest.mark.asyncio
async def test_full_chain_inject_during_final_response_continues_loop():
    """User submits while the LLM is producing its end-turn response.
    My agent.py fix should drain pending, continue the loop, emit ingestion event."""
    from ntrp.agent import AgentHooks
    from ntrp.services.chat import _build_get_pending
    from tests.test_agent_lib import FakeExecutor, FakeLLM, _make_agent, _msgs, _response

    bus = SessionBus(session_id="sess-inj2")
    run = RunState(run_id="cool-otter", session_id="sess-inj2")
    pending: list[dict] = []
    run.inject_queue = pending

    sub = bus.subscribe()

    # Two final-style responses (no tool calls). After the first, we inject;
    # the agent must continue rather than declaring END_TURN.
    llm = FakeLLM(
        [
            _response(text="first answer"),
            _response(text="second answer"),
        ]
    )
    closure = _build_get_pending(pending, bus, run)

    # Wrap the closure so we can inject between calls.
    call_count = 0

    async def hook():
        nonlocal call_count
        call_count += 1
        # On the 2nd call (which is the post-LLM drain check before declaring end-turn),
        # there's nothing pending yet — append now to simulate user submit during stream.
        if call_count == 2:
            pending.append({"role": "user", "content": "wait!", "client_id": "cid-LATE"})
        return await closure()

    agent = _make_agent(llm, FakeExecutor({}), hooks=AgentHooks(get_pending_messages=hook))

    messages = _msgs()
    result = await agent.run(messages)

    # Agent must have continued past the first response and produced a second.
    assert result.text == "second answer", f"agent did not loop: {result.text}"
    assert any(m.get("content") == "wait!" for m in messages)

    # Ingestion event was emitted.
    received: list = []
    while not sub.empty():
        received.append(sub.get_nowait())
    ingested = [e for e in received if isinstance(e, MessageIngestedEvent)]
    assert len(ingested) == 1
    assert ingested[0].client_id == "cid-LATE"
