# Knowledge System Implementation Notes

This file tracks implementation decisions and tradeoffs while turning `docs/internal/knowledge-system-architecture.md` into code.

## 2026-05-19

### Research Rebase Pass

Decision: re-check the architecture before continuing implementation.

Sources checked:

- Letta stateful agents: persisted messages/tools/memory blocks plus core memory in context.
- Zep/Graphiti: temporal graph memory for changing facts and historical relationships.
- Generative Agents: observation, reflection, planning, and dynamic retrieval.
- ChatGPT memory/projects: automatic memory with user controls and scope boundaries.
- Memp procedural memory: build, retrieve, update, correct, and deprecate procedures from trajectories.

Changes:

- `knowledge-system-architecture.md` now splits memory by criteria: source-of-truth, evidence, episodic, semantic, procedural, proactive, artifact, and feedback.
- The doc now states the continual-learning loop explicitly: episode -> reflection -> candidate -> review/trusted policy -> activated behavior -> outcome feedback -> ranking/retention/deprecation.
- Ranking criteria now include temporal validity, diversity, and interruption cost.
- Automation ownership is explicit: reflection, retention, and health are background processors; UI buttons do not own learning.
- A dedicated `knowledge_event` trigger is required for direct episode-driven reflection; generic time, event, idle, and count triggers still cover sweeps, retention, health, and user checks.

Tradeoff:

- Power-user flexibility remains API/search/provenance-first instead of restoring raw object CRUD tabs.
- `knowledge_event` is intentionally narrow: lifecycle changes from `knowledge_objects`, filtered by action/object type/status/scope.

### Activation Boundary First

Decision: start with a backend activation abstraction instead of new persistent tables.

Reason:

- The current memory tables already contain facts, patterns, access events, provenance, and ranking signals.
- The architecture's safest first step is to separate "recall candidates" from "activated context".
- New durable object tables for episodes, lessons, procedure candidates, and action candidates need UI/review semantics. Adding those before the activation boundary would create more maintenance surface.

Additional direction:

- Do not add back-compat branches or keep dual behavior.
- The knowledge system is the new canonical abstraction.
- Existing memory repositories may be used as a temporary storage adapter, but new code should expose knowledge vocabulary: evidence, patterns, activation, actions, feedback.

Implementation scope:

- Add `ntrp.knowledge` models and activation service.
- Add `/knowledge/activation/inspect` API.
- Project current facts/patterns into generic activation candidates.
- Add deterministic action candidates only for explicit artifact/note/action-like queries.

Follow-up:

- This boundary was later connected to persisted `source`, `evidence_ref`, `episode`, `lesson`, `procedure_candidate`, `action_candidate`, `artifact`, `sink_receipt`, and `outcome_feedback` objects.
- The remaining work is quality and integration depth, not missing object lifecycle primitives.

Verification:

- `uv run pytest tests/test_knowledge_activation.py`
- `uv run pytest tests/test_knowledge_activation.py tests/test_runtime_config_status.py`
- `uv run ruff format ntrp/knowledge ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py`
- `uv run ruff check ntrp/knowledge ntrp/server/app.py ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py`
- `uv run python -c "import ntrp.server.app; print('ok')"`

### Search UI Uses Activation

Decision: change the desktop memory search pane to call `/knowledge/activation/inspect`.

Reason:

- The user clarified that implementation should be pure re-implementation, not back compatibility.
- The search pane should preview the new canonical activation bundle, not the old recall payload.

Tradeoff:

- The search pane no longer opens individual facts/patterns directly from the activation result.
- Facts and Patterns tabs still exist for inspection, but the query path now speaks knowledge activation language.

Verification:

- `bun run typecheck`
- `uv run pytest tests/test_knowledge_activation.py tests/test_runtime_config_status.py`
- `uv run ruff check ntrp/knowledge ntrp/server/app.py ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py`

### Persistent Knowledge Objects

Decision: add one generic `knowledge_objects` table instead of separate tables per object type.

Reason:

- The architecture needs the same lifecycle, provenance, scope, activation, and review fields across lessons, procedures, actions, artifacts, and episodes.
- Separate tables would add more CRUD and UI work before the object lifecycle is stable.
- Object-specific meaning can live in `object_type` and `metadata` until a type proves it needs its own table.

