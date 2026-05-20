# Event Streaming Implementation Notes

Date: 2026-05-20

## Running Notes

- Started from `docs/internal/event-streaming-audit.md` and treated its requirements matrix as the implementation checklist.
- The repo is already dirty with unrelated knowledge/memory/UI changes. This pass keeps edits scoped to event streaming files, focused tests, and this notes file.
- First implementation slice targets phase 1 plus one phase 2 item: typed keepalive data events and `TEXT_MESSAGE_END.content` reconciliation. Full background/automation durability is larger and should be handled after the basic stream contract is stable.
- Decision: keepalive is a typed `stream_keepalive` SSE data frame that repeats the latest bus seq instead of allocating a new event seq. This preserves the audit's rule that `seq` is a transport cursor, not a domain object id.
- Decision: automation stream initially changed only to typed keepalive, then was upgraded to cursor replay in the cleanup pass below.
- Decision: `TEXT_MESSAGE_END.content` is treated as final top-level assistant reconciliation. Nested text ends remain ignored in desktop transcript projection.
- Background completion already used hidden meta messages and existing `bg:<task_id>:<status>` client ids. This pass made the SSE event contract explicit with `event_id`, `model_visible`, and `ui_visible`, then added active-run injection dedupe by `client_id`.
- Tradeoff: active-run dedupe skips duplicate queued injections with the same `client_id`; it does not replace the earlier queued content. That matches exactly-once completion delivery better than last-writer-wins for background results.
- Decision: the desktop stream state now tracks `projectionSessionId`. This is a narrow version of the audit's session-scoped reducer recommendation: transient projection buffers are reset and rebound at stream connection boundaries without moving the whole projection reducer into Zustand yet.
- Decision: automation SSE now uses the same in-memory cursor/replay path as chat (`after_seq` + `subscribe_with_replay`) instead of staying live-only. This handles reconnect gaps while the server process is alive; durable cross-restart replay for automation events is still out of scope unless we add a persisted automation event ledger.
- Decision: desktop automation reconnects now include the last seen `seq`, advance on typed keepalives, and reload canonical automation/loop state on `stream_reset`. This keeps the global automation panel consistent without treating the SSE stream itself as durable storage.
- Cleanup: initial automation connects without `after_seq` are live-only and do not replay old buffered automation progress. Only reconnects with an explicit cursor use buffered replay. This prevents stale progress from resurrecting in the sidebar.
- Cleanup: fixed the desktop automation stream URL helper to preserve any path prefix in `serverUrl`, matching the existing `${serverUrl}/path` convention used by the API layer.
- Cleanup: removed the `get_latest_session_transcript_checkpoint_seq()` rename. It only clarified naming and added interface churn; the router comment now carries that distinction while the existing `get_latest_session_checkpoint_seq()` API remains unchanged.
