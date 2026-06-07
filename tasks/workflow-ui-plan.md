# Workflow FleetView UI — plan

Decisions (user): **inline preview in ActivityTrace → click opens overlay detail**;
metrics = **finish-rollup + live elapsed**.

## Architecture

A workflow tool call already shows as ONE activity item in the trace (keyed by its
tool_id). That becomes the **inline preview row**. A NEW client `workflows` domain
consumes workflow-tagged events to build the **overlay**: workflow → phases → agent
rows (tokens/tools/time). The two never fight because the preview keys on the
workflow tool_id and the overlay keys on each subagent's unique task_id.

## Backend (apps/server)

### sse.py
- EventType: add `WORKFLOW_STARTED`, `WORKFLOW_PHASE`, `WORKFLOW_FINISHED`.
- New events:
  - `WorkflowStartedEvent(session_id, run_id, workflow_id, parent_tool_call_id, name, description)`
  - `WorkflowPhaseEvent(session_id, run_id, workflow_id, phase, index, total?)`
  - `WorkflowFinishedEvent(session_id, run_id, workflow_id, status, summary, agent_count)`
- Task* events: add optional `workflow_id: str | None = None`, `phase: str | None = None`.
- `TaskFinishedEvent`: add `usage: dict | None`, `cost: float | None`, `tool_count: int | None`,
  `elapsed_ms: int | None` (finish rollup).
- `TokenUsageEvent`: add optional `task_id: str | None = None` (attribution; used later).

### spawner.py  (FIXES bug #1)
- Add optional `lifecycle_id: str | None = None` and `workflow_id`/`phase` params to `spawn_child`.
- `lifecycle_task_id = lifecycle_id or parent_id or f"task-{uuid4()...}"` — when Orchestra
  passes a UNIQUE lifecycle_id per spawn, concurrent siblings no longer collide on
  `run.subagents[...]` (cancel + finish_subagent stop popping each other), while
  `parent_tool_call_id` stays = workflow tool_id for grouping. ADDITIVE: default None
  preserves research/background behavior exactly (no userspace break).
- Thread `workflow_id`/`phase` into the TaskStarted/Progress/Finished emits.
- On TaskFinished: include `usage`/`cost` (already have SpawnResult.usage/cost),
  `elapsed_ms` (now - started_at), `tool_count` (export RunBudget.tool_calls via Result).

### orchestra/engine.py  (FIXES bug #7)
- `_spawn`: generate a unique `lifecycle_id = f"{parent_id}:{uuid4().hex[:8]}"` per spawn;
  pass `workflow_id` + resolved phase.
- Default `tools`: when None, pass full toolset MINUS spawn tools {workflow, research,
  background} (least privilege; kills nested fan-out amplification).
- `phase(title)`: emit `WorkflowPhaseEvent` via `ctx.io.emit` (now real, not just a setter).
- Carry `workflow_id` + `name` (set by workflow.py) on the Orchestra.

### tools/workflow.py
- Generate `workflow_id`; emit `WorkflowStartedEvent` before `wf.run`, `WorkflowFinishedEvent`
  after (in finally). Pass `workflow_id` + `wf.meta.name` into `Orchestra.for_ctx`.

## Client (apps/desktop)

### api.ts
- Add the 3 workflow event types + new Task*/TokenUsage fields to ServerEvent union.

### store/workflow-domain.ts (NEW, reducer pattern like background-agent-domain.ts)
- `WorkflowState { workflowId, name, status, startedAt, phases: Record<phase, PhaseState> }`
- `PhaseState { phase, index, agents: Record<taskId, AgentRunView + metrics> }`
- reducers: reduceWorkflowStarted/Phase/Finished + reduceWorkflowTaskEvent (tag by workflow_id).
- keyed `workflowsBySessionId[sessionId][workflowId]`.

### chat-stream.ts / transcript-projection.ts
- Route workflow_* events + workflow-tagged task events into the workflow domain
  (in addition to existing activity projection, which keeps the single preview row).

### components
- `WorkflowPreviewRow.tsx` — compact inline row in ActivityTrace for a workflow tool item
  (name · N phases · M agents · status · elapsed) + "open" affordance. Mirrors automations preview.
- `WorkflowPanel.tsx` — overlay (reuse .surface-panel + modal pattern): header
  (name, elapsed, agent count, Σ tokens) → collapsible phase groups (StatusDot + Badge) →
  agent rows reusing AgentRunRow/AgentRunContent + a tokens/tools/time meta lane.
- Reuse: AgentRunView, StatusDot, Badge, IconButton, motion tokens (MOTION.*, EASE_EMPHASIZED).

## Phasing (verify each)
1. Backend events + spawner threading + #1/#7 + orchestra/workflow emits → pytest. ← THIS TURN
2. Client domain + api types → unit/contract test.
3. Components (preview + overlay) → verify in running app (Vite + Claude Preview), check
   live elapsed tick + finish rollup; screenshots Before/After.

## Notes
- feedback_design_verify_pixels: components verified in the running app, not code-read.
- Don't break userspace: spawner change is additive (lifecycle_id default None).
