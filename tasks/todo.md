# Channel-aware automations — fan-out, post-mode, lineage

## Why this spec

Loops shipped (commit `f0dea946`) but stay a special case: only loops can target a session, only loops have iteration semantics, and there's no way for one automation to spawn N children pointing at N different threads. The user's canonical use case — *"hourly watcher finds new offers; for each, spawn a per-offer monitor that posts updates into its own channel every 4h"* — needs three things the current model can't express:

1. A session as a generic **output thread** (any automation can target it, not just `kind="loop"`)
2. A **post-mode** run that fires fresh and drops a status message into the thread (vs the current loop's re-enter-with-full-history mode)
3. **Lineage** so a parent automation can list, cancel, or dedup-against its children

Research across Letta, LangGraph, Trigger.dev, Inngest, and Mastra converges on the same shape, with one important correction to codex's earlier proposal: **don't make `execution_mode` a 3-way enum**. LangGraph proves it's derived from `thread_id` (present?) + `read_history` (bool). Two fields, four behaviors, no enum branching.

## Final data model

```python
@dataclass
class Automation:
    # existing fields stay
    ...

    # Output target — replaces target_session_id (industry-standard name).
    # When set, this automation's run posts into the thread.
    thread_id: Optional[str]

    # Only meaningful when thread_id is set.
    # True  → agent re-enters with the thread's prior history (current loop)
    # False → agent runs fresh each fire; final output is posted as an
    #         assistant message into the thread (new — channel monitor)
    read_history: bool = False

    # Explicit lineage. Letta, Trigger.dev, Inngest all treat this as a
    # first-class field, not derived from naming convention.
    parent_automation_id: Optional[str]

    # Existing loop-only fields now apply to any automation:
    # max_iterations, max_age_days, stop_when, iteration_count
```

Behavior truth table:

| `thread_id` | `read_history` | Behavior | Replaces |
|---|---|---|---|
| `None` | — | Standalone — runs `AUTOMATION_PROMPT`, no chat context | current `kind="automation"` |
| set | `True` | Iteration — agent sees prior thread history | current `kind="loop"` |
| set | `False` | **Post** — fresh run, output posted to thread | NEW |

`kind` stays in phase 1 (no regression risk). Removed in phase 2.

## Session model

Sessions stay one type at the DB layer. Add a marker so the UI can style channel-origin sessions:

```python
@dataclass
class SessionState:
    ...
    session_type: Literal["chat", "channel"] = "chat"
    # When session was created by an automation rather than by the user:
    origin_automation_id: Optional[str]
```

UI: same sidebar list, channels get a distinct icon (lucide `Radio` / `Hash` / `Antenna`). No separate collapsible section.

## Open call resolution

1. **Post-mode message role:** `assistant`. The automation produces output; the agent IS the producer. Mark it with `source: "automation:<id>"` so the UI can render a subtle indicator.
2. **Channel UX:** same sidebar as chats, different icon. Filtering / grouping can come later if it gets noisy.
3. **Idempotency scopes:** all three from day one. `run` (default), `attempt`, `global`. Scope set per fan-out call; `global` is the load-bearing one for "watcher finds same item again, don't re-spawn."

## Phase 1 — build

### 1. Schema migration (v5)

- [ ] Add columns: `thread_id`, `read_history`, `parent_automation_id`, `idempotency_key`, `idempotency_scope` to `scheduled_tasks`
- [ ] Add `session_type`, `origin_automation_id` to sessions table
- [ ] Indexes: `(parent_automation_id)`, `(thread_id, kind)`, `(idempotency_scope, idempotency_key)`
- [ ] Backfill: existing `kind="loop"` rows → `thread_id = target_session_id`, `read_history = True`. Existing `target_session_id` column kept as alias during the transition.

### 2. Scheduler dispatch

- [ ] `_run_loop` renamed to `_run_session_bound`. Branches on `read_history`:
  - `True` → existing iteration path (`submit_chat_message`, agent sees history)
  - `False` → new post path (run agent fresh with `AUTOMATION_PROMPT`-style wrapper; on success, post `result` as `role="assistant"` message into `thread_id` via session_service)
- [ ] Both paths still honor `max_iterations`, `max_age_days`, `stop_when`
- [ ] `loop_fire_gate` keeps deferring while the target session has an active user run (applies to both modes)

### 3. Idempotency

- [ ] `IdempotencyScope` enum: `run` | `attempt` | `global`
- [ ] `try_claim_idempotency(scope, key, automation_id) -> bool` in `AutomationStore`
- [ ] Scheduler skips a fire when claim fails (returns False without consuming a tick)
- [ ] `global` scope: stores `(key)` → permanent. `run` scope: `(key, parent_run_id)` → expires with the parent. `attempt` scope: `(key, parent_run_id, attempt_n)` → per-attempt.

### 4. Lineage tools

- [ ] `parent_automation_id` is set on creation, indexed
- [ ] `AutomationService.list_children(parent_id)` and `cancel_children(parent_id)`
- [ ] On parent deletion: cascade-cancel children (or detach — decide based on UX testing)

### 5. New tools (agent-facing)

- [ ] `create_session(name: str, session_type: Literal["chat", "channel"] = "chat") -> SessionState`. Returns the new session id. Channel-type sessions are auto-marked with `origin_automation_id` from `ctx.run` (or null if user-typed).
- [ ] Extend `create_automation` with: `thread_id`, `read_history`, `parent_automation_id`, `idempotency_scope`, `idempotency_key`. All optional; presence triggers the corresponding behavior.
- [ ] Inngest-style naming: the spawn operation is **send** (fire-and-forget). No `invoke` (await-and-collect) variant in phase 1, but the name reserves the design space.

### 6. Bounded history for iteration mode

- [ ] When `read_history=True`, the agent receives the last N thread messages, not the full history. N is config (default ~50). Beyond N, summarization runs out-of-band as a separate concern.
- [ ] No clever pruning. Hard window. Letta/Mastra both do this; trying to be smart causes more bugs than bloat.

### 7. UI

- [ ] Sidebar: channel-type sessions get a `Radio`/`Hash` icon, same list
- [ ] Channel session header shows: `Origin: <parent_automation_name>` link + "Cancel all" button if there are sibling channel automations
- [ ] Automation list: hide `kind="loop"` rows (already in [routers/automation.py](apps/server/ntrp/server/routers/automation.py) post-merge of upcoming filter); post-mode automations stay visible since they're "real" automations
- [ ] Automation detail view: show thread_id link + "open thread" button

### 8. Tests

- [ ] Schema migration round-trip (v4 → v5, fields populated correctly)
- [ ] Scheduler: post-mode dispatches → fresh run → result message posted to thread
- [ ] Scheduler: iteration-mode unchanged (existing loop tests still pass)
- [ ] Idempotency: `global` claim succeeds first time, fails on duplicate; `run`-scope expires with parent
- [ ] Lineage: list_children returns correct rows; cancel_children flips enabled=False
- [ ] `create_session` tool creates a channel session with origin stamped
- [ ] `create_automation` with `parent_automation_id` + `idempotency_key` end-to-end (watcher spawns 3 children, re-fires, spawns 0)

## Phase 2 — cleanup (separate PR, after phase 1 ships)

- [ ] Drop `kind` field; all branches now read from `thread_id` / `read_history`
- [ ] Drop `loop_prompt` and `target_session_id` aliases; `description` carries the prompt for both modes
- [ ] Letta-style `last_processed_message_id` cursor per `(automation_id, thread_id)` for iteration-mode efficiency
- [ ] Out-of-band thread summarization (only when iteration-mode windows are routinely hitting cap)

## Out of scope (don't slip these in)

- `invoke` (call-and-wait spawn) — `send` is enough for now
- Cron expressions — keep the existing `every` / `at` / `days` schema
- Cross-automation messaging beyond parent_automation_id (Letta `send_message_to_agent` is rich but premature)
- Tool-rules solver (Letta) for sequencing
- Channel access controls / sharing

## Decisions still soft (revisit during build)

- Post-mode failure handling: retry, dead-letter, or silent skip with `last_result` carrying the error?
- `read_history` window N: 50 is a guess. Instrument and tune.
- Cascade-cancel children on parent delete vs detach: depends on whether channels are meant to outlive their producer.
