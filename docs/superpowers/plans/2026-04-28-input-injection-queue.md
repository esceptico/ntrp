# Input Injection Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Queue user messages submitted while the agent is mid-run, deliver them at the next agent-loop boundary (Claude-Code-style same-run continuation), and render them as distinct queued bubbles with cancel until ingested.

**Architecture:** Two-sided queue correlated by `client_id`. Frontend keeps a per-session list of queued bubbles in the zustand store. POST `/chat/message` with `client_id` lands the message in `run.inject_queue`. The agent loop's existing `_drain_pending` consumes entries at iteration boundaries; the closure now also emits a `message_ingested` SSE event per consumed entry. Frontend matches by `client_id`, removes the bubble from the queue, appends a normal user turn to the conversation. Cancel = `DELETE /chat/inject/{client_id}` with race-safe semantics (200 / 409 / 404).

**Tech Stack:** Python 3.13 + FastAPI + pytest-asyncio (backend); TypeScript + React + Zustand + OpenTUI (frontend). `uv run` for backend tooling, `bun` for frontend.

**Spec:** `docs/superpowers/specs/2026-04-28-input-injection-queue-design.md`

**Backend status note:** The backend portion is implemented and now has `RunState`
as the owner of the injection queue lifecycle. API handlers queue/cancel through
`RunState`, and the agent hook drains through `RunState.drain_injections()` so the
raw list is not treated as a shared protocol by callers.

---

## File Map

**Backend (`ntrp/`):**
- Modify `ntrp/events/sse.py` — add `MessageIngestedEvent` and event-type enum value.
- Modify `ntrp/server/schemas.py` — add `client_id: str | None` to `ChatRequest`.
- Modify `ntrp/server/app.py` — pass `client_id` into the inject-queue entry; add `DELETE /chat/inject/{client_id}` handler.
- Modify `ntrp/services/chat.py` — `_get_pending` closure pops `client_id` and emits `message_ingested` per matching entry.
- New `tests/test_chat_inject.py` — covers drain emission, cancel semantics, and 200/409/404 paths.

**Frontend (`ntrp-ui/`):**
- Modify `ntrp-ui/src/types.ts` — add `MessageIngestedEvent`, expand `ServerEvent` union.
- Modify `ntrp-ui/src/api/chat.ts` — `sendChatMessage` accepts optional `client_id`; new `cancelQueuedMessage(client_id, sessionId)`.
- Modify `ntrp-ui/src/stores/streamingStore.ts` — add per-session `queuedMessages: QueuedMessage[]`, plus mutator helpers.
- Modify `ntrp-ui/src/hooks/useStreaming.ts` — replace the streaming branch of `sendMessage` with an `enqueueMessage` action; add `cancelQueued`; handle `message_ingested`; reconcile orphans on run-terminal events.
- New `ntrp-ui/src/components/chat/QueuedMessages.tsx` — renders queued bubbles below `InputArea` with × cancel buttons.
- Modify `ntrp-ui/src/components/chat/InputArea.tsx` — drop the inline `queueCount` badge.
- Modify `ntrp-ui/src/App.tsx` — `handleSubmit` always enqueues when `isStreaming || pendingApproval`; render `QueuedMessages`; remove `useMessageQueue` import.
- Delete `ntrp-ui/src/hooks/useMessageQueue.ts` — superseded by store-resident queue.

---

## Conventions

- Backend tests run with `uv run pytest path/to/test.py::test_name -v`.
- Backend lints / formats follow existing style (no docstrings unless non-obvious; imports at top; dataclasses).
- Each task ends with a commit. Use Conventional Commits style matching the repo (`feat:`, `fix:`, `refactor:`, `test:`).
- Never use `--no-verify`. Pre-commit hooks must pass.
- Frontend changes built with `cd ntrp-ui && bun run build`. Type-check with `cd ntrp-ui && bun run typecheck` if available, otherwise `bun run build` will surface type errors.

---

## Task 1: Add `MessageIngestedEvent` to backend SSE event catalog

**Files:**
- Modify: `ntrp/events/sse.py`
- Test: `tests/test_chat_inject.py` (new file)

- [ ] **Step 1: Create the test file with the failing event-shape test**

Write `tests/test_chat_inject.py`:

```python
import json

from ntrp.events.sse import MessageIngestedEvent


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
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/test_chat_inject.py::test_message_ingested_event_serialization -v`
Expected: FAIL with `ImportError: cannot import name 'MessageIngestedEvent'`.

- [ ] **Step 3: Add the event type and dataclass**

In `ntrp/events/sse.py`, add `MESSAGE_INGESTED` to the `EventType` enum (place after `RUN_BACKGROUNDED`):

