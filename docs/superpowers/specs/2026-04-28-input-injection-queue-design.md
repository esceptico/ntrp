# Input Injection Queue — Design Spec

**Date:** 2026-04-28
**Status:** Approved (brainstorming complete; awaits implementation plan)
**Owner:** Tim

## Problem

When the user submits a chat message while the agent is mid-run (streaming an LLM response or executing a tool call), the frontend POSTs the message immediately and renders it inside the conversation. Visually it looks like the user interrupted the assistant — but on the backend the agent loop continues, and the message is silently appended to `run.inject_queue` and only consumed at the next loop iteration. The result: the UI lies about timing, and there is no affordance to cancel or even see that a message is "waiting."

We want **same-run continuation semantics**, modeled on Claude Code: queued messages get injected at the tool-result boundary inside the running agent loop, and the UI clearly distinguishes "queued" from "delivered."

## Goals

1. A queued message is visually distinct from a sent message, lives below the input area, and never appears mid-stream inside the conversation.
2. The user can cancel a queued message before it is ingested.
3. Multiple messages queued during one busy window are delivered as separate user turns at the next agent-loop boundary.
4. The architecture preserves the existing backend `inject_queue` and `_drain_pending` machinery — only the entry shape and SSE emission grow.

## Non-Goals

- Editing a queued message in place (deferred — same data model, can be added later).
- Mid-stream interrupt / abort of the current LLM generation (separate feature).
- Reordering or priority tiers (Claude Code's `'now' | 'next' | 'later'` model is unnecessary here).
- Batching multiple queued messages into a single user turn (we use separate turns).

## Architecture

The queue is split across the client/server boundary:

- **Backend `inject_queue`** is the source of truth for "messages waiting to be ingested by this run." It is consumed by `_drain_pending` at the top of each agent-loop iteration — i.e. after tool results have returned and before the next LLM call.
- **Frontend queue** is a UI projection: a list of messages the user has submitted that have not yet been confirmed-ingested. Each item carries the same `client_id` as its backend counterpart, and is reconciled via SSE.

We do **not** move the queue to a single side. A pure-frontend queue (Claude-Code-style) cannot reach a tool-result boundary in time — by the time an SSE event reached the browser and the browser POSTed, the next LLM call would already be in flight. A pure-backend queue cannot offer cancel/edit affordances cleanly. The two-sided model with `client_id` correlation is the simplest fit for ntrp's process split.

### Lifecycle of one queued message

```
[user types during stream]
       │
       ▼
Frontend enqueues locally (status=pending, client_id=uuid),
renders queued bubble in QueuedMessages with × cancel button
       │
       ▼
Frontend immediately POSTs /chat/message {client_id, text}
       │
       ▼
Backend appends entry to run.inject_queue (with client_id)
       │
       ▼
Agent loop reaches next iteration boundary (tool results returned, before next LLM call)
       │
       ▼
_drain_pending consumes the entry → emits SSE message_ingested {client_id}
       │
       ▼
Frontend matches client_id, moves bubble out of QueuedMessages
into the conversation as a normal user turn (status=sent)
```

### Cancel path

```
[user clicks × on a queued bubble]
       │
       ▼
Frontend marks item status=cancelling, sends DELETE /chat/inject/{client_id}
       │
       ▼
Backend looks up the active run and scans inject_queue:
  - found and not yet drained → remove, return 200
  - already drained → return 409 (race lost)
       │
       ▼
Frontend on 200: drop the bubble entirely
Frontend on 409: the message was already drained. Two sub-cases by event ordering:
  - if the message_ingested event already arrived (bubble has already moved
    into the conversation): no-op
  - if the bubble is still in the queue (waiting for ingestion event): mark
    status=sent and let the imminent message_ingested event do the move
```

## Components

### Frontend (`ntrp-ui/`)

| File | Change |
|---|---|
| `hooks/useMessageQueue.ts` | Extend the queue model: each item carries `{ client_id: string, text: string, status: 'pending' \| 'cancelling' \| 'sent' \| 'failed' }`. Drop the auto-drain effect — items live in queue until SSE ingestion or explicit cancel. The approval-pending case collapses into the same path: enqueue when `isStreaming \|\| pendingApproval`, otherwise send directly. |
| `App.tsx` (`handleSubmit`) | Replace branching on `pendingApproval` with the unified `isBusy = isStreaming \|\| pendingApproval` predicate. When busy → enqueue + POST with `client_id`. When idle → POST directly (no queue). |
| `App.tsx` (SSE listener) | Handle new `message_ingested` event: find item by `client_id`, mark `sent`, move into conversation messages, drop from queue render. |
| `components/chat/QueuedMessages.tsx` *(new)* | Stack of queued bubbles below `InputArea`. Each bubble shows truncated text + × button. Shows nothing when queue is empty. Visual treatment: muted/faded relative to live conversation bubbles. |
| `components/chat/InputArea.tsx` | Remove the inline "N queued" badge — `QueuedMessages` is the single source of truth for queue UI. |
| `api/chat.ts` (or equivalent) | Add `cancelQueuedMessage(client_id) -> Promise<{ status: 200 \| 409 }>` calling `DELETE /chat/inject/{client_id}`. |

### Backend (`ntrp/`)

| File | Change |
|---|---|
| `server/app.py` `POST /chat/message` | Accept optional `client_id: str` in the request body. When the path that appends to `active_run.inject_queue` fires, include `client_id` on the entry. |
| `server/app.py` *new* `DELETE /chat/inject/{client_id}` | Look up the active run for the session. Scan `run.inject_queue` for an entry with matching `client_id`. If found, remove and return 200. If not found, return 409. If no active run, return 404. |
| `services/chat.py` `_get_pending` closure | When draining `pending_messages`, for each consumed entry that has a `client_id`, emit an SSE event `message_ingested { client_id, run_id }` on the run's event bus. |
| `events/sse.py` | Add `message_ingested` to the event-type union. |
| `agent/agent.py` | Unchanged. `_drain_pending` continues to call the hook at the top of each iteration. |

### Inject queue entry shape

Today: a plain `dict[str, Any]` with role/content keys.
After: a small dataclass.

```python
@dataclass
class InjectedMessage:
    client_id: str | None  # None for server-internal injections (e.g. background task results)
    content: str
    # ... existing fields preserved
```

`client_id` is optional because the backend already injects internally-generated messages (background task results — see `services/chat.py:325-328`) that have no client counterpart. Those continue to flow without emitting `message_ingested` events.

## Data Flow Examples

### Example 1: single queued message, ingested

1. Run is mid-tool-call.
2. User submits "also check the calendar." Frontend creates `client_id=abc123`, enqueues, renders bubble, POSTs.
3. Tool call returns. Agent loop iterates.
4. `_drain_pending` consumes the message, emits `message_ingested {client_id: abc123}`.
5. Frontend receives event, moves the bubble into the conversation as a user turn.
6. Next LLM call sees the new turn in context.

### Example 2: three messages queued, drained together

1. Run is mid-tool-call.
2. User submits A, then B, then C in quick succession. Three bubbles render in `QueuedMessages`.
3. Tool call returns. `_drain_pending` consumes all three in order, emits three `message_ingested` events.
4. Frontend receives them sequentially, moves bubbles A, B, C into the conversation as three separate user turns.
5. Next LLM call sees all three.

### Example 3: cancel races drain

1. User submits "ignore that," realizes it was wrong, clicks ×.
2. Frontend marks `status=cancelling`, sends DELETE.
3. Server already drained the message 30ms earlier → 409.
4. Frontend marks `status=sent`. Within the next event loop tick, the `message_ingested` event arrives and the bubble moves into the conversation. The user sees the message land — accurate, slightly delayed.

### Example 4: end-of-run reconciliation

1. User submits a message late in a run.
2. Run completes (final assistant turn, no more tool calls). SSE stream closes.
3. If `message_ingested` arrived first → bubble already in conversation. Done.
4. If SSE closed first and the bubble is still `pending` → frontend treats it as orphaned and re-POSTs as a fresh user message (starts a new run). This preserves user intent.

## Error Handling

- **POST /chat/message fails with `client_id`**: frontend marks bubble `status=failed`, shows a retry button. (Existing failure UX for non-queued messages applies.)
- **DELETE /chat/inject/{client_id} 404 (no active run)**: the run ended; the message either ingested or was never queued. Frontend treats the same as 409.
- **SSE disconnects mid-run**: existing reconnect logic restores the stream. Any `message_ingested` events emitted during the gap are replayed (existing SSE-replay behavior covers this; if not, the end-of-run reconciliation path catches it).
- **Backend crash mid-drain**: `inject_queue` is in-memory and lost. The next user action triggers the orphaned-bubble re-POST path.

## Testing

- **Backend unit:** `_get_pending` emits one `message_ingested` per drained entry with `client_id`; entries without `client_id` are silent.
- **Backend unit:** `DELETE /chat/inject/{client_id}` returns 200 on hit, 409 on miss, 404 on no active run; concurrent drain + delete returns 409 for the loser.
- **Backend integration:** queued message arrives mid-tool-call, gets ingested at next iteration, agent's next LLM call includes it.
- **Frontend hook:** `useMessageQueue` transitions: enqueue→pending, on `message_ingested`→sent+removed, on cancel-200→removed, on cancel-409→sent.
- **Frontend integration / manual:** type during stream, see queued bubble, see it move; click × on queued, see it disappear; queue 3 in a row, all three land as separate user turns.

## Open Questions

None blocking. Deferred:

- Editable queued bubbles (UI affordance C from brainstorming).
- Priority tiers (`'now'` to abort current generation à la Claude Code).
- Server-side persistence of the queue (would unlock multi-tab consistency, currently out of scope).
