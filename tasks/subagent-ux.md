# Subagent UX/UI revamp

Goal: make a sub-agent a first-class, legible object everywhere. One visual
language across inline chat card, right-sidebar agents hub, and inspector.
Right sidebar is the home/navigation for child-agent sessions (user's call).

## Diagnosis (before)
- Inline: a backgrounded agent collapses to `Worked → Executed · 1 call →
  Background executed` — cryptic, two disclosures deep, no name/status/result.
  Prose leaks raw id: "Kicked off in background: agent-e15f2ad744".
- Right "Active" panel shows running-only → empty ~95% of the time; finished
  agents vanish; no way to review/re-open.
- Left sidebar filters out `session_type==="agent"` entirely → child sessions
  are orphaned (openable once via the card, then unreachable; no breadcrumb).
- Inspector renders `agentType · childRunId.slice(0,12)` — id-centric.

## Design
- Unified `AgentRunView` + `AgentRunCard`/`AgentRunRow` primitive (name · type ·
  status dot · elapsed · result preview · open · stop).
- Right sidebar = agents hub: running + recently-finished (with result preview);
  when inside a child agent session, show `← parent` breadcrumb + sibling agents
  (parent id = childSessionId.split("::")[0]).
- Inline distinct mini-card replacing the cryptic agent trace row.
- Kill ids: server spawn ack drops raw id (spawner.py:909); inspector name-first.

## Build order
- [x] Read all 4 surfaces + contracts (types, api, spawner)
- [x] P1 (me): shared primitive — lib/agentRun.ts, components/StatusDot.tsx,
      components/agents/AgentRunCard.tsx
- [x] P2 (workflow, parallel disjoint files): inline card (ActivityTrace),
      sidebar hub built by me, inspector (ToolViewer), server ack
      (spawner.py), helper unit tests
- [x] P3 (me): tsc clean + bun test 355/0 + visual verify in preview.
      Fixed live: card clip (height auto), inline name (displayName→task→target),
      detached inline result suppressed, sidebar name from child session,
      0s elapsed suppressed for terminal. Breadcrumb+siblings verified.
- [x] P4 (workflow): adversarial review (4 dimensions, per-finding verify) →
      14 confirmed. Fixed: nested-agent parent resolution (parent_session_id +
      lastIndexOf), useChildAgentResults rewrite (reset on nav, mark-on-success,
      inflight guard, no cancelled-loss), sub_agent→"Agent" label, roster keeps
      the current agent past the cap, active-row name ink, removed dead
      toolCount/tokens/cost + agentRunStatusMeta. Deferred: [7] role=button+inner
      button (matches existing SessionRow convention), [8] glyph DRY refactor.

## Verified in live app
- Inline mini-card: task name, Research·detached, no ack-leak, not clipped.
- Right hub: running+recent with real result previews, child-session titles.
- Child session → "← parent" breadcrumb + "Agents in this run" siblings,
  current highlighted; breadcrumb returns to parent. Round-trip works.

## Known followups (non-blocking)
- Server spawner registers command="Agent" default (label updated async);
  desktop now titles from child session name instead. Could fix at source.
- Background agents lack real start/end timestamps client-side → elapsed
  hidden for terminal. Could thread created_at/ended_at through the snapshot.
- useChildAgentResults fetches each terminal agent's result once; a result
  written slightly after first fetch won't retry until remount.

## Notes
- Branch: subagent-ux-revamp. No commit until reviewed (user pref).
- Verify polish against running pixels (Claude Preview @ 5180), not code-read.