Tradeoff:

- The schema is less relational than a fully normalized design.
- It is simpler to review, activate, archive, and evolve.

### Review Surfaces

Decision: keep the object system internal and expose only a small review queue in the user UI.

Reason:

- The architecture says the UI should expose the pipeline without making users manage the database.
- Raw Evidence, Patterns, Lessons, Sent, Artifacts, and Audit tabs turn memory into manual administration.
- The user should review only exceptions: procedure candidates, action candidates, and artifact drafts.

Tradeoff:

- Low-level object inspection remains API/debug territory.
- The desktop Memory surface is intentionally smaller: Overview and Search.

### Action-Oriented Home

Decision: make Memory open on a new Knowledge home surface.

Reason:

- The architecture calls for an action-oriented default view.
- `/knowledge/summary` is the backend contract for surface counts and review prompts.

Tradeoff:

- Search remains one tab away.
- Reflection, pruning, and health checks are automation-owned. Home only refreshes state and handles exception review.

Verification:

- `bun run typecheck`
- `uv run pytest tests/test_knowledge_activation.py tests/memory/test_migrations.py tests/test_runtime_config_status.py`
- `uv run ruff check ntrp/knowledge ntrp/memory/service.py ntrp/memory/store/base.py ntrp/memory/store/migrations.py ntrp/server/app.py ntrp/server/runtime/outbox.py ntrp/server/runtime/automation.py ntrp/server/runtime/core.py ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py`

### Full Processor Surface

Decision: add first-class processors for reflection, artifact rendering, artifact publishing receipts, and outcome feedback.

Reason:

- The architecture is not complete with storage and activation only.
- Processors are the mechanism that moves objects through the system.

Tradeoff:

- Reflection is deterministic and conservative. It creates reviewable candidates from episodes instead of silently mutating behavior.
- Publishing writes through the local sink adapter and creates a `sink_receipt`.

### Full Source Flow

Decision: run completion now captures `source`, `evidence_ref`, and `episode` objects.

Reason:

- `Episode` alone skipped the source/evidence layers in the architecture.
- The full flow needs durable lineage before lessons, procedures, actions, and artifacts are trusted.

Tradeoff:

- Source and evidence objects are compact pointers, not transcript copies.
- The canonical data path is now complete, but older facts/patterns still live in memory storage as the evidence adapter.

### Episode Capture

Decision: capture completed runs as `episode` knowledge objects from the outbox run-completed handler.

Reason:

- The architecture requires `Source -> EvidenceRef -> Episode` before reflection and lessons can be trustworthy.
- Run completion is already the durable event boundary for extraction and scheduler follow-up.

Tradeoff:

- Episodes are compact summaries of run metadata and final result, not full transcript copies.
- Full source remains in session/outbox data; episode objects point to `run:<id>` and `session:<id>`.

### Final Verification

- `uv run pytest`
- `uv run ruff check ntrp/knowledge ntrp/memory/service.py ntrp/services/chat.py ntrp/operator/runner.py ntrp/server/runtime/core.py ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py`
- `bun run typecheck`

### Completion Pass

Decision: close the architecture into working product behavior.

Changes:

- Publishing now writes artifact markdown through a file-backed sink adapter and records the resulting path/byte count on `sink_receipt`.
- Activation now emits prompt-ready context, uses object-type/status/evidence/outcome scoring, and filters rejected/archived/superseded objects.
- Chat and operator prompt assembly now use `ActivationBundle.prompt_context`.
- Approving a procedure candidate now creates an active procedure object.
- Retention is exposed through `/knowledge/processors/prune`.
- Object source tracing is exposed through `/knowledge/objects/{id}/sources`.
- Desktop review surfaces now support editing, source/provenance inspection, pruning, feedback, artifact rendering, and publishing.

Tradeoff:

- Sink publication is local-file backed under `~/.ntrp/knowledge-sinks/<sink>/...`. This keeps publication testable and auditable without giving memory direct control over external services.
- Reflection remains deterministic and review-gated. The implemented contract favors safe, inspectable behavior changes over opaque automatic prompt mutation.

Verification:

- `uv run pytest`
- `uv run ruff check ntrp/knowledge ntrp/memory/service.py ntrp/services/chat.py ntrp/operator/runner.py ntrp/server/runtime/core.py ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py`
- `bun run typecheck`