```python
class EventType(StrEnum):
    # ... existing values ...
    RUN_BACKGROUNDED = "run_backgrounded"
    MESSAGE_INGESTED = "message_ingested"
    AUTOMATION_PROGRESS = "automation_progress"
    AUTOMATION_FINISHED = "automation_finished"
```

Add the dataclass after `RunBackgroundedEvent` (around line 164):

```python
@dataclass(frozen=True)
class MessageIngestedEvent(SSEEvent):
    type: EventType = field(default=EventType.MESSAGE_INGESTED, init=False)
    client_id: str
    run_id: str
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `uv run pytest tests/test_chat_inject.py::test_message_ingested_event_serialization -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ntrp/events/sse.py tests/test_chat_inject.py
git commit -m "feat(sse): add message_ingested event for inject queue"
```

---

## Task 2: Add `client_id` to `ChatRequest`

**Files:**
- Modify: `ntrp/server/schemas.py:13-19`
- Test: `tests/test_chat_inject.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_chat_inject.py`:

```python
from ntrp.server.schemas import ChatRequest


def test_chat_request_accepts_client_id():
    req = ChatRequest(message="hi", client_id="abc-123")
    assert req.client_id == "abc-123"


def test_chat_request_client_id_optional():
    req = ChatRequest(message="hi")
    assert req.client_id is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_chat_inject.py -v -k client_id`
Expected: FAIL — `client_id` is not a valid field.

- [ ] **Step 3: Add the field to `ChatRequest`**

Edit `ntrp/server/schemas.py` `ChatRequest` (lines 13-19):

```python
class ChatRequest(BaseModel):
    message: str = Field("", max_length=100_000)
    images: list[ImageBlock] = Field(default_factory=list)
    context: list[dict] = Field(default_factory=list)
    skip_approvals: bool = False
    session_id: str | None = None
    client_id: str | None = None
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_chat_inject.py -v -k client_id`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ntrp/server/schemas.py tests/test_chat_inject.py
git commit -m "feat(api): accept client_id on chat message requests"
```

---

## Task 3: POST `/chat/message` stamps `client_id` onto the inject-queue entry

**Files:**
- Modify: `ntrp/server/app.py:213-232`
- Test: `tests/test_chat_inject.py`

- [ ] **Step 1: Write the failing test (uses fastapi.testclient and a stub run)**

Append to `tests/test_chat_inject.py`:

```python
import pytest
from fastapi.testclient import TestClient

from ntrp.server.app import app
from ntrp.server.runtime import Runtime
from ntrp.server.state import RunRegistry, RunStatus


@pytest.fixture
def client_with_active_run(monkeypatch):
    """Spin up the FastAPI app with a stub Runtime that already has an active run."""
    runtime = Runtime.__new__(Runtime)
    runtime.run_registry = RunRegistry()
    runtime.config = type("C", (), {"has_any_model": True, "api_key_hash": None})()
    run = runtime.run_registry.create_run("sess-1")
    run.status = RunStatus.RUNNING

    monkeypatch.setattr("ntrp.server.app.get_runtime", lambda: runtime)

    with TestClient(app) as c:
        yield c, run


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
```

Note: if the FastAPI auth middleware blocks unauth'd requests, set `runtime.config.api_key_hash = None` and the existing middleware should bypass. If the test fails at auth, add `headers={"Authorization": "Bearer test"}` and adjust the stub.

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/test_chat_inject.py::test_post_chat_message_stores_client_id_when_run_active -v`
Expected: FAIL — `client_id` not in entry (the current code only writes `role` and `content`).

- [ ] **Step 3: Modify the inject-queue append to include `client_id`**

Edit `ntrp/server/app.py` lines 226-232:

```python
    # If agent is already running, queue message for safe injection
    active_run = runtime.run_registry.get_active_run(session_id)
    if active_run:
        entry: dict = {
            "role": Role.USER,
            "content": build_user_content(request.message, images, context),
        }
        if request.client_id:
            entry["client_id"] = request.client_id
        active_run.inject_queue.append(entry)
        return {"run_id": active_run.run_id, "session_id": session_id}
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `uv run pytest tests/test_chat_inject.py::test_post_chat_message_stores_client_id_when_run_active -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ntrp/server/app.py tests/test_chat_inject.py
git commit -m "feat(api): stamp client_id onto inject queue entries"
```

---

## Task 4: Drain emits `message_ingested` and strips `client_id` before LLM

**Files:**
- Modify: `ntrp/services/chat.py:316-323`
- Test: `tests/test_chat_inject.py`

- [ ] **Step 1: Write the failing test (uses an in-memory SessionBus)**

Append to `tests/test_chat_inject.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_chat_inject.py -v -k drain`
Expected: FAIL — `_build_get_pending` does not exist.

