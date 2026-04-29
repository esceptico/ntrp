# Backend event flow cleanup

This notebook tracks the backend architecture cleanup that replaces the old in-process channel fan-out with explicit, durable protocols.

## Design rules

- Use direct calls when the producer and consumer are in the same runtime transaction path.
- Use a durable outbox when work crosses reliability boundaries or must survive process failure.
- Keep SSE/session streaming separate from backend domain workflows.
- Keep each background protocol owned by its data model, not by a generic process-wide bus.
- Make operational state queryable before adding manual repair controls.

## Completed stages

- Stage 1: durable outbox for `run.completed` events.
- Stage 2: persistent chat extraction cursor/state.
- Stage 3: run completions moved off the old channel bus.
- Stage 4: memory indexing routed through the outbox.
- Stage 5: monitor events routed directly to the scheduler.
- Stage 6: obsolete generic channel bus removed.
- Stage 7: outbox operational visibility.
- Stage 8: authenticated outbox repair controls.
  - Replay dead-letter rows only by explicit event IDs.
  - Prune completed outbox rows only with an age cutoff and bounded limit.
- Stage 9: documented remaining backend protocols.
  - SSE stream bus is documented as transient UI transport.
  - Outbox, scheduler triggers, and monitor events are documented as separate owned protocols.
- Stage 10: stabilized outbox API response contracts.
  - `/health`, `/outbox/status`, `/outbox/dead/replay`, and `/outbox/completed` now have explicit response schemas.
  - OpenAPI exposes stable outbox endpoint response models for future clients.
- Stage 11: guarded persistence ownership boundaries.
  - Backend protocol docs now map tables to their owner stores.
  - Architecture test prevents production modules from directly referencing owned protocol tables.
- Stage 12: automatic completed outbox retention.
  - Outbox worker prunes completed rows older than 30 days.
  - Pruning is interval-gated and bounded, and never touches pending/running/dead rows.
- Stage 13: scheduler status visibility.
  - Scheduler exposes runtime liveness without leaking table access.
  - AutomationStore owns persisted task, queue, count, and chat extraction status summaries.
- Stage 14: agent injection queue ownership.
  - `RunState` now owns queue, cancel, and drain operations for same-run user input injection.
  - Chat API and chat service no longer scan or clear the raw queue list directly.
  - The backend protocol docs now describe the injection queue as part of the session SSE/run lifecycle, not as a generic bus.
- Stage 15: active run lifecycle visibility.
  - `RunRegistry` exposes a content-free status snapshot for retained and active runs.
  - `/chat/runs/status` reports active run lifecycle flags, injection counts, and background task session counts without leaking messages.
  - Run observability now follows the same pattern as outbox and scheduler status endpoints.
- Stage 16: runtime outbox extraction.
  - `RuntimeOutbox` now owns the outbox worker, handler registration, health/status, replay, and pruning controls.
  - `Runtime` still composes the subsystem but no longer embeds durable event handler logic directly.
  - This is the first runtime decomposition step; the composition root is thinner without changing endpoint behavior.
- Stage 17: runtime subsystem extraction.
  - Knowledge, automation, and outbox runtime concerns moved behind explicit runtime subsystem objects.
  - `Runtime` remains the composition root, but it no longer owns the detailed setup and lifecycle logic for each subsystem inline.
- Stage 18: session stream boundary hardening.
  - Session SSE queues are bounded.
  - Slow subscribers are closed instead of back-pressuring producers indefinitely.
  - Architecture tests guard services from importing the runtime composition root.
- Stage 19: narrow server route dependencies.
  - Server dependencies expose run registry, knowledge runtime, automation runtime, tool executor, and bus registry directly.
  - Routes that do not need the whole runtime no longer receive it by default.
- Stage 20: chat submission service boundary.
  - `submit_chat_message()` owns active-run injection vs new-run creation.
  - Chat HTTP code delegates the data-flow decision instead of duplicating it in the route handler.
- Stage 21: chat HTTP router extraction.
  - Chat SSE, message submission, injection cancel, run status, background-task, cancel, and tool-result endpoints now live in `ntrp.server.routers.chat`.
  - `ntrp.server.app` is back to process lifecycle, middleware, router registration, and remaining top-level endpoints.
  - Protocol docs now point session streaming ownership at the chat router instead of the application composition module.
- Stage 22: operational HTTP router extraction.
  - `/health`, `/outbox/*`, `/index/*`, `/scheduler/status`, and `/tools` now live in `ntrp.server.routers.ops`.
  - `ntrp.server.app` owns only lifecycle, middleware, and router registration.
  - Automation SSE now uses the shared bus-registry dependency instead of reading `request.app.state` directly.
- Stage 23: route and rollback hardening.
  - The duplicate `GET /providers` registration was removed; LLM provider management keeps `/providers`, and unified tool-provider status moved to `/tool-providers`.
  - Architecture tests now reject duplicate method/path registrations.
  - Config rollback now deep-copies nested settings and reloads runtime again after restoring the backup.
- Stage 24: backgrounded-run save merge.
  - Backgrounded chat drains merge their non-overlapping tail into the latest saved session instead of overwriting newer same-session conversation state.
  - Tests cover preserving newer messages and avoiding duplicate background tails.
- Stage 25: provider router extraction.
  - LLM provider, service-key, and unified tool-provider endpoints moved from `ntrp.server.routers.settings` to `ntrp.server.routers.providers`.
  - Public paths remain `/providers`, `/providers/{provider_id}`, `/services`, and `/tool-providers`.
  - Route registration tests cover the extracted provider endpoints.
- Stage 26: context router extraction.
  - Context usage, compaction, and directive endpoints moved from `ntrp.server.routers.settings` to `ntrp.server.routers.context`.
  - Public paths remain `/context`, `/compact`, and `/directives`.
  - `settings.py` is now focused on config and model management.

## Next candidates

- Consider UI or CLI exposure now that the backend endpoint fields are stable.
- Consider extracting stronger typed internal models for run-side protocol entries if raw message dictionaries keep spreading.
- Consider moving custom-model file mutation out of the settings router into `ConfigService` or a small model-management service.
- Continue runtime decomposition with monitor or MCP/config reload wiring once the HTTP composition surface has settled.