### Replacement Pass

Decision: finish the pure replacement instead of leaving facts/observations as a live adapter.

Changes:

- Schema v20 migrates legacy facts into `knowledge_objects(type=fact)` and observations into `knowledge_objects(type=pattern)`.
- Activation now reads `knowledge_objects` only.
- `remember`, `recall`, and `forget` operate on knowledge objects.
- Built-in automation handlers now run knowledge reflection, retention, and health checks.
- Desktop Memory no longer imports old Facts, Observations, Sent, Cleanup, or Audit panes.
- The server app no longer mounts the legacy `/facts`, `/observations`, `/memory/recall/*`, or `/memory/prune/*` router.

Tradeoff:

- Some low-level legacy storage classes remain because v20 must read old SQLite tables during migration and existing repositories still own shared DB/telemetry plumbing.
- They are no longer the product contract or runtime activation path.

### Concept Review Pass

Decision: compare implementation against the architecture contract and fix underspecified shortcuts.

Changes:

- Activation records runtime injections as `outcome_feedback` objects when used by chat, operator, or recall.
- Prompt context excludes review-gated candidates, so `ActionCandidate` and draft review objects do not silently change agent behavior.
- Reflection now emits source-backed `fact` objects and review-gated `pattern` objects in addition to lessons, procedure candidates, and action candidates.
- Reflection idempotency is type-aware, so one reflected object no longer blocks later fact/pattern/procedure/action objects from the same episode.
- Superseded by the UX correction pass below: Sent and Audit are internal/API concepts, not default user tabs.

Tradeoff:

- Fact/pattern reflection is deterministic and conservative. It is enough to satisfy the architecture flow without adding an opaque LLM extraction pass back under a new name.

### UX Correction Pass

Decision: remove the manual object-management UI.

Changes:

- Desktop Memory now has Overview, Library, Review, and Activation.
- TUI Memory now has Overview, Library, Review, and Activation and calls `/knowledge/*` APIs only.
- Overview shows review exceptions plus recent context sent.
- Procedure/action candidates can be approved or dismissed; artifact drafts can be published or dismissed; all can be traced to sources.
- Reflection and pruning buttons were removed from the main UI.
- Old `chat_extraction_state` scheduler plumbing was removed; run completion now goes through scheduler handling and knowledge episode capture.
- Automation labels and internal filters now use `knowledge_reflection`, `knowledge_retention`, and `knowledge_health`.
- Built-in knowledge automations are no longer mixed into the default user automation list.

Tradeoff:

- The API can still expose processors and object details for debugging and tests.
- The product surface no longer asks the user to operate memory manually, but power users still get explicit System automation visibility.

### Continual-Learning Hardening Pass

Decision: keep temporal/procedural learning metadata inside `knowledge_objects.metadata` instead of adding new tables.

Reason:

- Zep/Graphiti proves temporal validity matters, but ntrp does not yet need a graph edge table.
- Memp/Voyager show procedures/skills should be updated from outcomes, but ntrp already has review-gated procedure candidates.
- Metadata keeps the sprint focused while still making temporal validity, feedback, and deprecation explicit.

Changes:

- Activation now skips expired, invalidated, and not-yet-valid objects based on `expires_at`, `valid_to`, `invalid_at`, `valid_from`, and `valid_at` metadata.
- Activation adds temporal signals, scope boost, procedure success/failure adjustment, and a diversity pass that omits near-duplicate candidates.
- Feedback now updates target metadata with `feedback_counts`, last feedback info, procedure success/failure counters, and creates a revision `procedure_candidate` after negative procedure feedback.
- Approving a revision candidate supersedes the target procedure before creating the replacement procedure.
- Retention no longer archives active procedures just because they are old.
- `/knowledge/processors/health` reports counts, missing provenance, stale objects, and review queue size; the built-in health automation uses it.

Tradeoff:

- Temporal facts are not yet a full graph with entity edges. The current design is enough to make activation safe and testable.
- Procedure update is review-gated; there is no silent self-modification of behavior.

### Final Gate

Decision: keep cross-type activation diversity.

Reason:

