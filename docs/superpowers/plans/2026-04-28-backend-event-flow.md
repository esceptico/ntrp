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

## Next candidates

- Consider UI or CLI exposure now that the backend endpoint fields are stable.
- Consider extracting stronger typed internal models for run-side protocol entries if raw message dictionaries keep spreading.
