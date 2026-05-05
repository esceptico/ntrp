# ntrp desktop roadmap

Living punch list. Tick items as they ship; replace this file when it goes stale.

Status syntax: `[ ]` = todo · `[~]` = shipped, not yet manually tested · `[x]` = shipped + verified.

Out of scope for now (per user, 2026-05-05): notifications panel, tools/skills browser.

---

## Server gaps with no UI

These are server endpoints that already work; just need a desktop surface.

- [~] **MCP server manager** — `/mcp/servers` list, add, enable/disable, tool whitelist, OAuth flow. _Implemented in `Settings → MCP servers` tab; not yet manually tested end-to-end._
- [ ] **Background tasks panel** — `/chat/background-tasks`, cancel, view results.
- [ ] **Pending messages queue** — `DELETE /chat/inject/{client_id}` exists; `MessageIngestedEvent` already streams. Show queued user messages while a run is in flight, with cancel-before-ingest. Currently the user can submit while a run is running but has no visibility into whether/when the message lands.
- [ ] **Memory observability tab** — `/stats`, `/memory/audit`, `/memory/events`, `/memory/access/events`, `/memory/recall/inspect`.
- [ ] **Learning/candidate review** — `/memory/learning/*`, `/memory/facts/kind-review`. Surface LLM-proposed memory edits before they apply.
- [ ] **Memory injection-policy preview** — `/memory/injection-policy/preview`. Show exactly what gets stuffed into the prompt for a given query.
- [ ] **Run history view** — `/chat/runs/status`. Per-run metadata, timing, replay.
- [ ] **Provider discovery** — `/providers`, `/tool-providers`. Connect new models/integrations.
- [ ] **Directives editor** — `/directives` PUT. Edit the system-level directives file from the app.

## Ideas worth stealing from other desktop AI apps

- [x] ~~**`@`-mention typed context picker**~~ — built v1 (memory-only); reverted. Use case wasn't clear and the UX didn't land. Park it; revisit if a concrete need shows up. (Cody.)
- [ ] **Live token meter + auto "summarize-and-fork" banner** above the composer. Leverages existing compaction events; fixes the "how full is context?" blindspot. (Zed.)
- [ ] **Tool/permission profiles per chat** — Write / Ask / Minimal scopes the agent's tools+model in one click. (Zed.)
- [ ] **Slash commands as parameterized templates** — `SKILL.md`-style with `{{var}}` arg prompts. (Cursor Skills, Warp Workflows.)
- [ ] **Automations with `{{var}}` placeholders + quick-fire dialog** — turns scheduled prompts into reusable templates that can also be fired ad-hoc. (Warp Workflows.)
- [ ] **Background agents that produce reviewable diffs** — long-running entropy-reduction tasks (inbox triage, vault cleanup) run async and present a changeset to review. (Cursor Background Agents.)
- [ ] **Global OS hotkey + screenshot-to-chat / "work with apps"** — Electron `globalShortcut`, capture from anywhere on the OS, promote captures to memory. (ChatGPT, Witsy, Pieces.)
- [ ] **Voice capture → structured note** — voice in, fact-extraction-ready transcript out. (Granola, Cleft, Bee.)
- [ ] **Editable profile timeline view** — chronological "what changed about me" across facts/observations/dreams with inline edit. (Bee.)
- [ ] **Persistent project containers** — `Project = (instructions + files + memory scope)` shared across sessions. (Claude Projects, LibreChat Presets.)
- [ ] **Live/interactive artifacts** — chat-embedded UIs that re-render with fresh data. (Claude Live Artifacts, MCP Apps.)

## Ranked picks (next-to-do, biased to ntrp's "personal entropy reduction" framing)

1. ~~**`@`-mention context picker**~~ — built and reverted; parked.
2. [ ] **Live token meter + auto-fork banner** — cheapest win; landed in ~an hour using existing compaction signal.
3. [~] **MCP server manager** — without it, MCP is power-user-only. _Shipped, untested._
4. [ ] **Memory observability tab** (audit + events + injection preview) — trust-builder for the memory work.
5. [ ] **Global hotkey + screenshot-to-chat** — biggest "real personal app" lift; needs Electron `globalShortcut` + native capture.
6. [ ] **Automation `{{var}}` placeholders + ad-hoc fire** — small change, big leverage on existing automations.
7. [ ] **Background tasks panel** — closes the async loop server-side wiring already enables.
8. [ ] **Editable profile timeline** — a 6th memory tab; another angle on the data we already store.

## Already shipped (reference)

- Sessions: list, search, archive, restore, permanent delete, right-click menu, manual compact.
- Compaction indicator (server emits start/finish; client shows spinner + "compacted N → M" toast).
- Automations: list (Active/Templates tabs), prompt-first editor, run, view-last-run, scheduling chip.
- Memory: Facts, Observations, Profile, Dreams, Merges (supersession candidates).
- Activity trace: per-parent rolling sub-tail; agent-kind tools render as agent cards instead of raw args.
- Tool inspector: agent variant with task / markdown result / recursive Activity tree.
- Edit + branch flows: stable `client_id` end-to-end (server stamps user messages on submit; provider preprocessor strips before API call).
- PageModal shell + lib/{hooks,format,agent} de-duped from across modals; MemoryModal split into `memory/{Facts,Observations,Profile,Dreams,Merges}Pane.tsx`.