- [ ] **Step 3: Extract `_build_get_pending` into a module-level helper**

Edit `ntrp/services/chat.py`. After the imports and helpers (around line 35, before `_logger`), keep imports as-is. Add this helper above `run_chat` (insert after `_drain_backgrounded`, before `async def run_chat`):

```python
def _build_get_pending(pending: list[dict], bus: SessionBus, run: RunState):
    """Closure that drains pending injects and emits message_ingested per client entry."""

    async def _get_pending() -> list[dict]:
        if not pending:
            return []
        batch = list(pending)
        pending.clear()
        for entry in batch:
            client_id = entry.pop("client_id", None)
            if client_id:
                await bus.emit(
                    MessageIngestedEvent(client_id=client_id, run_id=run.run_id)
                )
        return batch

    return _get_pending
```

Add `MessageIngestedEvent` to the imports at the top of the file:

```python
from ntrp.events.sse import (
    MessageIngestedEvent,
    RunBackgroundedEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextEvent,
    ThinkingEvent,
)
```

Replace the inline closure inside `run_chat` (lines 316-323) with a call to the helper:

```python
        pending_messages: list[dict] = []
        run.inject_queue = pending_messages
        run.status = RunStatus.RUNNING
        run_finished = False

        agent.hooks.get_pending_messages = _build_get_pending(pending_messages, bus, run)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_chat_inject.py -v -k drain`
Expected: PASS (both `test_drain_emits_ingested_for_entries_with_client_id` and `test_drain_no_events_when_queue_empty`).

- [ ] **Step 5: Run the existing agent tests to confirm no regression**

