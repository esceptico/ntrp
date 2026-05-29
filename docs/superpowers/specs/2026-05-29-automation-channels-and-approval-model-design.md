# Automation Channels + Auto-Approve Approval Model

**Date:** 2026-05-29
**Status:** Approved design, pending implementation plan

## Problem

Three related defects and one missing capability around automations:

1. **`notify()` dead-ends in headless automations even with `writable=true`.** `notify` carries a user `tool_overrides` entry of `ASK`. In `request_approval` ([context.py:360-364](../../../apps/server/ntrp/tools/core/context.py)) an `ASK` override beats `skip_approvals`, so the call falls through to the "No UI connected" rejection. The fact that it's an automation (no human to ask) is never considered.

2. **Plain automation output is silently dropped.** Non-session-bound automations run through `_run_agent` ([scheduler.py:507-528](../../../apps/server/ntrp/automation/scheduler.py)) and return their text to the scheduler as a run record. There is no channel binding, so generated output (e.g. a nudge) never lands anywhere the user reads.

3. **`writable` conflates two concepts:** "can use write tools" (tool availability) and "skip approval for write tools." There is no way to express "auto-approve safe actions, still gate destructive ones" — but in a headless run there is no one to approve anyway, so the practical need is a clean two-state.

4. **No per-automation channel.** Automations have no durable, contextual home for their activity. We want every automation to own a channel showing its full activity (tool calls included) that the user can also chat in.

## Goals

- `notify()` (and any `ASK`-tagged tool) fires in a headless auto-approve automation, while still prompting in interactive chat.
- Every automation owns a bound channel; all of its activity — tool calls, results, assistant text — is visible there, live.
- The user can chat inside an automation's channel.
- Rename the approval control to reflect what it does.

## Non-Goals

- Per-tool auto-approve allowlists (explicitly rejected in favor of a two-state model).
- Sidebar grouping of channels by automation (v1 uses a per-card link only).
- External channel adapters (Slack/iMessage) — out of scope.

---

## Part A — Approval model (`writable` → `auto_approve`)

### Rename

Rename the field `writable` → `auto_approve` across its full surface:

- **Model:** `Automation.writable` ([models.py:23](../../../apps/server/ntrp/automation/models.py))
- **Store:** column `writable` ([store.py:130](../../../apps/server/ntrp/automation/store.py)), `_COLUMNS`, all `_SQL_*` strings, `_row_to_automation` mapping, `set_writable`, `update_metadata`, `save`, `save_with_claim`. Requires a schema migration (see Part D).
- **Service:** `toggle_writable` → `toggle_auto_approve`, `create`/`update` param, `_build_metadata_changes`, `create_loop` (hardcoded `writable=True` → `auto_approve=True`).
- **Runner:** `RunRequest.writable` → `auto_approve` ([runner.py:48](../../../apps/server/ntrp/operator/runner.py)); still used to filter tools (`get_tools(read_only=not auto_approve)`, [runner.py:100](../../../apps/server/ntrp/operator/runner.py)).
- **Scheduler/app:** `skip_approvals=automation.writable` → `automation.auto_approve` ([scheduler.py:518](../../../apps/server/ntrp/automation/scheduler.py), [app.py:114,145](../../../apps/server/ntrp/server/app.py)).
- **Desktop:** the "Writable" toggle ([AutomationEditor.tsx:312-325](../../../apps/desktop/src/components/automations/AutomationEditor.tsx)) → "Auto-Approve", plus `FormState`, API payload types.

### Semantics (two-state, single boolean)

- `auto_approve = True` → full write toolset **and** skip approvals (autonomous).
- `auto_approve = False` → read-only tools, no approvals needed (observe-only).

The dual role is retained deliberately: a write tool that requires approval cannot run headless (no one to approve), so separating availability from approval adds no usable state.

### The ASK fix

`ASK` means "ask the human." Make that conditional on a human being reachable. In `ToolExecution.request_approval` ([context.py:360-364](../../../apps/server/ntrp/tools/core/context.py)):