- A fact, pattern, and lesson can share terms while serving different roles.
- The diversity pass should collapse same-source duplicates or same-type paraphrases, not erase useful object-class separation.

Verification:

- `bun run typecheck` in `apps/desktop`
- `bun run typecheck` in `apps/tui`
- `bun test` in `apps/tui`
- `uv run ruff check ntrp tests` in `apps/server`
- `uv run pytest` in `apps/server`

### Knowledge Event Trigger Pass

Decision: add a first-class `knowledge_event` trigger instead of relying only on generic time/idle/count triggers.

Reason:

- Reflection should react to new episodes directly, not wait for count/idle/sweep.
- Power users need to see the memory pipeline explicitly without managing raw objects.

Changes:

- Added `KnowledgeObjectChanged` trigger events and `KnowledgeEventTrigger`.
- `knowledge_objects.create/update` dispatch lifecycle events to the scheduler when memory runtime is connected.
- Built-in `Knowledge Reflection` now includes `knowledge_event(actions=created, object_types=episode, statuses=active)`.
- Scheduler can route knowledge events through the same dedupe/event queue path as other event automations.
- Desktop Automations shows pipeline automations and lets power users inspect/run them.
- Desktop Automations now exposes a System tab with built-in/internal automations.

Tradeoff:

- `knowledge_event` is filter-based, not a general graph subscription language. That is enough for processors and keeps scheduler ownership intact.

### Verification Cleanup Pass

Decision: remove leftover public fact/observation services and fact-index outbox handlers.

Reason:

- The canonical runtime object is `knowledge_objects`; keeping old `FactService` and `ObservationService` left broken methods that referenced removed extraction internals.
- Search indexing must scan canonical knowledge objects, not legacy fact rows.
- The outbox should own run completion and durable background work, not obsolete `memory.fact.index.*` events.

Changes:

- `MemoryService` now exposes knowledge objects and lifecycle audit events only.
- `FactMemory` no longer accepts fact-index enqueue callbacks.
- `MemorySearchSource` scans `knowledge_objects` and indexes `knowledge:<id>` rows with type/status/scope metadata.
- Runtime outbox no longer registers or tests fact upsert/delete/clear index handlers.
- Removed the old fact/observation retrieval, audit, decay, reranker, and source-ref helper modules plus their now-obsolete tests.

Tradeoff:

- The old fact/observation tables and repositories still exist for schema migration, historical tests, and v20 projection into `knowledge_objects`; they are no longer the product/runtime service surface.

### Persisted Built-In Cleanup Pass

Decision: built-in seeding must prune stale built-in knowledge automations by persisted row state, not only create/update current IDs.

Reason:

- Existing local databases can keep old built-in rows after handler/id renames.
- Fresh-store tests missed that path, which caused duplicate System automation cards in the live UI.

Changes:

- `seed_builtins()` now deletes built-in knowledge-handler rows whose `task_id` is not one of the current four built-ins.
- Added a regression fixture with the exact stale rows: chat extraction, consolidation, memory maintenance, and memory health.
- Updated desktop/macOS automation classification tests and handlers to the current `knowledge_*` names.
- Replaced the stale `docs/internal/memory.md` file map with a current knowledge-system pointer.

Tradeoff:

- The cleanup targets only built-in rows with current knowledge handlers and non-current IDs. User automations with knowledge handlers are preserved.

### Memory UI Separation Pass

Decision: Memory must not surface automation controls. Automations remain in the Automations panel; Memory surfaces knowledge itself.

Reason:

- The previous Memory Overview made background processors look like user-managed memory.
- Power users need typed knowledge views, not one flat row list.
- Review should contain only behavior-changing drafts, while activation should show what the agent would actually receive.

Changes:

- Desktop Memory tabs are now `Overview`, `Library`, `Review`, and `Activation`.
- Desktop Library groups by typed knowledge objects: episodes, facts, patterns, lessons, procedures, actions, artifacts, and activation feedback.
- Desktop Review owns only draft procedure/action/artifact decisions.
- Desktop Activation keeps the prompt-context preview.
- TUI Memory mirrors the same four surfaces.
- Added view-model tests for typed knowledge buckets and review gating.

Tradeoff:

- Processor run controls are not duplicated in Memory. They stay in Automations/System, where operational controls belong.