Run: `uv run pytest tests/test_agent.py tests/test_agent_lib.py -v`
Expected: PASS (existing inject hook tests should still pass — they don't use `client_id` and the behavior for non-client entries is unchanged).

- [ ] **Step 6: Commit**

```bash
git add ntrp/services/chat.py tests/test_chat_inject.py
git commit -m "feat(chat): emit message_ingested SSE event when draining inject queue"
```

---

## Task 5: New `DELETE /chat/inject/{client_id}` endpoint

**Files:**
- Modify: `ntrp/server/app.py` (add new route below `/chat/message`)
- Test: `tests/test_chat_inject.py`

- [ ] **Step 1: Write the three failing tests (200, 409, 404)**

Append to `tests/test_chat_inject.py`:

```python
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


def test_delete_inject_returns_404_when_no_active_run(monkeypatch):
    runtime = Runtime.__new__(Runtime)
    runtime.run_registry = RunRegistry()
    runtime.config = type("C", (), {"has_any_model": True, "api_key_hash": None})()
    monkeypatch.setattr("ntrp.server.app.get_runtime", lambda: runtime)

    with TestClient(app) as c:
        resp = c.delete("/chat/inject/cid-x?session_id=sess-none")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_chat_inject.py -v -k delete_inject`
Expected: FAIL — endpoint does not exist (404 from FastAPI for all three).

- [ ] **Step 3: Add the endpoint**

In `ntrp/server/app.py`, after the `/chat/message` POST handler (around line 246), add:

```python
@app.delete("/chat/inject/{client_id}")
async def cancel_inject(
    client_id: str,
    session_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    active_run = runtime.run_registry.get_active_run(session_id)
    if active_run is None:
        raise HTTPException(status_code=404, detail="No active run")

    for i, entry in enumerate(active_run.inject_queue):
        if entry.get("client_id") == client_id:
            active_run.inject_queue.pop(i)
            return {"status": "cancelled", "client_id": client_id}

    raise HTTPException(status_code=409, detail="Already ingested")
```

- [ ] **Step 4: Run the tests to confirm all three pass**

Run: `uv run pytest tests/test_chat_inject.py -v -k delete_inject`
Expected: PASS (all three tests).

- [ ] **Step 5: Run the full inject test file to confirm no regression**

Run: `uv run pytest tests/test_chat_inject.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ntrp/server/app.py tests/test_chat_inject.py
git commit -m "feat(api): add DELETE /chat/inject/{client_id} for queue cancel"
```

---

## Task 6: Frontend types — add `MessageIngestedEvent` to `ServerEvent` union

**Files:**
- Modify: `ntrp-ui/src/types.ts`

- [ ] **Step 1: Add the event interface**

In `ntrp-ui/src/types.ts`, add after `TextMessageEndEvent` (around line 120):

```ts
export interface MessageIngestedEvent {
  type: "message_ingested";
  client_id: string;
  run_id: string;
}
```

- [ ] **Step 2: Add it to the `ServerEvent` union**

Edit the union (around line 123):

```ts
export type ServerEvent =
  | ThinkingEvent
  | TextEvent
  | TextDeltaEvent
  | TextMessageStartEvent
  | TextMessageEndEvent
  | ToolCallEvent
  | ToolResultEvent
  | ApprovalNeededEvent
  | QuestionEvent
  | BackgroundTaskEvent
  | RunStartedEvent
  | RunFinishedEvent
  | RunErrorEvent
  | RunCancelledEvent
  | RunBackgroundedEvent
  | MessageIngestedEvent;
```

- [ ] **Step 3: Verify the type compiles**

Run: `cd ntrp-ui && bun run build`
Expected: Build succeeds. Note: the SSE handler in `useStreaming.ts` has a `default` arm with `_exhaustive: never = event` — this will surface a type error here because `MessageIngestedEvent` is not yet handled. That's expected; Task 9 will add the handler. To unblock the build for now, **skip this step** and verify in Task 9.

- [ ] **Step 4: Commit**

```bash
git add ntrp-ui/src/types.ts
git commit -m "feat(types): add MessageIngestedEvent to server event union"
```

---

## Task 7: Frontend API — `client_id` on send, new `cancelQueuedMessage`

**Files:**
- Modify: `ntrp-ui/src/api/chat.ts:85-99`

- [ ] **Step 1: Add `client_id` parameter to `sendChatMessage`**

Replace `sendChatMessage` (lines 85-99) with:

```ts
export async function sendChatMessage(
  message: string,
  sessionId: string,
  config: Config,
  skipApprovals: boolean = false,
  images?: ImageBlock[],
  clientId?: string,
): Promise<{ run_id: string; session_id: string }> {
  const body: Record<string, unknown> = {
    message,
    session_id: sessionId,
    skip_approvals: skipApprovals,
  };
  if (images?.length) body.images = images;
  if (clientId) body.client_id = clientId;
  return api.post(`${config.serverUrl}/chat/message`, body) as Promise<{ run_id: string; session_id: string }>;
}
```

- [ ] **Step 2: Add `cancelQueuedMessage` after `sendChatMessage`**

Append to `ntrp-ui/src/api/chat.ts`:

```ts
export async function cancelQueuedMessage(
  clientId: string,
  sessionId: string,
  config: Config,
): Promise<"cancelled" | "already_ingested" | "no_run"> {
  const url = `${config.serverUrl}/chat/inject/${encodeURIComponent(clientId)}?session_id=${encodeURIComponent(sessionId)}`;
  const headers: Record<string, string> = {};
  const apiKey = getApiKey();
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const res = await fetch(url, { method: "DELETE", headers });
  if (res.status === 200) return "cancelled";
  if (res.status === 409) return "already_ingested";
  if (res.status === 404) return "no_run";
  throw new Error(`cancelQueuedMessage: unexpected status ${res.status}`);
}
```

(`api.post` doesn't expose DELETE; raw fetch is the simplest fit. Reuse `getApiKey` already imported at the top of the file.)

- [ ] **Step 3: Re-export from `client.ts` if it barrels these helpers**

Check `ntrp-ui/src/api/client.ts`:

Run: `grep -n "sendChatMessage\|cancelRun" ntrp-ui/src/api/client.ts`

If `sendChatMessage` is re-exported, also re-export `cancelQueuedMessage`. Edit accordingly:

```ts
export { sendChatMessage, cancelQueuedMessage, /* …existing… */ } from "./chat.js";
```

- [ ] **Step 4: Commit**

```bash
git add ntrp-ui/src/api/chat.ts ntrp-ui/src/api/client.ts
git commit -m "feat(api): client_id on sendChatMessage; new cancelQueuedMessage"
```

---

## Task 8: Per-session `queuedMessages` in the streaming store

**Files:**
- Modify: `ntrp-ui/src/stores/streamingStore.ts`

- [ ] **Step 1: Define the `QueuedMessage` type**

At the top of `ntrp-ui/src/stores/streamingStore.ts`, after the existing exports (around line 25), add:

```ts
export type QueuedMessageStatus = "pending" | "cancelling" | "sent" | "failed";

export interface QueuedMessage {
  clientId: string;
  text: string;
  images?: { media_type: string; data: string }[];
  status: QueuedMessageStatus;
  enqueuedAt: number;
}
```

- [ ] **Step 2: Add the field to `SessionStreamState`**

Add to the `SessionStreamState` interface (around line 33), after `backgroundTasks`:

```ts
  queuedMessages: QueuedMessage[];
```

- [ ] **Step 3: Initialize it in `createSessionState`**

Add to the returned object in `createSessionState()` (around line 75):

```ts
    queuedMessages: [],
```

- [ ] **Step 4: Preserve in `replaceSession`**

The `replaceSession` helper at line 114 spreads the session and reconstructs `Map`/`Set` instances. `queuedMessages` is a plain array; the existing spread will copy the reference. To keep the array immutable across mutations, change the relevant line:

```ts
      sessions.set(id, {
        ...s,
        tools: { ...s.tools, descriptions: new Map(s.tools.descriptions), startTimes: new Map(s.tools.startTimes) },
        alwaysAllowedTools: new Set(s.alwaysAllowedTools),
        autoApprovedIds: new Set(s.autoApprovedIds),
        backgroundTasks: new Map(s.backgroundTasks),
        queuedMessages: [...s.queuedMessages],
      });
```

- [ ] **Step 5: Verify build**

Run: `cd ntrp-ui && bun run build`
Expected: Build succeeds (no consumers of `queuedMessages` yet, but the type adds cleanly).

- [ ] **Step 6: Commit**

```bash
git add ntrp-ui/src/stores/streamingStore.ts
git commit -m "feat(store): per-session queuedMessages array"
```

---

## Task 9: `useStreaming` — enqueue / cancel / SSE handler / drop optimistic append

**Files:**
- Modify: `ntrp-ui/src/hooks/useStreaming.ts`

This task is the biggest single change. Five small steps inside one task.

- [ ] **Step 1: Import `cancelQueuedMessage` and `QueuedMessage`**

Edit imports near the top:

```ts
import { connectEvents, sendChatMessage, submitToolResult, cancelRun, backgroundRun, getBackgroundTasks, revertSession, cancelQueuedMessage, type ImageBlock } from "../api/client.js";
import { createStreamingStore, type SessionNotification, type SessionStreamState, type MessageInput, type QueuedMessage } from "../stores/streamingStore.js";
```

- [ ] **Step 2: Add the `message_ingested` handler arm**

In the `mutateSession` switch statement inside `handleEventRef.current` (around line 110), add a new case **before** the `default:` arm:

```ts
        case "message_ingested": {
          const idx = s.queuedMessages.findIndex((q) => q.clientId === event.client_id);
          if (idx === -1) break; // already removed (cancel raced); idempotent
          const queued = s.queuedMessages[idx];
          s.queuedMessages = [
            ...s.queuedMessages.slice(0, idx),
            ...s.queuedMessages.slice(idx + 1),
          ];
          addMessageToSession(s, {
            role: "user",
            content: queued.text,
            imageCount: queued.images?.length ?? 0,
            images: queued.images,
          });
          break;
        }
```

The `default: { const _exhaustive: never = event; ... }` arm now compiles because `MessageIngestedEvent` is handled.

- [ ] **Step 3: Replace `sendMessage`'s streaming branch with no-op (callers should enqueue instead)**

`sendMessage` at line 399 currently has two branches: `s.isStreaming` (optimistic-append + post) and idle. The new contract is "this is the idle path only." Replace the function with:

```ts
  const sendMessage = useCallback(async (message: string, images?: ImageBlock[]) => {
    const id = store.getState().viewedId;
    if (!id) return;

    const imageCount = images?.length || 0;

    mutateSession(id, (s) => {
      addMessageToSession(s, { role: "user", content: message, imageCount, images });
      s.isStreaming = true;
      s.pendingText = "";
      s.status = Status.THINKING;
      s.toolChain = [];
      s.tools.descriptions.clear();
      s.tools.startTimes.clear();
      s.tools.sequence = 0;
    });

    try {
      const res = await sendChatMessage(message, id, configRef.current, skipApprovalsRef.current, images);
      mutateSession(id, (s) => { s.runId = res.run_id; });
    } catch (error) {
      mutateSession(id, (s) => {
        addMessageToSession(s, { role: "error", content: `${error}` });
        s.isStreaming = false;
        s.status = Status.IDLE;
      });
    }
  }, [store, getSession, addMessageToSession, mutateSession]);
```

- [ ] **Step 4: Add `enqueueMessage` and `cancelQueued` actions**

After `sendMessage`, add:

```ts
  const enqueueMessage = useCallback(async (message: string, images?: ImageBlock[]) => {
    const id = store.getState().viewedId;
    if (!id) return;
    const clientId = `cid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    mutateSession(id, (s) => {
      s.queuedMessages = [
        ...s.queuedMessages,
        {
          clientId,
          text: message,
          images,
          status: "pending",
          enqueuedAt: Date.now(),
        },
      ];
    });

    try {
      await sendChatMessage(message, id, configRef.current, skipApprovalsRef.current, images, clientId);
    } catch (error) {
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.map((q) =>
          q.clientId === clientId ? { ...q, status: "failed" } : q
        );
      });
    }
  }, [store, mutateSession]);

  const cancelQueued = useCallback(async (clientId: string) => {
    const id = store.getState().viewedId;
    if (!id) return;

    // Optimistic mark
    mutateSession(id, (s) => {
      s.queuedMessages = s.queuedMessages.map((q) =>
        q.clientId === clientId ? { ...q, status: "cancelling" } : q
      );
    });

    let result: "cancelled" | "already_ingested" | "no_run";
    try {
      result = await cancelQueuedMessage(clientId, id, configRef.current);
    } catch {
      // Revert on network error
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.map((q) =>
          q.clientId === clientId ? { ...q, status: "pending" } : q
        );
      });
      return;
    }

    if (result === "cancelled" || result === "no_run") {
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.filter((q) => q.clientId !== clientId);
      });
    } else {
      // already_ingested: leave the bubble; the imminent message_ingested
      // event will move it into the conversation. If the event already arrived,
      // the bubble is already gone and this is a no-op.
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.map((q) =>
          q.clientId === clientId ? { ...q, status: "sent" } : q
        );
      });
    }
  }, [store, mutateSession]);