```python
ui_connected = self.ctx.io.emit is not None and self.ctx.io.pending_approvals is not None
override = self.ctx.registry.get_override(self.tool_name)
ask_must_block = override == ToolOverrideDecision.ASK and ui_connected
if not ask_must_block and (self.ctx.skip_approvals or self.tool_name in self.ctx.auto_approve):
    return None
```

- Interactive chat (UI connected) + `notify→ASK` → still prompts.
- Headless auto-approve automation + `notify→ASK` → bypasses and fires.
- `DENY` is unaffected — it blocks upstream at [registry.py:49](../../../apps/server/ntrp/tools/core/registry.py) before middleware, regardless of approval state.

This resolves defects #1 and #3 and does **not** require removing the user's `notify→ASK` override.

---

## Part B — Channel per automation

### Provisioning

At automation-creation time, auto-provision a channel and bind the automation to it:

1. `SessionService.create(session_type="channel", origin_automation_id=<task_id>)` → returns a channel session.
2. Persist the empty session.
3. Set the new automation's `thread_id` to that channel's `session_id`.

Applies to **all** automations, including one-shots — the one-shot's output is exactly what the user wants to read afterward.

### Execution: in-session (chat pipeline)

All auto-channel automations execute **inside their channel session** via the chat/iteration path (`_dispatch_iteration` → `submit_chat_message`, [app.py:104-116](../../../apps/server/ntrp/server/app.py)), not the headless post pipeline. The scheduler selects the iteration dispatcher when `read_history=True` ([scheduler.py:552](../../../apps/server/ntrp/automation/scheduler.py)), so auto-channel automations are created with `read_history=True` (this becomes the default rather than an opt-in). Consequences:

- The full turn — assistant text **plus** `tool_call`/`tool_result` messages — persists into the channel.
- Live SSE updates render activity in real time.
- The channel is a normal session, so the user can send their own messages into it; the next automation fire sees them (history is read in-session).
- `skip_approvals` flows from `auto_approve` exactly as today ([app.py:114](../../../apps/server/ntrp/server/app.py)).

This makes every agent automation session-bound. The post pipeline (`_dispatch_post`) and `_run_agent` become vestigial for agent automations (internal `_run_handler` automations are unaffected) — flag for cleanup after verifying no remaining callers.

### Concurrency

Existing protections carry over: `_loop_can_fire` defers a tick when the channel session has an active user run, and per-session write locks serialize writes. So a user mid-conversation in a channel naturally defers the automation tick.

### Context growth

In-session execution accumulates history. This is handled by the app's existing context compaction; it is the primary thing to monitor.

---

## Part C — UI

- Rename the **Writable** toggle → **Auto-Approve** (label + `aria-label`) in [AutomationEditor.tsx:312-325](../../../apps/desktop/src/components/automations/AutomationEditor.tsx).
- Surface the channel: add a link from each automation card → its bound channel, resolved via `origin_automation_id`. Channels already render in the sidebar with a radio icon; the Chat header already shows the origin automation. No new sidebar grouping in v1.
- The channel composer already works (it is a normal session) — no new chat affordance needed beyond ensuring automation channels are openable.

---

## Part D — Migration & rollout

- **Schema migration:** add `auto_approve` column, backfill `auto_approve = writable`, drop `writable`.
- **Channel backfill:** for each existing automation without a `thread_id`, create a channel and bind it, so existing automations gain a channel on upgrade.
- `create_loop` hardcoded `writable=True` → `auto_approve=True`.
- Keep the `notify→ASK` override as-is; the Part A fix makes it correct in both contexts.

---

## Testing

- **Approval:** `ASK` override bypassed when headless + `skip_approvals`; `ASK` still blocks when UI connected; `DENY` blocks in both contexts; `notify` fires in an `auto_approve` automation.
- **Channel provisioning:** creating an automation creates a `session_type="channel"` session with `origin_automation_id` set and binds `thread_id`.
- **In-session execution:** an automation fire persists `tool_call`/`tool_result` messages into the channel, not just final text.
- **Chat interleaving:** a user message into a channel and an automation fire serialize correctly (lock / `_loop_can_fire`).
- **Migration:** `auto_approve` backfilled from `writable`; existing automations get channels.
