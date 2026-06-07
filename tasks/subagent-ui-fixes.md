# Subagent UI fixes — plan

Three reported issues (see screenshots): (1) incoherent agent cards in the tool-call
stack, (2) no live updates inside subagent sessions (static until reload), (3) subagents
look stuck. Root causes diagnosed + adversarially verified. User decisions:
① unify as clean rows · ② poll-refresh viewed child (fast/low-risk) · ③ harden backend now.

## ① Coherent agent rows in the activity stack (design)
Root: `ItemButton` (trace/ActivityTrace.tsx) renders 3 visual tiers in one list —
bordered `AgentRunCard` (session-backed), inline `AgentButton` (non-session agents),
bare mono tool rows. Stacked → dissonant.

- [ ] Generalize `AgentButton` into one clean agent ROW for ALL agents (session-backed
      + not): Bot glyph (status tone + stop-on-hover) · name · faint inline progress/
      result · `StatusDot` · elapsed · open-child-session affordance. Single-line, peer
      of tool rows.
- [ ] Remove the `isSessionBackedAgent → AgentRunCard` branch in `ItemButton`; route all
      agents through the unified row. KEEP `isSessionBackedAgent` (gates tree-recursion
      leaf-ness in buildRollingList/buildStaticTree — not styling).
- [ ] Drop card special-casing in `ActivityTail` (`isAgentCardItem`, `card ? my-1`,
      static-mode `hasCard`/auto-height) → uniform row rhythm.
- [ ] Delete now-unused `AgentRunCard` from agents/AgentRunCard.tsx (keep `AgentRunRow`).
- [ ] Verify in running app (Vite + Claude Preview): reads as rows; running/done/failed;
      long titles truncate; stop-on-hover; click opens child session.

## ② Live updates in subagent sessions — PROPER FIX (poll band-aid REJECTED by user)
User: "subagent must look and work the same as default agent, no differences." The 2s
poll special-cased child sessions → second-class. Replaced with the real fix: a FULL
subagent streams to its OWN session bus exactly like a normal run, so the normal
`useEvents(childSessionId)` path is live with zero client special-casing.

- [x] chat.py: `run_chat(ctx, bus, buses)`; build `_child_io_factory` (IOBridge bound to
      `buses.get_or_create(childSessionId).emit`, reusing the run's approval plumbing +
      run_id; returns ChildSession{io, aclose}). Set `ctx.run.child_io_factory`.
- [x] tools/core/context.py: `ChildIOParams`, `ChildSession`, `ChildIOFactory`,
      `RunContext.child_io_factory`.
- [x] spawner.py: for `child_io` (FULL+factory) route the child's full stream to the child
      bus, re-based to depth 0 / no parent (keeps recursion guard intact — agent.py
      untouched); parent gets only lifecycle. SHARED unchanged (nests to parent).
- [x] state.py: `mark_session_active`/`clear_session_active` so leaving a running child
      mid-run doesn't let remove_if_idle evict its bus. `aclose` drains/evicts on finish.
- [x] DELETE the poll band-aid: useViewedAgentSessionRefresh + appendLatestForSession +
      wiring (App.tsx, actions/index.ts, history.ts).
- [ ] Verify in running app after :6877 restart: open a running subagent → live token/
      tool/reasoning stream, no reload; navigate away + back mid-run → resumes.

## ③ Backend "stuck" hardening — high-confidence slice now
- [ ] FIX 1 (real): guarantee `child_session_id` propagation. spawner.py: add
      `has_child_session = child_state.session_id != calling_ctx.session_id`; advertise
      child_session_id on THAT predicate (not `child_session_persisted`) at every Task*/
      BackgroundTask event + SpawnResult site. SHARED → None (correct).
- [ ] FIX 1 tests (test_spawn_salvage.py): FULL advertises id even if provisioning
      fails; SHARED advertises None.
- [ ] FIX 2b (real, cheap): startup reconcile — sweep orphaned child-agent SESSIONS with
      `agent_status='running'` → 'interrupted' (mirror mark_interrupted_background_agent_runs),
      so a crash/dropped-terminal never leaves a forever-running card after reload.

### Reservation — confirm before building (do NOT build blindly)
- [ ] FIX 2a/3 (recursive subtree listing + per-subagent terminal overlay + cascading
      poll): targets partly SELF-HEALING edges — a dropped terminal event triggers
      stream_reset → history reload, and the parent transcript's spawn-tool result already
      resolves the card. Heavier surface (new store CTEs, endpoint param, client overlay).
      Recommend deferring unless nested-grandchild stuckness is actually observed.

## Verification
- [ ] Desktop: typecheck/build; live preview for ① and ②.
- [ ] Backend: `uv run pytest` for spawner + affected tests.

## Review (round 2 — ② replaced with the proper streaming fix)

Verification after the streaming fix: backend `uv run pytest` 1173 pass (+2 child-bus
tests: FULL streams to its own bus at depth 0 / parent gets lifecycle only; SHARED never
calls the factory), ruff clean; desktop `bun test` 362 pass, `tsc` clean.

Known limitation: a DETACHED background subagent viewed AFTER its parent turn completes
has a narrow bus-eviction edge (the active-session marker points at the parent run, which
has ended). The FOREGROUND case (the reported research-agent screenshots) is fully solid —
the parent run is active for the whole child lifetime.

Backend goes live only after a `:6877` restart (server runs without --reload).

## Review (round 1 — superseded ② poll)

Shipped (not committed — awaiting user review):
- ① ActivityTrace: removed the bordered `AgentRunCard`; all agents now render via one
  unified `AgentRow` (glyph + name + faint inline progress/result + StatusDot + elapsed +
  open-session affordance), a visual peer of the tool rows. Dropped card height
  special-casing in `ActivityTail`. Renamed `agents/AgentRunCard.tsx` → `AgentRunRow.tsx`
  (only `AgentRunRow` remained, used by the sidebar).
- ② `appendLatestForSession` + `useViewedAgentSessionRefresh` (mounted in App.tsx): the
  viewed child session appends newly-persisted steps every 2s; tail signature makes an
  idle poll a no-op (no re-render). Append, not replace → scroll stays anchored.
- ③ FIX 1: `has_child_session` predicate decouples child_session_id advertisement from
  persistence (SHARED→None, FULL→always). FIX 2b: `mark_interrupted_agent_sessions`
  startup sweep flips orphaned running agent sessions → interrupted.

Verification:
- Desktop: `tsc --noEmit` clean; `bun test` 362 pass / 0 fail (incl. 3 agent-row render
  tests covering the new AgentRow: stop control, generated-name-not-prompt, open-session).
- Backend: `uv run pytest` 1171 pass (added 2 spawn tests for FIX 1, 1 store test for 2b).
- NOT done: pixel-level polish of the new row in the running app — the Electron renderer
  needs the IPC bridge + backend + a session with subagents, which a headless Vite preview
  can't faithfully provide. Eyeball in the running instance (Vite HMR shows it live).

Deferred (reservation, NOT built — needs go-ahead): ③ FIX 2a/3 recursive-subtree listing
+ per-subagent terminal overlay + cascading poll. Targets partly self-healing edges
(dropped terminal → stream_reset → history reload resolves the card). Heavier surface.