```

- [ ] **Step 5: End-of-run reconciliation in terminal-event arms**

In the existing `run_finished`, `run_error`, `run_cancelled`, `run_backgrounded` arms inside `mutateSession`, after the existing logic but inside the same arm, queue messages that were never ingested are still in `s.queuedMessages` with status `pending`. They were already POSTed to the backend and *might* have made it into the just-finished run, or might have orphaned. The simplest correct rule: leave them as-is for now — they'll either be visible queued bubbles the user can manually cancel, or the user types something else and they auto-flush. Add the more aggressive auto-resend later if desired. **No code change here**, just confirm this design choice is what we want before moving on.

For the MVP, also add this at the start of each terminal arm to clean up status `cancelling` items that the server-side delete may have raced through:

In `run_finished`, `run_error`, `run_cancelled`, `run_backgrounded` arms, add at the bottom of each:

```ts
          // Reset orphaned cancelling items so the user can retry cancel
          s.queuedMessages = s.queuedMessages.map((q) =>
            q.status === "cancelling" ? { ...q, status: "pending" } : q
          );
```

- [ ] **Step 6: Expose `enqueueMessage`, `cancelQueued`, and `queuedMessages` from the hook return**

At the bottom of `useStreaming`, derive `queuedMessages`:

```ts
  const queuedMessages = viewed?.queuedMessages ?? [];
```

Add to the returned object:

```ts
  return {
    messages,
    isStreaming,
    status,
    toolChain,
    pendingApproval,
    usage,
    backgroundTaskCount,
    backgroundTasks,
    pendingText,
    sessionStates,
    queuedMessages,
    addMessage,
    clearMessages,
    sendMessage,
    enqueueMessage,
    cancelQueued,
    setStatus: setStatusPublic,
    handleApproval,
    cancel,
    background,
    revert,
    revertAndResend,
    switchToSession,
    deleteSessionState,
  };
```

- [ ] **Step 7: Build to confirm types are sound**

Run: `cd ntrp-ui && bun run build`
Expected: Build succeeds. The `default: { _exhaustive: never = event }` arm compiles because every `ServerEvent` variant is handled.

- [ ] **Step 8: Commit**

```bash
git add ntrp-ui/src/hooks/useStreaming.ts
git commit -m "feat(streaming): enqueueMessage and cancelQueued actions; handle message_ingested"
```

---

## Task 10: New `QueuedMessages.tsx` component

**Files:**
- Create: `ntrp-ui/src/components/chat/QueuedMessages.tsx`

- [ ] **Step 1: Inspect existing chat-message component for visual conventions**

Run: `ls ntrp-ui/src/components/chat/messages/`
Then read one user-message-style file to mimic colors/padding (e.g., the user bubble component, whatever it's named). Note the colors source: `import { useColors } from "../../theme/useColors.js"` or similar — match the existing import path used by `InputArea.tsx`.

```bash
grep -n "import.*colors" ntrp-ui/src/components/chat/InputArea.tsx | head -3
```

- [ ] **Step 2: Write the component**

Create `ntrp-ui/src/components/chat/QueuedMessages.tsx`:

```tsx
import type { QueuedMessage } from "../../stores/streamingStore.js";
import { useAccentColor } from "../../hooks/useAccentColor.js";
// Adjust the colors import to match the project; use the same path InputArea.tsx uses.
import { colors } from "../../theme/colors.js";

interface QueuedMessagesProps {
  items: QueuedMessage[];
  onCancel: (clientId: string) => void;
}

export function QueuedMessages({ items, onCancel }: QueuedMessagesProps) {
  if (items.length === 0) return null;

  return (
    <box flexShrink={0} flexDirection="column" marginBottom={1}>
      {items.map((q) => (
        <box
          key={q.clientId}
          flexDirection="row"
          paddingLeft={2}
          paddingRight={2}
        >
          <box flexGrow={1} overflow="hidden">
            <text>
              <span fg={colors.text.muted}>queued · </span>
              <span fg={colors.text.muted}>{truncate(q.text, 80)}</span>
            </text>
          </box>
          <box flexShrink={0} marginLeft={1}>
            <text>
              <span
                fg={q.status === "cancelling" ? colors.text.disabled : colors.status.warning}
                onMouseDown={() => q.status === "pending" && onCancel(q.clientId)}
              >
                {q.status === "cancelling" ? "…" : "×"}
              </span>
            </text>
          </box>
        </box>
      ))}
    </box>
  );
}

function truncate(s: string, n: number) {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
```

Notes:
- The exact `colors` import path and syntax need to match the project conventions discovered in Step 1. If `useColors` is a hook, switch to that pattern.
- OpenTUI's mouse / key handlers may differ from the above. If `onMouseDown` isn't supported, expose cancel via a keyboard binding (e.g. `Backspace` while focused) or via parent-managed key handling instead. Defer to whatever pattern other clickable elements in `ntrp-ui` already use — search for `onMouseDown` or equivalent in the codebase first.

- [ ] **Step 3: Build to verify**

Run: `cd ntrp-ui && bun run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ntrp-ui/src/components/chat/QueuedMessages.tsx
git commit -m "feat(ui): QueuedMessages component for queued bubbles below input"
```

---

## Task 11: Wire `QueuedMessages` into `App.tsx`; route submit through `enqueueMessage`

**Files:**
- Modify: `ntrp-ui/src/App.tsx`
- Modify: `ntrp-ui/src/components/chat/InputArea.tsx`

- [ ] **Step 1: Pull `enqueueMessage`, `cancelQueued`, `queuedMessages` from the hook**

In `App.tsx`, find the destructure of `useStreaming` (around line 114):

Find the existing line that destructures `sendMessage` and friends, and extend it to include the new fields:

```tsx
const {
  // ...existing fields...
  sendMessage,
  enqueueMessage,
  cancelQueued,
  queuedMessages,
  // ...remaining fields...
} = useStreaming({ /* …existing args… */ });
```

(Edit in place rather than rewriting the whole destructure.)

- [ ] **Step 2: Replace `useMessageQueue` usage**

Remove this line (around line 17 and line 135):

```tsx
useMessageQueue,
// ...
const { messageQueue, enqueue, clearQueue } = useMessageQueue(isStreaming, pendingApproval, sendMessage);
```

Delete the `useMessageQueue` import at the top of the file.

- [ ] **Step 3: Update `handleSubmit`**

Replace the body (lines 231-257):

```tsx
const handleSubmit = useCallback(
  async (value: string, images?: ImageBlock[]) => {
    const trimmed = value.trim();
    if (!trimmed && !images?.length) return;

    if (trimmed.startsWith("/")) {
      if (pendingApproval || isStreaming) return;
      const handled = await handleCommand(trimmed);
      if (handled) return;
      const cmdName = trimmed.slice(1).split(" ")[0];
      if (skills.some(s => s.name === cmdName)) {
        sendMessage(trimmed, images);
      } else {
        addMessage({ role: "error", content: `Unknown command: ${trimmed}` });
      }
      return;
    }

    if (isStreaming || pendingApproval) {
      enqueueMessage(trimmed, images);
      return;
    }

    sendMessage(trimmed, images);
  },
  [pendingApproval, isStreaming, sendMessage, handleCommand, addMessage, skills, enqueueMessage]
);
```

- [ ] **Step 4: Render `QueuedMessages` above the `InputArea`**

In the JSX, find the input area block (around line 463-487). Before `<InputArea>`, add:

```tsx
<box flexShrink={0}>
  <QueuedMessages items={queuedMessages} onCancel={cancelQueued} />
</box>
<box flexShrink={0}>
  <InputArea
    /* …existing props… */
  />
</box>
```

Add the import at the top of the file:

```tsx
import { QueuedMessages } from "./components/chat/QueuedMessages.js";
```

- [ ] **Step 5: Drop the `queueCount={messageQueue.length}` prop**

Remove this prop from the `<InputArea>` invocation (it's now subsumed by the new component).

- [ ] **Step 6: Drop the `queueCount` badge inside `InputArea.tsx`**

In `ntrp-ui/src/components/chat/InputArea.tsx`:

- Remove the `queueCount` prop from the interface (line 32).
- Remove `queueCount = 0,` from the props destructure (line 55).
- Remove the badge block (lines 341-343).

- [ ] **Step 7: Build**

Run: `cd ntrp-ui && bun run build`
Expected: Build succeeds. Any leftover `messageQueue` references will surface as type errors — clean them up.

- [ ] **Step 8: Delete `useMessageQueue.ts`**

```bash
git rm ntrp-ui/src/hooks/useMessageQueue.ts
```

If `hooks/index.ts` re-exports it, remove that line too.

Run: `cd ntrp-ui && bun run build`
Expected: Build still succeeds.

- [ ] **Step 9: Commit**

```bash
git add ntrp-ui/src/App.tsx ntrp-ui/src/components/chat/InputArea.tsx ntrp-ui/src/hooks/index.ts
git rm ntrp-ui/src/hooks/useMessageQueue.ts
git commit -m "feat(ui): route mid-run submits through enqueueMessage; show QueuedMessages"
```

---

## Task 12: Manual end-to-end verification

This is a manual checkout — there are no end-to-end frontend tests in the repo. Run through these scenarios.

**Files:** none (verification only)

- [ ] **Step 1: Start backend and frontend**

```bash
# Terminal 1
uv run ntrp-server serve

# Terminal 2
cd ntrp-ui && bun run dev
```

- [ ] **Step 2: Scenario A — single queued message, ingested**

1. Send a prompt that triggers a tool call (e.g. "list my todos").
2. While the tool is running, type "also count them" and press Enter.
3. Observe: a queued bubble appears below the input with `queued · also count them × `.
4. When the tool returns, the queued bubble disappears and the message appears as a normal user turn in the conversation.
5. Verify: the agent's next LLM call factors it in.

Expected: ✅ Queued bubble visible during tool, transitions cleanly to user turn at boundary.

- [ ] **Step 3: Scenario B — three messages queued together**

1. Trigger a long tool call.
2. Type three short messages in quick succession (A, B, C).
3. Three queued bubbles render below the input.
4. When the tool returns, all three move into the conversation as separate user turns, in order.

Expected: ✅ Three bubbles, three user turns, in order.

- [ ] **Step 4: Scenario C — cancel before ingestion**

1. Trigger a long tool call.
2. Type a message, click the × on the queued bubble.
3. Bubble disappears.
4. When the tool returns, no orphaned message appears in the conversation.

Expected: ✅ Cancel removes the bubble cleanly; nothing leaks.

- [ ] **Step 5: Scenario D — cancel races drain (409)**

1. Trigger a tool call that completes quickly (e.g. cheap tool).
2. Type a message and quickly click × to attempt to cancel.
3. If the tool finishes first → bubble moves into conversation as user turn.
4. If cancel arrives first → bubble vanishes.

Expected: ✅ No double-rendering or stuck bubble in either case.

- [ ] **Step 6: Scenario E — orphans across run end**

1. Trigger a one-step run that finishes quickly.
2. Type a message during the brief stream window.
3. Run finishes before the message is drained (race) OR drains it normally.

Expected: ✅ Either the bubble gets ingested cleanly or, if orphaned, it remains visible as a queued bubble the user can cancel manually. (Auto-resend of orphans is a deferred enhancement.)

- [ ] **Step 7: Commit a brief verification note**

If anything failed, fix it in a follow-up commit. If all passed, no commit needed.

---

## Self-Review Performed

This plan was self-reviewed for: spec coverage (every spec section maps to one or more tasks); placeholder scan (no TBDs except deliberate "deferred" notes that match the spec's Open Questions); type consistency (`client_id` is the field name across Python/TS, `clientId` in TS is the camelCase variant inside the store); scope (one feature, single PR-able plan).

Known weak points:
- Task 10 (`QueuedMessages.tsx`) hand-waves the exact OpenTUI mouse/key API. The task instructs the implementer to pattern-match existing clickable elements in the codebase. If no clickable pattern exists, fallback is keyboard-only cancel via a focus model — that's a reasonable extension within the same task.
- End-of-run reconciliation is intentionally minimal in v1 (Task 9 Step 5 leaves orphans visible). This matches the spec's "user can manually cancel" framing without adding auto-resend complexity. Auto-resend is in Open Questions, deferred.
- **Spec deviation:** the spec proposed introducing an `InjectedMessage` dataclass to carry `client_id`. The plan keeps `inject_queue` as `list[dict]` and adds an optional `"client_id"` key, popped before forwarding to the LLM. Functionally equivalent, less code change, and consistent with how background-task results are already injected as plain dicts.
- The `client_with_active_run` fixture in Task 3 stubs `Runtime` directly via monkeypatch. If the `AuthMiddleware` rejects unauthenticated requests, switch to `app.dependency_overrides[get_runtime] = lambda: runtime` and add `headers={"Authorization": "Bearer test"}` if the middleware requires it. Either approach is fine — the implementer should pick what works after running the first failing test.
