# ntrp CL Memory Implementation Notes

Date: 2026-05-25

## Current slice

Implementing the spec's first implementation slice from `docs/internal/ntrp-cl-memory-spec.md`: explicit write gate, episode-close routing, negative-feedback candidate cleanup, regression tests, and health counters.

## Decisions / tradeoffs

- Treat the spec's "First implementation slice" as the current scope. Later phases are retrieval bundles, usage telemetry, corrections, and skill promotion.
- Keep usage telemetry out of this slice. The spec recommends a dedicated table, but adding it before the write gate is stable would mix two migrations.
- Add the write gate as a service next to knowledge models rather than burying it in `KnowledgeObjectService.create()`. Some existing call sites still need to create audit/review objects directly; the gate should be explicit on CL write paths.
- Route episode-close durable candidates through the write gate before persistence. This avoids relying only on post-create cleanup.
- Keep historical/direct repository support for legacy rows in tests and migration code, but prevent new CL paths from regenerating active/draft `procedure`, `procedure_candidate`, `pattern`, or `entity_profile`.

## Implementation log

- Added red tests for:
  - write-gate decision models/service behavior;
  - unsourced extracted durable candidates not becoming active memory;
  - duplicate extracted memories becoming review candidates;
  - conflicting extracted memories becoming review candidates;
  - negative procedure feedback creating `action_candidate`, not `procedure_candidate`;
  - explicit `always` commands becoming `lesson`, not active legacy `procedure`.
- Added `MemoryWriteAction` and `MemoryWriteDecision` to the knowledge models.
- Added `KnowledgeWriteGate` in `apps/server/ntrp/knowledge/write_gate.py`.
- Write-gate behavior in this slice:
  - episode-close `pattern`, `procedure`, and `procedure_candidate` normalize to active `lesson`;
  - episode-close `entity_profile` is ignored;
  - episode-extracted active facts/lessons/artifacts without episode provenance are ignored;
  - conflicts become draft `action_candidate` review items;
  - likely duplicates become draft `action_candidate` review items;
  - accepted candidates get `metadata.write_gate = "knowledge.write_gate.v1"` plus action/reason/confidence metadata.
- Routed `_extract_memories_from_closed_episode(...)` through the write gate before persistence.
- Routed explicit `always`/`never` memory commands through the write gate. Decision: these now persist as `lesson`, not active legacy `procedure`, because the spec treats procedure-like durable memory as lessons until skill promotion exists.
- Negative feedback on legacy `procedure` now creates a draft `action_candidate` with `promotion_kind=lesson_revision`, not `procedure_candidate`.
- Approval promotion now supports review-gated `action_candidate` lesson revisions in addition to historical `procedure_candidate` rows. Tradeoff: only candidates with explicit promotion metadata are promoted, so ordinary action/follow-up candidates do not silently become lessons.
- Extended health with:
  - `unsourced_active_durable_objects`;
  - `write_gate_decisions`;
  - `write_gate_reviews_pending`.

## Verification log

- `uv run pytest tests/test_knowledge_write_gate.py -q` initially failed because `MemoryWriteAction` did not exist. This confirmed the new tests were red before implementation.
- `uv run pytest tests/test_knowledge_write_gate.py -q` -> `6 passed`.
- `uv run pytest tests/test_knowledge_activation.py::test_negative_procedure_feedback_creates_action_candidate_and_supersedes_old_procedure tests/test_knowledge_activation.py::test_explicit_memory_commands_write_archive_and_supersede tests/test_knowledge_activation.py::test_episode_close_model_extractor_creates_typed_candidates tests/test_knowledge_activation.py::test_close_memory_episode_extracts_durable_memory_with_episode_provenance tests/test_knowledge_activation.py::test_memory_create_policy_archives_unsourced_profiles_and_large_patterns -q` -> `5 passed`.
- `uv run pytest tests/test_knowledge_activation.py::test_health_counts_missing_provenance_stale_and_review_queue -q` -> `1 passed`.
- `uv run pytest tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py -q` -> `78 passed`.
- `uv run pytest tests/test_knowledge_*.py -q` -> `79 passed`.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/write_gate.py ntrp/knowledge/processors.py ntrp/memory/service.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` -> passed.

## Still out of scope after this slice

- Bundle-aware retrieval/context assembly.
- Correction detector in the chat/episode pipeline.
- Skill/playbook promotion UI and draft `SKILL.md` generation.
- Historical cleanup/backfill for older unsourced or legacy rows.

## 2026-05-25 — Phase 2 usage telemetry

Decision: reuse `memory_access_events` as the dedicated usage-event store for this phase.

Reason:

- It is already a separate audit table and is excluded from normal knowledge activation by construction.
- It already records retrieved/injected/omitted IDs and prompt character count.
- A new table would duplicate most of the existing schema before we know whether the current event shape is insufficient.

Changes:

- `ActivationBundle` now returns:
  - `retrieved_memory_ids`
  - `injected_memory_ids`
  - `omitted_memory_ids`
  - `usage_event_id`
- Activation access events now include the CL outcome envelope in `details`:
  - retrieved/injected/cited/omitted memory IDs;
  - `bundle_counts`;
  - `user_corrected_answer`;
  - `outcome`, defaulting to `unknown`;
  - full selected/omitted trace rows.
- Added access-event detail updates so later feedback can mark usage outcomes without creating durable remembered content.
- `KnowledgeFeedbackRequest` now accepts `usage_event_id` and `outcome`.
- `/knowledge/feedback` now updates usage-event outcome metadata when `usage_event_id` is supplied, while still creating the existing audit-only `outcome_feedback` object.
- Processor health now reports:
  - `memory_usage_events_7d`
  - `memory_helped_7d`
  - `memory_irrelevant_7d`
  - `memory_harmful_7d`

Tradeoffs:

- The existing table column names still say `*_fact_ids`; this phase treats those as memory object IDs for canonical `knowledge_objects`. I kept the columns for schema stability and put the clearer names in `details` and `ActivationBundle`.
- The `7d` health counters use recent access events and filter by `created_at` when available. Fake/in-memory test events without timestamps are treated as recent.

Verification:

- `uv run pytest tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects tests/test_knowledge_activation.py::test_feedback_updates_memory_usage_event_outcome tests/test_knowledge_activation.py::test_health_counts_recent_memory_usage_outcomes -q` -> `3 passed`.
- `uv run pytest tests/test_knowledge_activation.py::test_memory_access_event_store_updates_usage_outcome -q` -> `1 passed`.
- `uv run pytest tests/test_knowledge_*.py -q` -> `82 passed`.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/write_gate.py ntrp/knowledge/processors.py ntrp/knowledge/activation.py ntrp/memory/service.py ntrp/memory/store/access_events.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` -> passed.

## 2026-05-25 — Phase 3 retrieval bundles

Decision: keep `ActivationBundle.candidates` as the selected list for internal callers, but make the prompt assembly and response structured through explicit bundle fields.

Reason:

- Chat/operator callers already consume `prompt_context`; they do not need a separate compatibility path.
- Eval/tests still need a simple selected-candidate list, but now it is produced by bundle-aware fitting instead of flat rank-only fitting.

Changes:

- `ActivationCandidate` now carries `scope` and `metadata` so activation can reason about preferences, project scope, conflicts, and sources without reloading objects.
- `ActivationBundle` now includes:
  - `bundles`
  - `why_retrieved`
  - `source_summaries`
  - `conflict_warnings`
- Added bundle classifier for:
  - `active_user_preferences`
  - `procedural_lessons`
  - `active_project_memory`
  - `task_relevant_facts`
  - `artifacts_resources`
  - `recent_episode_context`
  - `warnings_conflicts`
  - `source_evidence_context`
- Replaced flat fitting with bundle-aware fitting:
  - first selects the best item from important bundles;
  - then fills remaining slots by score;
  - still applies near-duplicate, limit, and budget omissions.
- Prompt context now renders compact XML-like bundle sections with object type/id, score, source hints, and retrieval reasons.
- Conflict metadata now surfaces as `warnings_conflicts` and `conflict_warnings`.

Tradeoffs:

- Legacy `pattern` rows are no longer treated as procedural lessons for required-bundle priority. They can still activate by score, but they should not outrank current facts/lessons just because they are pattern-shaped legacy memory.
- Source summaries are compact source-id hints, not full source traces. Full provenance remains available via the source-trace route.
- Bundle fitting uses deterministic classification, not an LLM judge. This keeps activation predictable and testable.

Verification:

- `uv run pytest tests/test_knowledge_activation.py::test_activation_projects_current_memory_into_typed_candidates tests/test_knowledge_activation.py::test_activation_context_groups_required_memory_bundles tests/test_knowledge_activation.py::test_activation_surfaces_conflict_warnings_in_context -q` initially failed on the old flat prompt/bundle shape, then passed after implementation.
- `uv run pytest tests/test_knowledge_*.py -q` -> `84 passed`.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/write_gate.py ntrp/knowledge/processors.py ntrp/knowledge/activation.py ntrp/knowledge/activation_scoring.py ntrp/memory/service.py ntrp/memory/store/access_events.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` -> passed.

## 2026-05-25 — Phase 4 correction loop

Decision: implement correction handling as a conservative backend review path first.

Reason:

- The spec wants high-signal corrections, not broad irritation mining.
- Reviewable `action_candidate` rows fit the current Memory Review model and avoid silent behavior mutation.

Changes:

- Added `KnowledgeObjectService.apply_correction_signal(...)`.
- Correction triggers currently include:
  - `no, i meant`
  - `that's wrong`
  - `that is wrong`
  - `don't do that`
  - `remember this instead`
  - `from now on`
  - `you keep`
- Correction candidates:
  - persist as draft `action_candidate`;
  - carry `promotion_kind=memory_write_review`;
  - cite turn/run/source IDs and target memory IDs when supplied;
  - include write-gate review metadata;
  - can later be approved into a lesson by the existing review promotion path.
- When target memory IDs are supplied, the target memory gets:
  - score decay;
  - `feedback_counts.corrected`;
  - `correction_candidate_ids`;
  - last-feedback metadata.
- When a usage event ID is supplied, the usage event is marked `harmful` with `user_corrected_answer=true`.
- `assimilate_run_completed(...)` now calls the correction detector on user messages when the message was not already handled as an explicit memory command.

Tradeoffs:

- This does not try to infer target memories from text yet. That requires the run-level injected-memory IDs to be passed through the chat/run event boundary.
- UI review affordance is still generic action-candidate review; no custom correction panel yet.
- Vague messages like "that's annoying" are ignored.

Verification:

- `uv run pytest tests/test_knowledge_write_gate.py::test_correction_signal_creates_review_candidate_and_marks_target tests/test_knowledge_write_gate.py::test_vague_correction_signal_is_ignored -q` initially failed on the missing service method, then passed.
- `uv run pytest tests/test_knowledge_*.py -q` -> `86 passed`.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/write_gate.py ntrp/knowledge/processors.py ntrp/knowledge/activation.py ntrp/knowledge/activation_scoring.py ntrp/memory/service.py ntrp/memory/store/access_events.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` -> passed.

## 2026-05-25 — Phase 5 skill/playbook promotion

Decision: implement skill promotion as draft `action_candidate` rows with a full draft body, then create the skill from Memory Review only after an explicit user action.

Reason:

- The spec is explicit that skills must not be written silently.
- The Memory Review row now acts as the approval surface for memory-originated skill proposals; it shows the full `SKILL.md` body before the write.

Changes:

- Added `KnowledgeProcessorService.propose_skill_promotions(...)`.
- Added `POST /knowledge/processors/skill-promotions`.
- Detector currently promotes active/approved lessons when repeated evidence exists through:
  - `metadata.success_count >= min_successes`, or
  - `metadata.feedback_counts.helpful`, or
  - their sum crossing the threshold.
- Created candidates are draft `action_candidate` objects with:
  - `promotion_kind=skill`;
  - `approval_flow=memory_review_create_skill`;
  - `skill_name`;
  - `skill_description`;
  - full `skill_body`;
  - source lesson IDs and source IDs.
- Existing skill candidates suppress duplicate proposals for the same lesson.
- Review UI now labels skill candidates, shows the full skill draft, and uses the `Create skill` action label.

Tradeoffs:

- Earlier implementation only marked the proposal reviewed and left skill creation to a later chat/tool flow. Post-review, the Review action now creates the skill through `SkillService.create(...)`, marks the candidate approved, and links created-skill metadata back to the source lessons.
- The detector is metadata-based. Deeper repeated-use detection from usage events can be added after usage outcomes have enough real data.

Verification:

- `uv run pytest tests/test_knowledge_write_gate.py::test_repeated_successful_lesson_creates_skill_promotion_candidate -q` initially failed on the missing processor method, then passed.
- `uv run pytest tests/test_knowledge_write_gate.py::test_approved_skill_promotion_creates_skill_and_links_source_lesson -q` initially failed on the missing promotion service, then passed.
- `uv run pytest tests/test_knowledge_*.py -q` -> `87 passed`.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/write_gate.py ntrp/knowledge/processors.py ntrp/knowledge/activation.py ntrp/knowledge/activation_scoring.py ntrp/memory/service.py ntrp/memory/store/access_events.py ntrp/server/routers/knowledge.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` -> passed.
- Desktop typecheck initially failed inside sandbox because `npx` could not resolve `node@22.12.0`; reran with approved network access.
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` in `apps/desktop` -> passed.

## 2026-05-25 — Phase 6 health counters

Changes:

- Added health counters for:
  - `correction_candidates_pending`
  - `skill_candidates_pending`
  - `dangling_source_refs`
- Existing CL quality counters now cover:
  - usage outcomes;
  - active legacy objects;
  - tool-looking episodes;
  - extracted objects without episode source;
  - unsourced active durable objects;
  - write-gate decisions and pending write-gate reviews;
  - duplicate/conflict fact clusters.

Tradeoff:

- `dangling_source_refs` is a distinct-ref count across the scanned health window, not a per-object total. This keeps it actionable and avoids inflating one missing object referenced many times.

Verification:

- `uv run pytest tests/test_knowledge_activation.py::test_health_counts_missing_provenance_stale_and_review_queue -q` -> passed with new correction/skill/dangling-source assertions.
- `uv run pytest tests/test_knowledge_*.py -q` -> `87 passed`.

## Pre-review verification pass

- `uv run pytest tests/test_knowledge_*.py -q` -> `87 passed`.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/write_gate.py ntrp/knowledge/processors.py ntrp/knowledge/activation.py ntrp/knowledge/activation_scoring.py ntrp/memory/service.py ntrp/memory/store/access_events.py ntrp/server/routers/knowledge.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` -> passed.
- `git diff --check -- apps/server/ntrp/knowledge/models.py apps/server/ntrp/knowledge/__init__.py apps/server/ntrp/knowledge/write_gate.py apps/server/ntrp/knowledge/processors.py apps/server/ntrp/knowledge/activation.py apps/server/ntrp/knowledge/activation_scoring.py apps/server/ntrp/memory/service.py apps/server/ntrp/memory/store/access_events.py apps/server/ntrp/server/routers/knowledge.py apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_activation.py apps/desktop/src/lib/knowledgeViews.ts apps/desktop/src/components/memory/KnowledgeReviewPane.tsx docs/internal/ntrp-cl-memory-implementation-notes.md` -> passed.
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` in `apps/desktop` -> passed with approved network access for `npx`.

## 2026-05-25 — Post-review structural fixes

Trigger: strict review found that the CL memory implementation worked in focused tests but concentrated too much policy in `KnowledgeObjectService` / `KnowledgeProcessorService`, duplicated matching helpers, and exposed a misleading skill-promotion action.

Changes:

- Added `KnowledgeSkillPromotionService`.
  - `propose_skill_promotions(...)` moved out of the generic processor.
  - `create_skill_from_candidate(...)` creates the skill via `SkillService.create(...)`, approves the candidate, and records `skill_created_*` metadata.
  - Source lessons now receive `metadata.skill_promotions[]` backlinks.
- Added focused backend modules:
  - `knowledge/fact_consolidation.py`;
  - `knowledge/corrections.py`;
  - `knowledge/review_promotions.py`;
  - `knowledge/health.py`;
  - `knowledge/activation_bundles.py`;
  - `knowledge/similarity.py`;
  - `knowledge/metadata.py`.
- `KnowledgeObjectService` now delegates write-gate application, fact consolidation, correction candidate creation, and approved-review promotion.
- `KnowledgeProcessorService` now delegates skill promotion and health aggregation.
- Activation bundle classification, budget fitting, prompt formatting, source summaries, and conflict warnings moved out of `activation.py`.
- Removed the dead activation `_fit_budget` path.
- Desktop Review now calls `POST /knowledge/skill-promotions/{id}/create` for skill candidates instead of generic status approval.

Tradeoffs:

- `KnowledgeObjectService` remains large because it already owns core object CRUD, episode assimilation, entity resolution, and embedding side effects. The post-review fix removes CL-specific policy from the file without attempting a broader service decomposition in this branch.
- Memory-originated skill creation uses the Memory Review row as the explicit user approval surface instead of synthesizing a chat tool approval card. This avoids silent writes and keeps the full draft visible where the proposal is reviewed.

Verification:

- `uv run pytest tests/test_knowledge_write_gate.py::test_approved_skill_promotion_creates_skill_and_links_source_lesson -q` failed before `KnowledgeSkillPromotionService` existed, then passed.
- `uv run pytest tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py -q` -> `71 passed`.
- `uv run pytest tests/test_knowledge_*.py -q` -> `88 passed`.
- `uv run ruff check ntrp/knowledge ntrp/memory/service.py ntrp/server/routers/knowledge.py tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py` -> passed.
- `./node_modules/typescript/bin/tsc --noEmit` in `apps/desktop` -> passed.

## 2026-05-25 — Agent-review gate hardening

Trigger: follow-up review found remaining write-gate bypasses and automatic conflict supersession.

Changes:

- `KnowledgeObjectService.create(...)` now routes through `write_gate_decision(...)` and `apply_write_gate_decision(...)`.
- Added `_create_without_write_gate(...)` only for already-gated writes, migrations/test fixtures, and internal review-candidate creation.
- Direct active/draft writes of legacy `pattern`, `procedure`, and `procedure_candidate` no longer persist as those types:
  - episode-close legacy outputs still normalize to active lessons;
  - direct procedure/pattern writes normalize to lessons;
  - direct procedure-candidate writes become draft action candidates.
- Active/draft durable writes without `source_ids` now become review candidates instead of active memory.
- Active/draft durable writes with malformed source refs or dangling `knowledge:<id>` refs now become review candidates instead of active memory.
- Update policy now rejects attempts to activate or rewrite active/draft legacy rows, and rejects active/draft durable rows without sources.
- Semantic conflict detection now delegates review-candidate creation to `KnowledgeConflictReviewService`. It no longer commits supersession automatically.
- Health now counts pending write-gate reviews only when `write_gate_action == "review"`; ordinary accepted writes are still counted as write-gate decisions.
- Follow-up cleanup changed duplicate detection from a `merge` write-gate action to a `review` action. Similarity and contradiction heuristics now only create draft review candidates; they do not merge, supersede, or mutate active durable memory metadata.
- Desktop Review no longer treats `procedure_candidate` as an active review type. Old wire/schema support remains only so historical rows can be read.
- LongMemEval benchmark ingestion now stores session refs as prefixed source IDs while reporting raw dataset session IDs in benchmark traces/citations. This keeps benchmark writes compatible with source-ref validation without changing benchmark output semantics.

Tradeoffs:

- Legacy enum values remain in the model for old rows and read paths, but service/API writes cannot create active/draft rows with those types.
- External provenance refs such as `run:*`, `turn:*`, `episode:*`, `session:*`, and benchmark `source:*` refs are shape-checked but not existence-checked; there is no single canonical source table for those IDs yet.
- Existing legacy rows can still receive feedback metadata/score updates so negative feedback can produce a review candidate; content/status rewrites remain blocked.
- Tests that intentionally need historical bad rows now seed through the repository rather than the service boundary.

Verification:

- Regression tests for direct create bypass, unsafe update bypass, and conflict review initially failed, then passed.
- `uv run pytest tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py tests/test_knowledge_routes.py -q` -> `91 passed`.
- `uv run pytest tests/test_spawn_salvage.py -q` -> `20 passed`.
- `uv run pytest -q` -> `875 passed`.
- `uv run ruff check ntrp tests` -> passed.
- `git diff --check` -> passed.

## 2026-05-25 — Verification cleanup

Trigger: follow-up review requested exact failure cleanup without broadening the branch.

Changes:

- The reported spawn-salvage token-usage failure did not reproduce; `tests/test_spawn_salvage.py` passed before any spawn changes, so no spawn code was changed.
- Desktop knowledge view tests now expect `fact`, `lesson`, `artifact`, and `memory_episode` library surfaces.
- `procedure_candidate` was removed from `KNOWLEDGE_REVIEW_TYPES`; explicit test coverage now asserts draft procedure candidates are not active review items.
- Source-ref validation now rejects malformed refs and dangling `knowledge:<id>` refs for active/draft durable writes.
- LongMemEval stores benchmark session refs with source prefixes so benchmark facts pass validation while traces/citations still expose raw dataset session IDs.
- Duplicate detection now creates a review candidate with `write_gate_action == "review"`, not `merge`.
- Semantic conflict review creation no longer annotates active durable memory metadata.

Verification:

- `uv run pytest tests/test_knowledge_write_gate.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py tests/test_knowledge_routes.py -q` -> `92 passed`.
- `uv run pytest tests/test_spawn_salvage.py -q` -> `20 passed`.
- `uv run pytest -q` -> `876 passed`.
- `uv run ruff check ntrp tests` -> passed.
- `git diff --check` -> passed.
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` -> passed after rerunning with network access for `npx`.
- `npm run build` -> passed.
- `bun test` -> `265 pass`.

## 2026-05-25 — Closed-loop slice 1: feedback signals feed lessons

Trigger: implement `docs/internal/ntrp-cl-memory-closed-loop-spec.md` one feature/fix at a time. First slice targets the missing signal path between feedback/outcomes and skill promotion.

Problem:

- Skill promotion reads `lesson.metadata.success_count` and `lesson.metadata.feedback_counts.helpful`.
- Feedback processing only updated target metadata when `score_delta` was non-zero.
- Success/failure counters were only applied to legacy `procedure` objects, not retained `lesson` objects.
- Result: a user could mark a lesson helpful and the promotion detector would still have no reliable signal.

Changes:

- `KnowledgeProcessorService.feedback()` now applies metadata feedback for any targeted object even when `score_delta == 0`.
- Feedback metadata updates are centralized in `_apply_feedback_to_target()`.
- `lesson` and legacy `procedure` targets now both receive `success_count` / `failure_count` updates from positive/negative signals.
- Score remains unchanged unless the request includes a non-zero `score_delta`.
- Added regression coverage that helpful feedback against a lesson populates `feedback_counts.helpful` and `success_count` without requiring a score change.

Verification:

- `uv run pytest apps/server/tests/test_knowledge_write_gate.py::test_lesson_feedback_populates_skill_promotion_signals apps/server/tests/test_knowledge_activation.py::test_feedback_updates_memory_usage_event_outcome -q` -> `2 passed`.
- `uv run ruff check apps/server/ntrp/knowledge/processors.py apps/server/tests/test_knowledge_write_gate.py` -> passed.
- `git diff --check -- apps/server/ntrp/knowledge/processors.py apps/server/tests/test_knowledge_write_gate.py docs/internal/ntrp-cl-memory-implementation-notes.md` -> passed.
- Thermo review -> passed for this slice. File sizes stayed below the 1k-line danger threshold (`processors.py` 262 LOC, `test_knowledge_write_gate.py` 536 LOC). No new abstraction or spaghetti issue found; the change centralizes an already-existing feedback update path instead of adding another branch.

## 2026-05-25 — Slice 1: activation usage metadata counters

### Scope
- Added the first closed-loop usage primitive: every recorded activation now also updates selected knowledge-object metadata.
- Hooked `KnowledgeActivationService.inspect(... record_access=True)` to call `KnowledgeObjectService.record_activation_usage(...)` after the existing `memory_access_events` row is created.
- Added per-object activation metadata counters:
  - `activation_count`, `last_activated_at`, `last_activation_event_id`
  - `retrieved_count`, `last_retrieved_at`
  - `injected_count`, `used_count`, `last_used_at`
  - `omitted_count`, `last_omitted_at`

### Files changed
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_knowledge_activation.py`

### Behavior added
- Activation still writes the detailed `memory_access_events` trace with ranks/scores/reasons/candidate metadata.
- Activation now leaves durable per-memory usage counters on retrieved/injected/omitted objects, giving later outcome/correction/skill-promotion slices something to learn from.
- Telemetry metadata updates are non-critical: if counter recording fails, recall still returns the activation bundle and logs a warning instead of breaking user context assembly.
- Counter parsing is defensive against bad historical metadata values.

### Validation
- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects apps/server/tests/test_knowledge_activation.py::test_record_activation_usage_updates_memory_metadata -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_activation.py -q` → `62 passed`
- `git diff --check` → clean

### Thermo review result
- Ran the thermo-nuclear review skill for this slice and inspected the implementation directly.
- Findings:
  - Acceptable for a first narrow primitive; no new abstraction stack, no UI hot-path expansion, no live DB mutation outside normal activation runtime.
  - Main caveat: `used_count` currently means “injected into prompt/context”, not proven “semantically used by the model.” Future outcome feedback must distinguish injected vs cited/helpful/harmful.
  - Main debt: metadata counters are denormalized and updated object-by-object; okay for now, but high-volume activation should eventually get an atomic usage table / batch aggregation path instead of JSON metadata as the source of truth.
  - Repo-local thermo command was not discoverable (`find . -maxdepth 4 ...` found no thermo/review command), so this pass used the configured review skill plus focused diff inspection.

### Remaining gaps
- Usage event still lacks explicit run/session/task IDs beyond the existing activation request/task/source fields.
- Outcome feedback is not yet propagated back into per-memory helpful/harmful/irrelevant counters.
- Skill promotion still depends on weak/underwired helpfulness/success signals.

## 2026-05-25 — Slice 2: outcome feedback counters for used memories

### Scope
- Added the second closed-loop primitive: feedback on an activation now updates the memories that were actually injected into that activation.
- Centralized outcome counter updates in `KnowledgeObjectService.record_usage_outcome(...)`.

### Files changed
- `apps/server/ntrp/knowledge/processors.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_knowledge_activation.py`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`

### Behavior added
- `KnowledgeProcessorService.feedback(...)` still updates the `memory_access_events` outcome detail.
- If feedback references a `usage_event_id`, the service now applies feedback metadata to the event's injected memory IDs.
- If feedback references a `target_object_id`, the target still receives score/`feedback_counts` updates, and now also receives normalized closed-loop counters through the same outcome path.
- Added per-memory outcome metadata:
  - `feedback_count`
  - `helpful_count`
  - `harmful_count`
  - `irrelevant_count`
  - `corrected_count`
  - `last_feedback_signal`
  - `last_feedback_outcome`
  - `last_feedback_at`
  - `last_feedback_event_id`
  - `last_corrected_at` for corrections
- Outcome counter parsing is defensive against malformed historical metadata values.

### Validation
- `pytest apps/server/tests/test_knowledge_activation.py::test_feedback_updates_memory_usage_event_outcome apps/server/tests/test_knowledge_activation.py::test_record_usage_outcome_updates_injected_memory_metadata -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_activation.py -q` → `63 passed`
- `git diff --check` → clean

### Thermo review result
- Ran the slice through the configured thermo-nuclear review procedure by doing a strict diff/code-path inspection after tests.
- Findings:
  - Good: outcome mapping is centralized in `KnowledgeObjectService.record_usage_outcome(...)`; processors no longer duplicate helpful/harmful/irrelevant counter semantics.
  - Good: feedback dedupes IDs through the service and excludes the explicit target from event-injected IDs to avoid double-counting.
  - Caveat: outcome signals are still stringly typed (`helped`, `harmful`, `irrelevant`, `corrected`) because the existing API is string-based. A later cleanup should move this to an enum/model-level validator.
  - Caveat: counters remain JSON metadata, not a normalized aggregate table. This is okay for current volume and keeps the slice small, but it is not the long-term analytics substrate.
  - Caveat: feedback applies outcome counters to injected memories, which is better than nothing but still not proof the model semantically relied on each item. Future cited/accepted/corrected signals should refine this.

### Remaining gaps
- No UI affordance yet to mark a selected memory as helpful/irrelevant/harmful directly from Review/Recall.
- No correction-closure flow yet: harmful/corrected feedback does not automatically create/supersede corrected memory.
- Skill promotion can now consume better counters, but the promotion detector itself is still scaffold-level.

## 2026-05-25 — Slice 3: correction feedback closes the usage loop

Files changed:
- `apps/server/ntrp/knowledge/corrections.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_knowledge_write_gate.py`

Behavior added:
- User correction signals that are tied to a memory usage event now update both the access event outcome and the referenced memory objects' feedback metadata.
- Correction-linked targets get `feedback_count`, `corrected_count`, `harmful_count`, `last_feedback_*`, and `last_corrected_at` through the shared outcome counter path.
- If the access event can report injected memory ids, those ids are included in the correction outcome update so the blame/quality signal reaches memories that were actually inserted into the answer context.
- Harmful correction outcomes now increment both `corrected_count` and `harmful_count`; correction is the semantic signal, harmful is the quality signal.

Remaining gaps:
- This still depends on callers passing `target_memory_ids` or a usage event with injected ids; automatic contradiction detection and supersession/approval of the correction candidate remain future slices.
- The correction candidate remains review-only; it does not create the replacement fact/lesson automatically, intentionally avoiding memory soup.

Validation:
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_correction_signal_creates_review_candidate_and_marks_target apps/server/tests/test_knowledge_activation.py::test_record_usage_outcome_updates_injected_memory_metadata -q` → 2 passed.
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_activation.py -q` → 78 passed.
- `git diff --check` → no output.

Thermo review:
- Pass. The change reuses the existing shared outcome counter path instead of adding a second bespoke metadata updater.
- No new UI hot path, schema migration, background worker, or live DB mutation.
- Watch item: correction outcome wiring still uses permissive `getattr` around `access_events`; acceptable for current service-boundary tolerance, but a future cleanup should make this interface explicit instead of duck-typed.

## 2026-05-25 — Slice 4: activation bundle selection trace

Files changed:
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior added:
- Activation responses now expose a structured `selection_trace` alongside the selected/omitted candidates.
- Each trace item includes rank, score, object id/type/title, whether it was selected, whether it was injected into the prompt, `used_by_model`, surface (`prompt` or `context`), selection reason, retrieval reasons, signals, sources, and text size.
- The access-event trace uses the same enriched shape, so API callers and persisted usage events now agree on why each memory was selected or omitted.

Remaining gaps:
- `used_by_model` is still inferred from prompt injection, not from a true model-side attribution signal.
- The trace explains retrieval/budget behavior; it does not yet connect to skill activation decisions or workflow-mined playbooks.

Validation:
- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_projects_current_memory_into_typed_candidates -q` → 1 passed.
- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects -q` → 1 passed.
- `pytest apps/server/tests/test_knowledge_activation.py -q` → 63 passed.
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_activation.py -q` → 78 passed.
- `git diff --check` → no output.

Thermo review:
- Pass after tightening `surface` to the spec-compatible values `prompt`/`context` instead of inventing `omitted` as a surface.
- The change is additive to the response model and reuses the existing activation trace helper, avoiding a second hand-rolled trace schema.
- Watch item: `selection_trace` is still typed as `list[dict[str, Any]]`; if it grows, promote it to a dedicated Pydantic model instead of letting anonymous dicts sprawl.

## 2026-05-25 — Slice 5: explicit activation trace model

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior added:
- Promoted the activation selection trace from anonymous `dict[str, Any]` entries to the typed `ActivationSelectionTrace` response model.
- Constrained `surface` to the allowed activation surfaces (`prompt`, `context`, `tool`, `skill`) instead of leaving arbitrary strings open.
- Persisted usage-event details still store JSON dictionaries via `model_dump(mode="json")`, so DB payloads remain serializable while API internals stay typed.

Remaining gaps:
- The model allows `tool` and `skill`, but current activation usage only emits `prompt`/`context`; true skill/tool activation tracing is still a later slice.
- `signals` remains a flexible list of JSON objects because the underlying signal model is already serialized there.

Validation:
- `pytest apps/server/tests/test_knowledge_activation.py -q` → 63 passed.
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_activation.py -q` → 78 passed.
- `git diff --check` → no output.

Thermo review:
- Pass. This removes schema ambiguity introduced by Slice 4 and makes invalid surfaces fail validation early.
- No migration or live DB touch; persisted event payload shape is the same JSON keys as Slice 4.
- Watch item: when skill activation lands, do not bolt more ad hoc trace variants onto this model; extend the same model or create a sibling typed event for non-memory activation.

## 2026-05-25 — Slice 6: usage-event control-plane endpoint

Files changed:
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior added:
- Added `GET /knowledge/activation/usage-events` for inspecting recorded activation usage events.
- Defaults to `source=knowledge_activation`, clamps `limit` to `1..500`, clamps negative offsets to `0`, and returns event details including the selection trace written by activation.
- This gives the review/control plane a read path for “what memory was activated, why, and was it injected?” without hitting expensive health/consolidation processors.

Remaining gaps:
- No desktop UI yet; this is backend control-plane plumbing only.
- Endpoint exposes raw event details; a later UI/API slice should summarize per-memory usage/outcome stats instead of forcing reviewers to read raw event payloads.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py -q` → 2 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_write_gate.py -q` → 80 passed.
- `git diff --check` → no output.

Thermo review:
- Pass. The endpoint is bounded, source-filtered by default, and does not run any expensive processors.
- Good: no live DB mutation and no UI hot-path dependency.
- Watch item: avoid turning this endpoint into a dumping ground for analytics; richer review summaries should be computed separately and cached if they become expensive.

## 2026-05-25 — Slice 7: explicit activation outcome feedback endpoint

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/__init__.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior added:
- Added `POST /knowledge/activation/usage-events/{event_id}/outcome` to record explicit outcomes for activation usage events.
- Supports spec-level outcomes: `helpful`/`helped`, `irrelevant`, `harmful`, `corrected`, `task_success`, `task_failure`, and `unknown`.
- Updates the access event outcome details and then updates usage outcome metadata on the explicitly targeted memory ids, or on the event's injected memory ids when no explicit targets are supplied.
- Dedupe/sorts target ids before metadata updates and rejects non-positive target ids at request validation.
- Extended `KnowledgeFeedbackRequest.outcome` to accept the same closed-loop outcome vocabulary so existing feedback paths can carry corrected/task-success/task-failure signals instead of squeezing everything into `helped|irrelevant|harmful|unknown`.

Remaining gaps:
- This endpoint records outcome metadata, but it does not create a separate `outcome_feedback` knowledge object; the existing `/knowledge/feedback` path still handles durable feedback objects.
- No desktop review UI yet for applying these outcomes from the usage-event list.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py -q` → 4 passed.
- `pytest apps/server/tests/test_knowledge_activation.py::test_record_usage_outcome_updates_injected_memory_metadata -q` → 1 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_write_gate.py -q` → 82 passed.
- `git diff --check` → no output.

Thermo review:
- Pass after tightening `target_object_ids` to positive integers and making event-not-found return a real 404 before any memory metadata update.
- Good: endpoint only updates the event plus the memories actually injected/explicitly targeted, avoiding broad retrieved-memory punishment.
- Watch item: there are now two feedback surfaces (`/knowledge/feedback` and this direct outcome endpoint). Keep their responsibilities explicit or consolidate later; otherwise feedback semantics will drift like absolute spaghetti.

## 2026-05-25 — Slice 8: per-memory activation usage summary

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/__init__.py`
- `apps/server/ntrp/knowledge/usage_events.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior added:
- Added `GET /knowledge/activation/usage-summary` to summarize recent activation usage by memory object without running expensive memory health/consolidation processors.
- Summary rows include event/retrieved/selected/injected/omitted/used-by-model counts, selection reasons, surfaces, outcome counts, last event id, and last seen timestamp.
- Added `KnowledgeUsageObjectSummary` and a dedicated `knowledge/usage_events.py` aggregation helper instead of bloating the router with analytics logic.
- Outcome updates can now record explicit `target_object_ids` in access-event details; summaries use those targets when present, otherwise they attribute event-level outcomes only to injected memories.

Remaining gaps:
- Summary scans recent events on demand; if this becomes large or hot-path, move it to a cached/background processor.
- Summary does not hydrate object titles/types; reviewers still need a second object lookup or UI join for human-friendly display.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py -q` → 5 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_write_gate.py -q` → 83 passed.
- `git diff --check` → no output.

Thermo review:
- Pass after moving aggregation out of the router and preserving explicit target attribution for outcomes.
- Good: bounded to 500 events by default/max, source-filtered, and no object table scan.
- Watch item: if UI starts polling this aggressively, it becomes analytics in the request path. Cache it before it turns into another `/knowledge/health` lmao.

## 2026-05-25 — Slice 9: desktop Review usage-signal surface

Files changed:
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

Behavior added:
- Added desktop API typings/client for `GET /knowledge/activation/usage-summary`.
- Review pane now shows a compact **Memory usage signals** section with recent per-memory activation counts, injected/used counts, top selection reasons, surfaces, outcomes, and last-seen time.
- Usage summary loads separately from draft review objects and fact consolidation, with its own stale async generation guard and non-blocking error display.

Remaining gaps:
- Rows currently show `knowledge:<id>` only; a later slice should hydrate titles/types or join with loaded objects for a friendlier review workflow.
- This is a read-only signal surface; it does not yet let reviewers mark a specific usage row as helpful/harmful from the UI.

Validation:
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` → passed.
- `bun test` → 265 passed, 0 failed.
- `npm run build` → status 0; built renderer/main/preload successfully, existing large-chunk warning only.
- `git diff --check` → no output.

Thermo review:
- Pass. The UI does not mount another heavy health/consolidation scan; it calls the bounded usage summary endpoint separately and degrades to a local error pill.
- Good: the section is read-only, compact, and isolated from the draft-review approval flow.
- Watch item: showing raw ids is honest but rough. Hydrate object summaries next; don’t turn this pane into a mystery-meat table.

## 2026-05-25 — Slice 10: hydrate usage-summary rows

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

Behavior added:
- Usage-summary rows now include `object_title`, `object_type`, and `object_status` when the referenced memory object still exists.
- Backend hydrates those fields with one bounded batch lookup after aggregation, not N+1 object reads.
- Added `max_objects` to cap response rows separately from the event scan limit, preventing huge SQL placeholder lists when recent events reference many memories.
- Desktop Review now shows titles/types/statuses instead of only raw `knowledge:<id>` rows.
- Fixed the desktop contract to use backend’s `outcome_counts` and `events_scanned` field names.

Remaining gaps:
- Dangling object ids still show as raw `knowledge:<id>`, by design; a later health/control-plane slice can make dangling usage references reviewable.
- The endpoint is still computed on request. It is bounded and cheap enough for Review, but should be cached if it starts getting polled.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py -q` → 5 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_write_gate.py -q` → 83 passed.
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` → passed.
- `bun test` → 265 passed, 0 failed.
- `npm run build` → status 0; existing large-chunk warning only.
- `git diff --check` → no output.

Thermo review:
- Pass after fixing two contract problems caught in review: the UI was reading `outcomes` while the API returns `outcome_counts`, and the endpoint needed a row cap separate from event scan size.
- Good: hydration is batched, bounded, and tolerant of missing historical objects.
- Watch item: `limit` means event scan size, not row count. It is documented by code now via `max_objects`, but the API is still a little footgunny.

## 2026-05-25 — Slice 11: Review UI can record latest usage outcomes

Files changed:
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

Behavior added:
- Added a desktop API wrapper for `POST /knowledge/activation/usage-events/{event_id}/outcome`.
- Review’s usage summary now includes per-row controls to mark the latest usage event for a memory as helpful, irrelevant, or harmful.
- The UI posts the selected outcome with the row’s memory id as an explicit target, so multi-memory activation events do not fan outcome metadata to unrelated objects.
- After marking an outcome, only the bounded usage summary is refreshed. It does not rerun pending review queries or the expensive fact-consolidation scan.

Remaining gaps:
- This is deliberately coarse: summary rows mark only the latest event, not an arbitrary historical event. A later detailed event drawer/table should expose exact event-level feedback.
- Repeated user clicks on the same latest event can still add repeated feedback counters server-side. That needs backend idempotency or per-event/outcome history before this becomes a high-trust quality signal.

Validation:
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` → passed.
- `bun test` → 265 passed, 0 failed.
- `npm run build` → status 0; existing large-chunk warning only.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py -q` → 68 passed.
- `git diff --check` → no output.

Thermo review:
- Pass with caveat. The first draft reloaded the whole Review pane after outcome marking, which would have rerun consolidation and recreated the original “hot Review path” smell. Fixed to refresh only usage summary.
- Remaining sharp edge: event-level outcome idempotency is not solved yet. UI labels this as “latest event,” but backend needs dedupe semantics before counts are trusted for automatic promotion.

## 2026-05-25 — Slice 12: idempotent usage outcome feedback

Files changed:
- `apps/server/ntrp/memory/service.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior added:
- Usage event feedback now stores per-object labels in `event.details.feedback_by_object`.
- Reposting the same `signal`/`outcome` for the same event/object is idempotent: the event detail is preserved/updated, but memory metadata counters are not incremented again.
- Reclassifying an event/object from one label to another adjusts quality counters instead of double-counting. Example: helpful → harmful decrements `helpful_count`, increments `harmful_count`, and leaves `feedback_count` as one unique labeled event.
- Added a service-level `get()` for access events so the route can compare existing feedback before writing.
- Hardened the route against malformed historical `feedback_by_object` details by treating non-dicts as empty and ignoring non-string previous labels.

Remaining gaps:
- This handles one feedback label per event/object. It does not yet preserve a full audit history of label changes; only the current classification is stored on the event details.
- The extra `harmful_count` fallback for harmful outcomes remains for compatibility with existing outcome strings. It is safe for normal labels, but it is still a slightly weird counter rule.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py -q` → 71 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_write_gate.py -q` → 86 passed.
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` → passed before backend-only slice.
- `bun test` → 265 passed, 0 failed before backend-only slice.
- `npm run build` → status 0 before backend-only slice; existing large-chunk warning only.
- `git diff --check` → no output.

Thermo review:
- Pass after hardening malformed `feedback_by_object` handling. Initial approach fixed duplicate counts but assumed the event detail shape was always a dict; that is exactly the kind of historical-data optimism this memory system cannot afford.
- Good: counter adjustment is localized in `KnowledgeObjectService.record_usage_outcome` and route logic remains explicit about which event/object changed.
- Watch item: a future audit trail table would be cleaner than piling more current-state fields into event details, but this is a pragmatic non-destructive slice.

## 2026-05-25 — Slice 13: skill promotion reads real helpful usage counters

Files changed:
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

Behavior added:
- Skill promotion candidates can now be proposed from the new flat `helpful_count` metadata populated by usage outcome feedback, not only legacy `metadata.feedback_counts.helpful` or manual `success_count`.
- Promotion candidate metadata carries `helpful_count` so Review can show why the lesson became promotable.
- Integer counter parsing is defensive; malformed `helpful_count`/`success_count` values no longer crash promotion scans.

Remaining gaps:
- This is still threshold promotion of one lesson, not real workflow mining across episodes. It wires the closed-loop outcome signal into the existing promotion scaffold so useful memories can actually become visible.
- Promotion quality still depends on good lesson extraction and human review.

Validation:
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → 16 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_write_gate.py -q` → 87 passed.
- `git diff --check` → no output.

Thermo review:
- Pass. This is intentionally small and removes a real dead-wire: the system was recording `helpful_count` but promotion only looked at older/manual counters.
- Watch item: this does not make threshold-based promotion smart. The next serious improvement should mine repeated workflows across episodes/lessons instead of promoting a lone popular lesson blindly.

## 2026-05-25 — Slice 14: activation item view exposes closed-loop usage fields

Files changed:
- `apps/server/ntrp/memory/store/migrations.py`
- `apps/server/tests/memory/test_migrations.py`

Behavior added:
- Added schema migration v29 to recreate `knowledge_activation_items` with closed-loop usage columns:
  - `used_by_model`
  - `surface`
  - `selection_reason`
- Refactored the activation item view SQL behind `_recreate_knowledge_activation_items_view(...)` so v28 and v29 use one definition instead of duplicated view text.
- Kept legacy `candidate_ids` events visible in the same view, with explicit defaults:
  - `used_by_model` follows legacy `injected`
  - `surface = prompt`
  - `selection_reason = legacy_candidate_id`
- Newer structured candidates/omissions now preserve the precise usage semantics required by the closed-loop spec.

Remaining gaps:
- The view still reads JSON from `memory_access_events.details`; this is good enough for reporting, but heavier analytics may eventually deserve a real normalized event-items table.
- The view does not include run/session/task IDs because those are not consistently present in access event details yet.

Validation:
- `pytest apps/server/tests/memory/test_migrations.py -q` → 19 passed.
- `pytest apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py -q` → 106 passed.
- `git diff --check` → no output.

Thermo review:
- Pass. The main structural win is extracting the view DDL to a single helper used by both the original v28 migration and the corrective v29 migration.
- Watch item: JSON-backed view is acceptable as a compatibility/reporting layer, but don’t build complex mining logic on it forever; normalize activation items if workflow mining starts needing joins/aggregates at scale.

## 2026-05-25 — Slice 15: activation requests carry run/session/task identifiers

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/memory/store/migrations.py`
- `apps/server/tests/memory/test_migrations.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior added:
- `ActivationRequest` now accepts optional `run_id`, `session_id`, and `task_id` fields.
- Recorded activation access events now persist those identifiers in `details` alongside the existing human-readable `task` label.
- Added migration v30 to expose `run_id`, `session_id`, and `task_id` as first-class columns in `knowledge_activation_items`.
- Updated activation and migration tests so structured usage logs preserve the context IDs required by the closed-loop spec.

Remaining gaps:
- Callers still need to actually pass real session/run/task IDs. This slice creates the transport/storage path; it does not yet wire every runtime caller.
- The activation-items view is still the read/reporting projection over JSON details, not a normalized analytics table.

Validation:
- `pytest apps/server/tests/memory/test_migrations.py::test_migrate_v28_archives_activation_telemetry_and_exposes_activation_items -q -s --tb=short` → 1 passed.
- `pytest apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py -q && git diff --check` → 83 passed; diff check clean.
- `pytest apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py -q` → 106 passed.

Thermo review:
- Pass after fixing one real migration hygiene issue: v30 was added to `_MIGRATIONS` before bumping `CURRENT_VERSION`, which would have left schema bookkeeping inconsistent. Fixed to `CURRENT_VERSION = 30`.
- Risk remains caller completeness, not storage. Next slice should wire the main activation caller(s) to pass session/run/task identity where available, or add route-level assertions if no caller has those IDs yet.

## 2026-05-25 — Slice 16: wire runtime activation callers to context IDs

Files changed:
- `apps/server/ntrp/services/chat.py`
- `apps/server/ntrp/operator/runner.py`
- `apps/server/tests/test_iteration_window.py`

Behavior added:
- Chat prompt activation now passes:
  - `session_id` from the active chat session
  - `task_id` from `client_id` when present
- Operator/automation prompt activation now passes:
  - `run_id` generated for the operator run
  - `task_id` from `automation_id` when present, otherwise `source_id`
- Added a focused chat test that monkeypatches activation inspection and asserts session/client IDs reach `ActivationRequest` before access telemetry is recorded.

Remaining gaps:
- Chat activation still does not have `run_id` at activation time because the chat run is currently created after prompt preparation. Wiring that cleanly means reordering run creation, not cramming a fake ID into telemetry.
- Operator activation still does not pass `session_id` because the operator session is currently created after prompt preparation. Same deal: fix with a deliberate preparation-order slice if needed.
- Tool-level activation calls (`recall`, `forget`, `research_context`) mostly lack session/run/task context. They need tool context plumbing later.

Validation:
- `pytest apps/server/tests/test_iteration_window.py::test_prepare_chat_passes_session_and_client_ids_to_activation -q` → 1 passed.
- `pytest apps/server/tests/test_iteration_window.py::test_prepare_chat_passes_session_and_client_ids_to_activation apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py -q && python -m py_compile apps/server/ntrp/operator/runner.py apps/server/ntrp/services/chat.py && git diff --check` → 84 passed; compile and diff check clean.
- `pytest apps/server/tests/test_iteration_window.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py -q` → 120 passed.

Thermo review:
- Pass with caveat. This slice improves real telemetry coverage without pretending every context ID exists.
- The honest remaining design smell is ordering: both chat and operator build activation context before all run/session identifiers are available. Do not paper over that with synthetic IDs; either reorder setup or leave fields null.

## 2026-05-25 — Slice 17: operator activation gets real session identity

Files changed:
- `apps/server/ntrp/operator/runner.py`
- `apps/server/tests/test_operator_activation_context.py`

Behavior added:
- Operator run preparation now creates its session before memory activation, so activation telemetry records both:
  - generated `run_id`
  - actual `session_id`
- Added a focused operator test that monkeypatches agent creation and activation inspection, then verifies activation telemetry and the agent receive the same run/session identifiers.

Remaining gaps:
- Chat activation still lacks `run_id` because chat run creation happens after prompt preparation. That needs a separate ordering refactor if we want complete chat run identity in activation telemetry.
- Tool-level recall/research activations still need context plumbing.

Validation:
- `pytest apps/server/tests/test_operator_activation_context.py -q` → 1 passed.
- `pytest apps/server/tests/test_operator_activation_context.py apps/server/tests/test_iteration_window.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py -q && python -m py_compile apps/server/ntrp/operator/runner.py apps/server/ntrp/services/chat.py && git diff --check` → 98 passed; compile and diff check clean.
- `pytest apps/server/tests/test_operator_activation_context.py apps/server/tests/test_iteration_window.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py -q` → 121 passed.

Thermo review:
- Pass. This is a real cleanup, not just telemetry decoration: session creation now happens before any session-scoped memory lookup in operator mode.
- Risk is low because the session was already always created in `_prepare`; this only moves it earlier. If any future session creation grows side effects, keep this order explicit in tests.

## 2026-05-25 — Slice 18: chat activation gets real run identity

Files changed:
- `apps/server/ntrp/services/chat.py`
- `apps/server/tests/test_iteration_window.py`

Behavior added:
- Chat run creation now happens before prompt/memory preparation, so activation telemetry can record the actual chat `run_id` instead of leaving it null.
- `_prepare_messages(...)` now accepts `run_id` and passes it through `ActivationRequest` together with the existing `session_id` and `task_id`/`client_id`.
- Expanded the focused chat activation test to assert the activation request `run_id` equals the returned `ctx.run.run_id`.

Remaining gaps:
- Tool-level activation calls still do not receive full run/session context. Runtime chat/operator prompt activation is now covered; tool invocation plumbing is separate.

Validation:
- `pytest apps/server/tests/test_iteration_window.py::test_prepare_chat_passes_session_and_client_ids_to_activation -q` → 1 passed.
- `pytest apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py -q && python -m py_compile apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py && git diff --check` → 98 passed; compile and diff check clean.
- `pytest apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py -q` → 121 passed.

Thermo review:
- Pass. This removes the previous ordering excuse for null chat `run_id` without adding fake IDs.
- Watch item: run allocation now occurs a little earlier in `prepare_chat`; current behavior is safe because the run already belonged to this preparation path and is still populated before return. If future failures before return need cleanup, handle that in run lifecycle code rather than memory telemetry.

## 2026-05-25 — Slice 19: usage summaries honor per-object feedback

Files changed:
- `apps/server/ntrp/knowledge/usage_events.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior added:
- Activation usage summaries now read `details.feedback_by_object` and count outcomes per specific memory object.
- Event-level `details.outcome` remains a fallback only when no per-object feedback is present. This avoids smearing a single top-level outcome across the wrong object set once the closed loop has object-specific feedback.
- Expanded the route test so one usage event can report object `10` as harmful while object `11` is helpful.

Remaining gaps:
- The summary is still bounded to recent events from `access_events.list_recent`; long-term rollups/cached aggregates are still a separate processor/cache problem.
- Outcome vocabulary is still a small literal set; richer user reactions can be normalized later.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py::test_activation_usage_summary_aggregates_recent_event_trace_and_outcomes -q` → 1 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/memory/test_migrations.py -q && python -m py_compile apps/server/ntrp/knowledge/usage_events.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py && git diff --check` → 105 passed; compile and diff check clean.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_write_gate.py -q` → 121 passed.

Thermo review:
- Pass. This fixes an actual attribution bug in the feedback loop: object-specific outcomes must stay object-specific or the system learns garbage.
- The fallback path is intentionally preserved for older usage events that only had top-level outcome fields.

## 2026-05-25 — Slice 20: feedback detail edits do not double-count outcomes

Files changed:
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior added:
- Updating a usage event with the same per-object `signal`/`outcome` but a changed `detail` now updates `feedback_by_object` on the event.
- The same edit does **not** call `record_usage_outcome(...)`, so memory-level counters are not double-counted for a note/detail correction.
- Existing idempotency and reclassification behavior remains intact:
  - exact same feedback → no metadata update
  - changed classification → replaces previous counter instead of double-counting

Remaining gaps:
- The route still returns `updated_object_ids` for metadata counter changes only. If the UI needs to distinguish detail-only edits, add a separate response field instead of overloading this one.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py::test_activation_usage_event_outcome_updates_detail_without_double_counting apps/server/tests/test_knowledge_routes.py::test_activation_usage_event_outcome_is_idempotent_for_same_object_signal apps/server/tests/test_knowledge_routes.py::test_activation_usage_event_outcome_reclassifies_existing_feedback_without_double_counting -q` → 3 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/memory/test_migrations.py -q && python -m py_compile apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/knowledge/usage_events.py && git diff --check` → 106 passed; compile and diff check clean.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/memory/test_migrations.py apps/server/tests/test_knowledge_write_gate.py -q` → 122 passed.

Thermo review:
- Pass. This is a small but important counter-integrity fix: closed-loop learning data should be editable without inflating helpful/harmful counts.
- The implementation keeps one clear distinction: event feedback can change independently; memory metadata counters only change on classification changes.

## 2026-05-25 — Slice 21: tool-level memory activation gets runtime identity

Files changed:
- `apps/server/ntrp/tools/memory.py`
- `apps/server/ntrp/tools/research.py`
- `apps/server/tests/test_memory_tools.py`
- `apps/server/tests/test_research_tools.py`

Behavior added:
- `recall()` tool activation telemetry now records:
  - `task_id` = tool call id
  - `session_id` = current session
  - `run_id` = current run
  - project knowledge scope when present
- Research prompt memory activation now records the same runtime identity and sets `record_access=True`, so memories injected into spawned research context are no longer invisible to usage telemetry.
- `forget()` activation now carries runtime identity too, without changing its archival behavior.

Remaining gaps:
- `forget()` still does not record an activation access event. That is deliberate for this slice because it is a destructive/search-for-archive path, not prompt/context injection; if we want audit trails for forget searches, add a separate access surface/policy instead of pretending it was model context.
- Other bespoke memory retrieval paths outside `KnowledgeActivationService` still need an audit pass.

Validation:
- `pytest apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py::test_research_prompt_memory_activation_records_runtime_context -q` → 3 passed.
- `pytest apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py -q && python -m py_compile apps/server/ntrp/tools/memory.py apps/server/ntrp/tools/research.py && git diff --check` → 89 passed; compile and diff check clean.

Thermo review:
- Pass. This closes a real attribution hole: memories pulled by explicit recall and research context now have run/session/tool-call identity.
- The change is intentionally boring plumbing with focused tests. No fake run IDs, no broad behavioral changes, no UI coupling.
- Watch item: research context now writes activation access events. That is correct for closed-loop learning, but if research calls become extremely frequent we may need rollup/cached summaries rather than querying raw access rows on UI hot paths.

## 2026-05-25 — Slice 22: activation telemetry records the actual surface

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/tools/memory.py`
- `apps/server/ntrp/tools/research.py`
- `apps/server/tests/test_memory_tools.py`
- `apps/server/tests/test_research_tools.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior added:
- `ActivationRequest` now has an explicit `surface` field: `prompt`, `context`, `tool`, or `skill`.
- Activation access event details persist the requested surface.
- Selection traces for injected memories now use the requested surface instead of always pretending they were prompt context.
  - Example: recall/research tool activations now emit `surface="tool"` and `selection_reason="selected_for_tool"`.
  - Omitted memories still emit `surface="context"` because they were not actually injected anywhere.
- `recall()`, `forget()`, and research context activation set `surface="tool"`.

Remaining gaps:
- Chat/operator surfaces still default to `prompt`, which matches their current injection path.
- Skill activation still needs a dedicated retrieval/use path that sets `surface="skill"` instead of stuffing skill-ish memory into ordinary prompt context.
- Selection traces still do not distinguish sub-surfaces such as `research_prompt`; `task="research_context"` currently carries that detail.

Validation:
- `pytest apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py::test_research_prompt_memory_activation_records_runtime_context apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects -q` → 4 passed.
- `pytest apps/server/tests/test_knowledge_activation.py -q` → 64 passed.
- `pytest apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_knowledge_routes.py -q && python -m py_compile apps/server/ntrp/knowledge/models.py apps/server/ntrp/knowledge/activation.py apps/server/ntrp/tools/memory.py apps/server/ntrp/tools/research.py && git diff --check` → 97 passed; compile and diff check clean.

Thermo review:
- Pass. This removes a misleading telemetry abstraction where tool-injected memory was labeled as prompt use.
- The model/API change is small and defaults preserve existing callers.
- Risk is low: persisted historical events can still carry old `surface` values in details, and read paths already treat details as JSON metadata rather than strict domain objects.

## 2026-05-25 — Slice 23: outcome feedback can only target memories from the activation event

Files changed:
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior added:
- `/knowledge/activation/usage-events/{event_id}/outcome` now validates explicit `target_object_ids` against the memory ids actually present on that access event:
  - retrieved ids
  - injected ids
  - omitted ids
- Unknown target ids are rejected with HTTP 400 before event outcome mutation and before per-memory metadata updates.
- Default behavior is unchanged: if no explicit targets are provided, feedback applies to the event's injected memory ids.

Why this matters:
- Feedback is only a learning signal if it is causally tied to the memory that was actually retrieved/injected/omitted for that event.
- Before this slice, a caller could attach helpful/harmful/corrected counters to arbitrary memory ids through an unrelated access event. That poisons the loop, lmao.

Remaining gaps:
- The endpoint still lets callers target omitted ids intentionally. That is useful for explicit “this omitted memory should/should not have mattered” feedback, but UI affordances should make that distinction clear.
- There is still no higher-level correction closure here; this only protects attribution integrity.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py::test_activation_usage_event_outcome_rejects_targets_outside_event apps/server/tests/test_knowledge_routes.py::test_activation_usage_event_outcome_updates_event_and_memory_metadata -q` → 2 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py -q && python -m py_compile apps/server/ntrp/server/routers/knowledge.py && git diff --check` → 98 passed; compile and diff check clean.

Thermo review:
- Pass. This is a small defensive integrity check with a direct closed-loop payoff: no arbitrary counter poisoning through usage outcomes.
- The check is intentionally strict for explicit targets and leaves historical event read paths alone.
- No DB migration, no server restart, no live data mutation.

## 2026-05-25 — Slice 24: correction feedback writes per-object event detail

Files changed:
- `apps/server/ntrp/knowledge/corrections.py`
- `apps/server/tests/test_knowledge_corrections.py`

Behavior added:
- `KnowledgeCorrectionService.apply(...)` now reads the referenced usage event before writing correction outcome feedback.
- Correction feedback now writes `feedback_by_object` entries for the corrected target memories plus memories injected by the referenced activation event.
- The usage event update now receives explicit `target_object_ids` for those objects.
- Per-memory `record_usage_outcome(...)` is only called if the usage event update actually succeeds.

Why this matters:
- Correction signals should be traceable to the exact memory objects that contributed to the bad answer, not only smeared as top-level event outcome.
- Failed/missing usage-event updates no longer still mutate memory outcome counters, which would create fake learning signal.

Remaining gaps:
- This still creates a review-gated correction candidate; it does not yet auto-supersede stale memory or create the replacement fact/lesson. That belongs behind the review/write-gate path.
- It uses injected ids from the existing usage event plus explicit correction targets; deeper contradiction matching is still pending.

Validation:
- `pytest apps/server/tests/test_knowledge_corrections.py -q` → 2 passed.
- `pytest apps/server/tests/test_knowledge_corrections.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py -q && python -m py_compile apps/server/ntrp/knowledge/corrections.py && git diff --check` → 100 passed; compile and diff check clean.

Thermo review:
- Pass. This strengthens causal attribution for corrections and blocks counter mutation when the event write fails.
- The implementation stays localized and keeps historical read paths tolerant.
- Watch item: once review approval creates corrected replacement memory, it should link back to these correction candidates and supersede stale targets instead of leaving “old fact + correction note” soup.

## 2026-05-25 — Slice 25: approved correction reviews create replacement memory

Files changed:
- `apps/server/ntrp/knowledge/review_promotions.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_knowledge_write_gate.py`

Behavior added:
- Approving a correction review candidate now creates a real replacement memory object instead of treating the review candidate itself as the durable corrected fact/lesson.
- The stale target memory is superseded by the replacement object id, not by the review candidate id.
- Replacement promotion has explicit helpers for:
  - target id extraction from correction metadata;
  - replacement object type selection;
  - replacement title selection;
  - replacement text extraction.
- Replacement text is taken from reviewed correction fields (`replacement_content`, `corrected_content`, `proposed_content`, etc.) and rejects review-instruction prose like “Review correction”.
- `KnowledgeReviewPromotionService` now receives an explicit already-approved replacement creation callback from `KnowledgeObjectService`, instead of reaching into a private method by name.

Why this matters:
- This closes the worst correction-loop failure mode: accumulating “old fact + correction note” soup without actually retiring the stale memory.
- A reviewer approval now has a concrete state transition: candidate approved, replacement durable memory created, stale target superseded to that replacement.

Remaining gaps:
- This is still the backend approval flow only; the Review UI still needs to make correction replacement/source context obvious.
- Conflict closure and duplicate merge flows still need the same kind of “replace the stale object, do not just add commentary” scrutiny.
- Replacement extraction is deterministic and intentionally conservative; richer correction payloads can add more explicit reviewed fields later.

Validation:
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_approved_correction_candidate_creates_replacement_and_supersedes_target apps/server/tests/test_knowledge_write_gate.py::test_approved_plain_memory_write_review_preserves_candidate_text -q` → 2 passed.
- `python -m py_compile apps/server/ntrp/knowledge/review_promotions.py apps/server/ntrp/memory/service.py` → clean.
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_activation.py::test_explicit_memory_commands_write_archive_and_supersede -q && git diff --check` → 19 passed; diff check clean.

Thermo review:
- Initial review caught a brittle private-method lookup from `KnowledgeReviewPromotionService` into `KnowledgeObjectService`.
- Fixed by injecting the approved replacement creation callback explicitly, matching the existing write-gate/conflict-service pattern.
- Post-fix review: pass. The replacement flow is small, helperized, does not leak review instructions into durable memory, and avoids hot-path/read-path compatibility churn.

## 2026-05-25 — Slice 26: per-memory activation metadata keeps rank/score/reason

Files changed:
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior added:
- Activation access recording now forwards the same selection trace used in the access event into `record_activation_usage(...)`.
- Per-memory metadata now records the latest activation trace fields:
  - `last_activation_rank`
  - `last_activation_score`
  - `last_activation_surface`
  - `last_selection_reason`
  - `last_used_by_model`
  - `last_activation_selected`
  - `last_activation_injected`
  - `last_activation_reasons`
- Existing counters/timestamps still update as before: activation/retrieved/injected/omitted/used counts and timestamps.

Why this matters:
- The closed loop needs to know not only that memory was used, but why it was selected and how it ranked.
- This makes the latest per-memory activation attribution inspectable without having to reconstruct everything from raw access-event JSON.

Remaining gaps:
- This stores the latest trace only; historical rank/score lives in access events, not each memory object.
- `_record_access(...)` is still a chunky method assembling event payload plus per-memory telemetry. It is tolerable for this slice, but should be split if the activation payload grows again.
- `used_by_model` is still inferred from injection, not direct model attention/acceptance.

Validation:
- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects apps/server/tests/test_knowledge_activation.py::test_record_activation_usage_updates_memory_metadata -q` → 2 passed.
- `pytest apps/server/tests/test_knowledge_activation.py -q && python -m py_compile apps/server/ntrp/knowledge/activation.py apps/server/ntrp/memory/service.py && git diff --check` → 64 passed; compile and diff check clean.
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py apps/server/tests/test_iteration_window.py apps/server/tests/test_operator_activation_context.py -q && git diff --check` → 98 passed; diff check clean.

Thermo review:
- Pass with one watch item: `_record_access(...)` remains broad, but this slice kept the added behavior isolated to passing trace JSON plus two small metadata helpers.
- No DB migration and no historical read-path strictness added.
- The new metadata fields are additive and sourced from the already-recorded activation trace, so attribution stays consistent with the access event.

## 2026-05-25 — Slice 27: usage/review summaries expose latest activation attribution

### Scope

Made activation attribution visible in the usage summary/read-model path instead of burying it only inside raw event details or object metadata.

### Files changed

- `apps/server/ntrp/knowledge/models.py`
  - Added explicit `KnowledgeUsageObjectSummary` fields:
    - `last_activation_rank`
    - `last_activation_score`
    - `last_activation_surface`
    - `last_selection_reason`
    - `last_used_by_model`
    - `last_activation_reasons`
- `apps/server/ntrp/knowledge/usage_events.py`
  - Summary aggregation now carries the latest activation trace attribution per memory object.
  - Historical events missing rank/score/reasons remain tolerated and return `null`/empty defaults.
  - Refactored the previously chunky summary loop into smaller helpers after thermo review flagged that adding more inline trace copying would grow the spaghetti.
- `apps/server/tests/test_knowledge_routes.py`
  - Extended the activation usage summary regression to assert rank, score, surface, selection reason, used-by-model, and explanation reasons.
- `apps/desktop/src/api.ts`
  - Exposed the new usage summary fields to desktop typing.
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
  - Review usage rows now show concise latest attribution: reason, rank, score, and surface.

### Behavior

The Review/usage summary API now answers “why was this memory last activated?” directly from the summary row:

- selected reason (`selected_for_prompt`, omitted reason, etc.)
- latest surface (`prompt`, `context`, `tool`, `skill`)
- rank and score
- whether it was used by the model
- raw explanation reasons from the activation trace

This closes the Slice 26 follow-through gap: selection attribution was being recorded, but Review/summary consumers still had to dig through event details or object metadata to see it.

### Validation

- `pytest apps/server/tests/test_knowledge_routes.py::test_activation_usage_summary_aggregates_recent_event_trace_and_outcomes -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_activation.py -q` → `73 passed`
- `python -m py_compile apps/server/ntrp/knowledge/usage_events.py apps/server/ntrp/knowledge/models.py` → passed
- `git diff --check` → passed
- `cd apps/desktop && npm run typecheck` → passed

### Thermo review

- Initial review found a real maintainability smell: `summarize_activation_usage_events(...)` was already large and the first implementation added more inline attribution plumbing.
- Fixed before closing the slice by extracting focused helpers:
  - `_new_row`
  - `_latest_trace_fields`
  - `_increment_membership_counts`
  - `_record_trace_items`
  - `_record_feedback_outcomes`
  - `_mark_seen`
- Post-refactor function size check:
  - `summarize_activation_usage_events`: 46 lines
  - largest new helper: 39 lines
- Result: pass.

### Remaining gaps

- Review still needs stronger correction/conflict closure UX around superseded/replaced memories.
- Usage telemetry still needs a final pass for any remaining activation surfaces that do not produce a usage event.
- Workflow mining and skill activation/invocation remain the big missing closed-loop pieces.

## 2026-05-25 — Slice 28: omitted activation traces keep the real caller surface

### Scope

Fixed a telemetry attribution bug in activation traces: omitted/non-injected memories were being relabeled as `context` even when the actual activation caller was `tool` or another surface.

### Files changed

- `apps/server/ntrp/knowledge/activation.py`
  - `_activation_trace_item(...)` now preserves the request surface for all trace rows.
  - `used_by_model` still stays `false` unless the memory is actually injected into model context.
  - Selection reason behavior is unchanged:
    - injected → `selected_for_<surface>`
    - selected but not injected → `selected_not_injected`
    - omitted → `omitted_by_budget_or_limit`
- `apps/server/tests/test_knowledge_activation.py`
  - Extended access-event regression to assert omitted trace rows from a tool activation stay stamped as `surface="tool"`, with `used_by_model=false`.

### Behavior

Closed-loop usage telemetry now distinguishes:

- where activation was requested (`surface`), from
- whether the model actually saw the memory (`used_by_model` / injected fields).

That matters for tool/research recall audits: omitted tool memory should not look like generic prompt/context memory just because it was not injected.

### Validation

- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py -q` → `73 passed`
- `python -m py_compile apps/server/ntrp/knowledge/activation.py apps/server/ntrp/knowledge/usage_events.py apps/server/ntrp/knowledge/models.py` → passed
- `git diff --check` → passed

### Thermo review

- Checked the changed helper shape after the slice.
- `_activation_trace_item(...)`: 31 lines.
- No new abstraction pile or branching tangle; this is a one-line semantic fix plus targeted assertions.
- Result: pass.

### Remaining gaps

- Need a final audit of all activation consumers to ensure every real runtime usage path chooses the right `surface` and `record_access` behavior.
- Workflow mining and skill promotion/activation are still incomplete.

## 2026-05-25 — Slice 29: usage summaries expose latest task/session/run attribution

### Scope

Completed the usage-summary attribution shape by surfacing the latest activation task/session/run fields alongside rank/score/reason.

### Files changed

- `apps/server/ntrp/knowledge/models.py`
  - Added explicit summary fields:
    - `last_activation_task`
    - `last_activation_task_id`
    - `last_activation_session_id`
    - `last_activation_run_id`
- `apps/server/ntrp/knowledge/usage_events.py`
  - Summary rows now copy the latest event-level task/session/run IDs from activation event details.
  - Historical events without those fields return `null`, not errors.
- `apps/server/tests/test_knowledge_routes.py`
  - Extended usage-summary regression with task/session/run fields.
- `apps/desktop/src/api.ts`
  - Added desktop typings for the new summary fields.
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
  - Latest attribution line now includes task and run IDs when present.

### Behavior

Review/usage summaries can now answer both:

- why a memory was selected (`selection_reason`, rank, score, surface), and
- where that activation happened (`task`, `task_id`, `session_id`, `run_id`).

This closes the remaining attribution requirement for the summary/read-model path.

### Validation

- `pytest apps/server/tests/test_knowledge_routes.py::test_activation_usage_summary_aggregates_recent_event_trace_and_outcomes -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py -q` → `73 passed`
- `python -m py_compile apps/server/ntrp/knowledge/usage_events.py apps/server/ntrp/knowledge/models.py apps/server/ntrp/knowledge/activation.py` → passed
- `git diff --check` → passed
- `cd apps/desktop && npm run typecheck` → passed

### Thermo review

- Kept task/session/run extraction in `_latest_event_fields(...)` instead of adding more inline logic to the summary loop.
- Post-change size check:
  - `summarize_activation_usage_events`: 46 lines
  - `_latest_event_fields`: 9 lines
  - largest helper remains `_record_feedback_outcomes`: 39 lines
- No new giant function or hidden coupling.
- Result: pass.

### Remaining gaps

- Review/control-plane still needs better correction/conflict closure UX.
- Need stronger workflow mining from episodes/actions into skill/playbook candidates.
- Skill activation should invoke a skill when appropriate instead of stuffing long memories into context.

## 2026-05-25 — Slice 30: `use_skill` logs skill activation telemetry

### Scope

Closed the Phase A gap where memory activations were logged, but skill invocations through the `use_skill` tool were invisible to the closed-loop telemetry stream.

### Files changed

- `apps/server/ntrp/skills/tool.py`
  - Added best-effort `skill_activation` access-event logging after a skill successfully loads.
  - Logged fields:
    - `task="use_skill_tool"`
    - `task_id`
    - `session_id`
    - `run_id`
    - `surface="skill"`
    - `skill_name`
    - `skill_args`
    - `skill_path`
  - Telemetry failure is non-fatal so skill loading does not break if memory services are unavailable.
- `apps/server/tests/test_skills.py`
  - Added regression coverage that `use_skill` records a `skill_activation` event with run/session/tool attribution.

### Behavior

Successful skill activation now leaves an auditable usage event:

```text
source = skill_activation
policy_version = skills.use.activation.v1
surface = skill
```

This satisfies the spec requirement that skill invocation is logged too, instead of only memory-object activations being visible.

### Validation

- `pytest apps/server/tests/test_skills.py::test_use_skill_records_activation_telemetry -q` → `1 passed`
- `pytest apps/server/tests/test_skills.py -q` → `6 passed`
- `python -m py_compile apps/server/ntrp/skills/tool.py` → passed
- `git diff --check` → passed

### Thermo review

- Kept telemetry in `_record_skill_activation(...)` instead of bloating `use_skill(...)`.
- Post-change size check:
  - `_record_skill_activation`: 23 lines
  - `use_skill`: 20 lines
  - no new giant class/function or cross-module private reach-in.
- Result: pass.

### Remaining gaps

- `skill_activation` events are logged, but the usage summary route currently focuses on `knowledge_activation` events. A later slice should expose skill activation history in review/debug views.
- Skill-first activation still needs runtime selection/invocation of approved skills for matching workflows.

## Slice 31 — Workflow-cluster skill promotion candidates

### Files changed

- `apps/server/ntrp/knowledge/skill_promotions.py`
  - Added workflow-cluster promotion alongside the existing single-lesson promotion path.
  - Lessons with shared `workflow_cluster_key`, `workflow_key`, or `task_pattern` metadata are grouped into one repeat-workflow candidate.
  - The candidate records:
    - `promotion_source = "workflow_cluster"`
    - `workflow_cluster_key`
    - `workflow_cluster_size`
    - `source_lesson_ids`
    - `source_episode_ids`
    - aggregate `success_count` and `helpful_count`
    - a `why_should_exist` explanation
  - Skill bodies now include all source lessons plus source memory/episode references, so review can see why the skill exists before approving it.
  - Kept the existing single-lesson threshold path working for legacy/current helpful/success metadata.
- `apps/server/tests/test_knowledge_write_gate.py`
  - Added regression coverage that three lessons from the same workflow cluster create one skill-promotion candidate, not three unrelated candidates.
  - Added duplicate protection coverage: rerunning the processor does not recreate the same workflow-cluster candidate.

### Behavior

Skill promotion is no longer only “one lesson got enough counters, propose a skill.” The processor can now mine an explicit repeated workflow cluster from multiple lessons and create a single review candidate with source links and an auditable rationale.

This is still deterministic/scaffolded mining — it uses workflow keys already present on lessons rather than doing full semantic episode clustering — but it closes a real gap in the closed-loop path: repeated workflow evidence can produce a skill draft with multiple sources.

### Validation

- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `19 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

### Thermo review

- Ran the configured thermo-nuclear review procedure for this slice using the review skill plus strict local inspection.
- Initial implementation had a too-fat `_propose_workflow_cluster_skill(...)`; refactored evidence aggregation and metadata construction into small helpers.
- Post-cleanup checks:
  - no function over 50 lines in `skill_promotions.py`
  - file remains ~379 lines
  - no UI hot-path work or live DB mutation
- Result: pass.

### Remaining gaps

- Workflow clustering still depends on lesson metadata keys; full mining from raw episodes/runs/tool traces remains pending.
- Approved skills are still review-created; runtime skill-first retrieval/invocation is still a separate gap.
- Review/debug views still need better visibility into `skill_activation` history.

## Slice 32 — Review/debug visibility for skill activation history

### Files changed

- `apps/server/tests/test_knowledge_routes.py`
  - Added regression coverage that `/knowledge/activation/usage-events?source=skill_activation` returns skill activation events with details such as `skill_name`, `surface`, `run_id`, `session_id`, and `tool_id`.
- `apps/desktop/src/api.ts`
  - Added typed `KnowledgeActivationUsageEvent` / `KnowledgeActivationUsageEventsResult` models.
  - Added `listKnowledgeActivationUsageEventsApi(...)` for the existing cheap usage-events endpoint.
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
  - Review now loads recent `skill_activation` events alongside memory usage summaries.
  - Added a small `SkillActivationList` component to show skill name, source/policy, timestamp, skill path, session/run/tool IDs.
  - Kept this on the existing cheap usage-events route; no health/consolidation hot-path expansion.

### Behavior

The Review tab can now show recent skill activations, so Slice 30's `use_skill` telemetry is visible/debuggable instead of silently sitting in raw access-event storage.

Historical events with missing detail fields are tolerated: the UI falls back to `unknown skill` and only renders optional path/session/run/tool labels when present.

### Validation

- `pytest apps/server/tests/test_knowledge_routes.py::test_activation_usage_events_can_list_skill_activation_history -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_routes.py -q` → `10 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

### Thermo review

- Ran the configured thermo-nuclear review procedure for this slice via strict local inspection.
- Initial UI pass inlined the skill activation renderer into the already-large Review pane; refactored it into `SkillActivationList` before accepting the slice.
- Kept backend surface unchanged because the existing `usage-events` endpoint already supports source filtering; adding a redundant endpoint would be worse.
- Result: pass.

### Remaining gaps

- The UI shows recent skill invocations, but runtime still does not automatically select and invoke approved skills ahead of prompt-stuffed memory.
- Full workflow mining from raw episodes/runs is still pending beyond Slice 31's keyed workflow-cluster promotion.

## Slice 33 — Activation bundle separates skill candidates from prompt-stuffed lessons

### Files changed

- `apps/server/ntrp/knowledge/activation_bundles.py`
  - Added `skills_to_consider` as an explicit activation bundle group.
  - Added `_is_skill_promotion_candidate(...)` so approved/active `action_candidate` objects with `metadata.promotion_kind = "skill"` are grouped as skill candidates instead of generic facts.
  - Existing prompt formatting still excludes `action_candidate`, so draft/approved skill candidates are visible in structured activation output without dumping skill-draft text into prompt context.
- `apps/server/tests/test_knowledge_activation.py`
  - Added regression coverage for skill-candidate grouping and no prompt stuffing.

### Behavior

Activation now has a real structured place for skill promotion candidates:

- `bundle.bundles["skills_to_consider"]` contains matching skill candidate memories.
- `prompt_context` does not include `<skills_to_consider>` or the skill draft body.
- Regular procedural lessons still appear under `procedural_lessons` and can be injected as before.

This closes a piece of the “future activation should prefer a skill candidate over dumping the whole playbook into context” path, without silently creating or invoking skills.

### Validation

- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_groups_skill_candidates_without_prompt_stuffing -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_activation.py -q` → `65 passed`
- `python -m compileall apps/server/ntrp/knowledge` → passed
- `git diff --check` → passed

### Thermo review

- Ran thermo-nuclear review for the slice.
- No broad refactor added; the new behavior is one bundle label plus one tiny predicate.
- The test is verbose because it builds realistic `KnowledgeObject` fixtures, but it is localized and documents the closed-loop contract.
- Result: pass.

### Remaining gaps

- Installed approved skills from the filesystem registry are still matched primarily through the system prompt/`use_skill` instruction path, not a separate activation scoring pipeline.
- The runtime still does not automatically invoke matched skills without model/tool selection.

## Slice 34 — Skill creation links back to all source memories, not only lessons

### Files changed

- `apps/server/ntrp/knowledge/skill_promotions.py`
  - Added helpers to collect source memory ids from candidate metadata and `knowledge:<id>` source refs.
  - Skill creation now appends a `skill_promotions` link to every available source memory for the candidate, not just `source_lesson_ids`.
- `apps/server/tests/test_knowledge_write_gate.py`
  - Expanded the skill creation regression so a source `memory_episode` referenced by the lesson also receives the skill linkback.

### Behavior

When a user approves a memory-derived skill candidate:

- the candidate is still approved and stamped with `skill_created_*` metadata;
- source lessons still get `metadata.skill_promotions[]`;
- source episodes / other knowledge memories referenced via `knowledge:<id>` now also get the same linkback;
- missing historical source refs are tolerated and skipped.

This makes the closed loop easier to audit: source memories can show which approved skill they helped produce.

### Validation

- `pytest apps/server/tests/test_knowledge_write_gate.py::test_approved_skill_promotion_creates_skill_and_links_source_memories -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `19 passed`
- `python -m compileall apps/server/ntrp/knowledge` → passed
- `git diff --check` → passed

### Thermo review

- Ran thermo-nuclear review for the slice.
- Kept source-id parsing in small helpers (`_knowledge_ref_ids`, `_skill_source_memory_ids`) instead of broadening the create method further.
- The create method still performs sequential read/update operations; acceptable for review-time skill creation, not a hot path.
- Result: pass.

### Remaining gaps

- Skill candidates now link back to source memories after approval, but there is still no automatic skill deprecation/update loop from later bad outcomes.
- Runtime skill invocation is still model/tool mediated rather than enforced by an activation matcher.

## Slice 35 — Outcome feedback writes spec metadata timestamps

### Files changed

- `apps/server/ntrp/memory/service.py`
  - `record_usage_outcome(...)` now writes the spec-level timestamp fields for usage outcomes:
    - `last_helpful_at`
    - `last_irrelevant_at`
    - `last_harmful_at`
    - `last_corrected_at`
  - Added `correction_count` alongside the existing `corrected_count` when correction feedback lands.
  - Replacement feedback decrements the correction alias when a prior correction outcome is replaced.
  - Extracted timestamp-field mapping into small helpers to avoid burying more branching inside the already-hot method.
- `apps/server/tests/test_knowledge_write_gate.py`
  - Added direct coverage for helpful + corrected/harmful outcome metadata.
  - Expanded correction-signal coverage to assert `correction_count` and `last_harmful_at`.

### Behavior

Outcome feedback now leaves enough per-memory metadata to audit whether a memory has recently helped, hurt, been irrelevant, or been corrected. A corrected harmful outcome stamps both correction and harm metadata, so correction flows no longer lose the harm timestamp.

### Validation

- `pytest apps/server/tests/test_knowledge_write_gate.py::test_usage_outcome_records_spec_metadata_counters_and_timestamps apps/server/tests/test_knowledge_write_gate.py::test_correction_signal_creates_review_candidate_and_marks_target -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `20 passed`
- `python -m compileall apps/server/ntrp/memory/service.py` → passed
- `git diff --check` → passed

### Thermo review

- Ran thermo-nuclear review for the slice, then refactored the counter/timestamp mapping into `_usage_outcome_timestamp_counters(...)` and `_apply_usage_outcome_timestamp_metadata(...)` so `record_usage_outcome(...)` did not absorb more inline condition soup.
- Result: pass.

### Remaining gaps

- Outcome metadata now has the requested counters/timestamps, but skill deprecation/update from repeated harmful skill outcomes is still not implemented.
- Outcome events are still represented as usage-event outcome fields plus per-object feedback detail, not a separate first-class outcome-event table.

## Slice 36 — Cache expensive processor snapshots off the Review hot path

Date: 2026-05-25

Files changed:
- `apps/server/ntrp/server/response_cache.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

Behavior implemented:
- Added a bounded async response cache for expensive read-only snapshots.
- `/knowledge/facts/consolidation` now returns a cached snapshot by default and accepts `refresh=true` for an explicit recompute.
- `/knowledge/processors/health` now returns a cached snapshot by default and accepts `refresh=true` for an explicit recompute.
- Cached responses include `cache.hit` and `cache.ttl_seconds` so the UI/debugger can tell whether a heavy processor actually reran.
- Fact consolidation commits invalidate the consolidation and processor-health cache scopes for the active memory service, so approved merges do not leave obviously stale snapshots around for the full TTL.
- Route inputs are bounded for consolidation (`limit` and `max_proposals`) before cache-key construction, avoiding accidental giant request shapes.

Why this slice matters:
- The closed-loop spec says expensive health/consolidation processors must not run on UI hot paths.
- This does not finish the proper background/materialized processor story, but it removes the worst “every Review visit recomputes the world” behavior and gives the UI/API an explicit refresh knob.

Thermo review result:
- Initial implementation had cache mechanics directly in `knowledge.py`; review flagged router-global cache complexity and unbounded key growth as maintainability risks.
- Fixed by extracting `AsyncResponseCache` into `ntrp.server.response_cache`, adding a bounded `max_entries`, pruning expired keys, and keeping router logic to cache-key + loader wiring.
- Remaining acceptable caveat: this is still per-process in-memory cache, not durable/background materialization. That is intentional for this slice and remains a later CL processor gap.

Validation:
- `pytest apps/server/tests/test_knowledge_routes.py::test_heavy_knowledge_response_cache_returns_snapshot_until_refresh apps/server/tests/test_knowledge_routes.py::test_heavy_knowledge_response_cache_invalidates_by_prefix_and_scope -q` → 2 passed.
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py -q` → 31 passed.
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_skills.py -q` → 103 passed.
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed.
- `git diff --check` → passed.
- `cd apps/desktop && npm run typecheck` → passed.

Remaining gaps:
- Move processor health/consolidation/duplicate/conflict detection to real background/materialized snapshots instead of first-request computation.
- Add UI affordance to display `cache.hit` and trigger `refresh=true` only on explicit user action.
- Continue workflow mining and skill-first runtime invocation work.

## Slice 37 — Expose cached processor snapshots in Review UI

Date: 2026-05-25

Files changed:
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

Behavior implemented:
- Added typed cache metadata for fact consolidation results: `cache.hit` and `cache.ttl_seconds`.
- `getKnowledgeFactConsolidationApi(...)` can now pass `refresh=true` to explicitly recompute the expensive backend snapshot.
- Review tab initial load uses the backend default cached snapshot path.
- Review tab manual Refresh and post-mutation reloads pass `refreshConsolidation: true`, so expensive recomputation is now tied to explicit user action or changed data instead of hidden background tab mounting.
- Duplicate-fact proposals now show a small “cached snapshot” / “fresh snapshot” pill when cache metadata is present.

Why this slice matters:
- Slice 36 gave the backend a cheap cached path and explicit refresh knob. This slice wires the UI to use that contract instead of blindly recomputing the heavy duplicate/conflict scan.

Thermo review result:
- Reviewed for accidental hidden recompute paths, stale UI confusion, and type drift.
- Kept the change deliberately small: no new polling, no new background task, no extra endpoint. The UI only passes one explicit refresh flag and renders existing cache metadata.
- Acceptable caveat: there is no dedicated desktop unit test runner script in `apps/desktop/package.json`; validation uses TypeScript checking and backend route tests for the cache contract.

Validation:
- `cd apps/desktop && npm run typecheck` → passed.
- `git diff --check` → passed.
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_skills.py -q` → 103 passed.
- Attempted `cd apps/desktop && npm test -- --run knowledgeViews.test.ts memoryTabs.test.ts` → failed because `apps/desktop/package.json` has no `test` script.

Remaining gaps:
- Add/standardize a desktop test runner script if UI interaction regressions need automated coverage.
- Replace per-process cache with background/materialized processor snapshots.
- Continue workflow-mining and skill-first invocation implementation.

## Slice 38 — Activation items now declare required/advisory/evidence roles

Date: 2026-05-25

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/activation_scoring.py`
- `apps/server/ntrp/knowledge/activation_bundles.py`
- `apps/server/tests/test_knowledge_activation.py`
- `apps/desktop/src/api.ts`

Behavior implemented:
- Added `selection_role` to `ActivationCandidate` and `ActivationSelectionTrace`.
- Role values are intentionally small and spec-aligned: `required`, `advisory`, `evidence_only`.
- Activation scoring now classifies objects by durable role:
  - facts → `required`
  - lessons/action candidates/skills-to-consider → `advisory`
  - artifacts and memory episodes → `evidence_only`
- Prompt context lines now include `role=<selection_role>` next to score/source/why, so the model sees whether a memory is something to trust/follow versus supporting evidence.
- Activation telemetry stores the same role in selection traces, including tool-surface activation events.
- Desktop API types now include `ActivationSelectionRole`, avoiding backend/frontend contract drift.

Why this slice matters:
- The closed-loop spec requires activation bundles to be intentional, not piles of similar memories. Each selected item now carries a compact role that says whether it is required, advisory, or evidence-only.
- This pairs with existing `score`, `rank`, `selection_reason`, `scope` reasons, and source summaries to make activation auditable and easier to judge later.

Thermo review result:
- Reviewed for enum/string risks, role derivation location, prompt bloat, and API drift.
- Kept the role derivation simple and deterministic in scoring; no LLM/judge path and no broad refactor.
- Fixed the main review catch: update desktop API typing so the new backend field is not invisible to TS callers.
- Remaining acceptable caveat: role derivation is type-based for now; future slices can refine it using object metadata or explicit source policy if needed.

Validation:
- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_marks_selection_roles_in_bundle_context_and_trace apps/server/tests/test_knowledge_activation.py::test_activation_context_groups_required_memory_bundles apps/server/tests/test_knowledge_activation.py::test_activation_groups_skill_candidates_without_prompt_stuffing apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects -q` → 4 passed.
- `pytest apps/server/tests/test_knowledge_activation.py -q` → 66 passed.
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_skills.py -q` → 84 passed.
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed.
- `git diff --check` → passed.
- `cd apps/desktop && npm run typecheck` → passed.

Remaining gaps:
- `used_by_model` is still a boolean derived from prompt-context inclusion; there is no nullable/unknown state yet.
- Workflow clusters are still lightweight candidates, not full cached workflow-cluster records with success/failure/correction counters.
- Skill-first invocation still needs runtime retrieval/use of approved skills instead of only skill-promotion telemetry/review.

## Slice 39 — `used_by_model` now has unknown semantics

Date: 2026-05-25

Files changed:
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/tests/test_knowledge_activation.py`

Behavior implemented:
- `ActivationSelectionTrace.used_by_model` is now nullable (`true | false | null`).
- Injected prompt-context items still record `used_by_model=true`.
- Omitted items still record `used_by_model=false`.
- Selected-but-not-injected items now record `used_by_model=null` instead of pretending they were definitely unused.
- This matters for skill candidates/action candidates and other structured selections that are intentionally not stuffed into the model prompt.

Why this slice matters:
- The closed-loop spec calls for honest use semantics. A selected object can be useful for routing/review/debug without being injected into the prompt; marking that as `false` smeared “not injected” into “not used.”
- Usage summaries already treat non-boolean values as unknown and only increment `used_by_model_count` on explicit `true`, so historical events remain readable and counters do not inflate.

Thermo review result:
- Reviewed nullability, counter semantics, Pydantic/API compatibility, and read-path tolerance.
- Kept the implementation deliberately small: no migration needed because event JSON already tolerates missing/non-boolean values and summaries already preserve unknown as `None`.
- No broad refactor needed; the semantics sit at the activation-trace boundary where selected/injected/omitted is already known.

Validation:
- `pytest apps/server/tests/test_knowledge_activation.py::test_activation_groups_skill_candidates_without_prompt_stuffing apps/server/tests/test_knowledge_activation.py::test_activation_marks_selection_roles_in_bundle_context_and_trace apps/server/tests/test_knowledge_activation.py::test_activation_records_access_events_not_feedback_objects -q` → 3 passed.
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_skills.py -q` → 84 passed.
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed.
- `git diff --check` → passed.
- `cd apps/desktop && npm run typecheck` → passed.

Remaining gaps:
- Activation bundles now carry role and honest unknown use state, but recall tool output still mostly returns prompt text rather than a first-class structured bundle to the model caller.
- Skill-first invocation remains underwired: approved skills can be surfaced/reviewed, but task routing still needs to actively invoke skill instructions when they match.

## Slice 40 — Recall tool returns a structured activation bundle payload

Date: 2026-05-25

Files changed:
- `apps/server/ntrp/tools/memory.py`
- `apps/server/tests/test_memory_tools.py`

Behavior implemented:
- `recall()` still returns the existing prompt-context text as `ToolResult.content`, so model-facing behavior stays compatible.
- `recall()` now also returns `ToolResult.data["activation_bundle"]` as the full JSON activation bundle.
- The structured payload includes candidates, omitted items, grouped bundles, selection traces, roles, reasons, scores, source IDs, and `used_by_model` semantics.
- The helper is typed against `ActivationBundle` and just uses `model_dump(mode="json")`; no bespoke/dynamic serialization mess.

Why this slice matters:
- The closed-loop spec requires actual recall payloads to carry why/source/role metadata, not only hidden telemetry.
- This gives downstream callers/debuggers the complete activation decision while preserving the concise prompt-context text for the model.

Thermo review result:
- Reviewed payload size/shape, helper abstraction, backward compatibility, and whether this creates spaghetti.
- Initial dynamic fallback helper was too loose; replaced it with a typed `ActivationBundle` serializer using Pydantic directly.
- No new hot-path scans or extra DB work; this reuses the already-built activation bundle.

Validation:
- `pytest apps/server/tests/test_memory_tools.py::test_recall_tool_passes_runtime_context_to_activation -q` → 1 passed.
- `pytest apps/server/tests/test_memory_tools.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_skills.py -q` → 86 passed.
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/tools/memory.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed.
- `git diff --check` → passed.
- `cd apps/desktop && npm run typecheck` → passed.

Remaining gaps:
- The model-facing content still excludes skill/action candidates from prompt stuffing by design; skill-first invocation still needs explicit runtime routing/use.
- Workflow clusters still need more durable cluster records and review UI affordances.

## Slice 41 — Promoted skills keep source lineage and activation telemetry reports it

Date: 2026-05-25

Files changed:
- `apps/server/ntrp/skills/service.py`
- `apps/server/ntrp/skills/tool.py`
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_skills.py`
- `apps/server/tests/test_knowledge_write_gate.py`

Behavior implemented:
- `SkillService.create(...)` now accepts optional `source=` and writes it into skill frontmatter when present.
- Creating a skill from a memory review candidate passes `source="knowledge:<candidate_id>"` into the skill file.
- `use_skill` activation telemetry now records:
  - `skill_location`
  - `skill_source` when present in frontmatter
- This lets a future skill activation be traced back to the approved memory-review candidate that created it.

Why this slice matters:
- Closed-loop learning should not end at “we created a skill somewhere.” A future `use_skill` event now carries source lineage back to the memory candidate, which links to source lessons/episodes/workflow clusters.
- This gives review/debug views a concrete chain: repeated workflow → action candidate → approved skill file → later skill activation.

Thermo review result:
- Reviewed protocol/API compatibility, frontmatter source injection risk, and whether lineage belongs in the skill file.
- Kept `source` optional/keyword-only so normal skill creation stays compatible.
- Sanitized source to one frontmatter line before writing to avoid accidental newline/frontmatter injection.
- No broad registry refactor needed because `SkillRegistry` already parses optional `source` into `SkillMeta`.

Validation:
- `pytest apps/server/tests/test_skills.py::test_use_skill_records_activation_telemetry apps/server/tests/test_knowledge_write_gate.py::test_approved_skill_promotion_creates_skill_and_links_source_memories -q` → 2 passed.
- `pytest apps/server/tests/test_skills.py apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_memory_tools.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py -q` → 106 passed.
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/skills apps/server/ntrp/tools/memory.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py` → passed.
- `git diff --check` → passed.
- `cd apps/desktop && npm run typecheck` → passed.

Remaining gaps:
- Skill activation telemetry now has source lineage, but runtime still relies on the model/tool system to call `use_skill`; no automatic skill router is implemented yet.
- Review UI could surface this lineage more explicitly in activation history.

### Slice 42 repair: restore fact-consolidation Review endpoints

**Date:** 2026-05-25

**Files changed**
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_fact_consolidation_routes.py`

**Behavior added / fixed**
- Restored the backend routes consumed by the Review pane after the frontend API surface was recovered:
  - `GET /knowledge/facts/consolidation`
  - `POST /knowledge/facts/consolidation/commit`
- The GET route now uses the shared heavy-endpoint cache, honors `refresh=true`, clamps abusive query bounds, and returns `cache.hit` / `cache.ttl_seconds` metadata.
- The Review payload is enriched with the UI fields it already expects (`canonical_id`, `canonical_title`, `canonical_text`, `duplicate_ids`, `duplicate_titles`) while keeping the canonical backend proposal fields intact.
- Commit invalidates only the current memory-service fact-consolidation cache scope, so post-merge refreshes recompute instead of showing stale duplicate proposals.

**Validation**
- `pytest apps/server/tests/test_knowledge_fact_consolidation_routes.py -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `87 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- Checked for the regression class that caused the UI break: frontend exports existed but the matching server routes were absent. Fixed with route-level tests instead of another untested adapter.
- Kept route logic small by putting enrichment in `_fact_consolidation_payload(...)` and reusing `AsyncResponseCache` instead of adding a second cache shape.
- Remaining known wart: `apps/desktop/src/api.ts` is still a large API aggregator; this repair did not make it worse structurally, but future API additions should avoid orphaning related types far from the knowledge API section.

**Remaining gaps**
- Resume closed-loop memory work with used/selected/injected/omitted semantics and skill-first activation behavior.

### Slice 43: structured skill-first activation suggestions

**Date:** 2026-05-25

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/activation_bundles.py`
- `apps/server/tests/test_knowledge_activation.py`
- `apps/desktop/src/api.ts`

**Behavior added / fixed**
- Activation bundles now expose structured `skills_to_use` suggestions instead of only hiding skill-first guidance inside rendered prompt text.
- Each suggestion includes `object_id`, `skill_name`, `description`, `score`, `reasons`, `source_ids`, and `selection_role`.
- Activation access-event details now persist the same structured skill suggestions plus a `skill_names_to_use` convenience list, so later review/debug tooling can see when retrieval wanted a skill invocation.
- The prompt `<skills_to_use>` block now formats from the same structured suggestion helper to avoid duplicated skill-name/description/source extraction logic.
- Desktop API types were updated so the inspect-activation response can consume `skills_to_use` without `any` drift.

**Validation**
- `pytest apps/server/tests/test_knowledge_activation.py -q` → `67 passed`
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `87 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- Initial implementation duplicated skill-name/description/source extraction between the structured payload and prompt renderer. Refactored prompt rendering to consume `skill_invocation_suggestions(...)` directly.
- Kept the new model small and purpose-specific (`ActivationSkillSuggestion`) instead of overloading `ActivationCandidate` or leaking full skill bodies into context.
- No new hot-path scans or Review-pane calls were added.

**Remaining gaps**
- Runtime still relies on model/tool instruction compliance to call `use_skill`; next slices should make skill-use telemetry/review visibility stronger and continue tightening selected/injected/omitted/actually-used semantics.

### Slice 44: disambiguate activation visibility from observed use

**Date:** 2026-05-25

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/usage_events.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_knowledge_activation.py`
- `apps/server/tests/test_knowledge_routes.py`
- `apps/desktop/src/api.ts`

**Behavior added / fixed**
- Activation traces now explicitly carry:
  - `activation_state`: `injected`, `selected_not_injected`, or `omitted`
  - `model_visible`: whether the object was actually supplied to the model-visible context/result
  - `actual_use_observed`: `None` for injected objects where usage cannot be proven from activation alone; `False` for selected-not-injected and omitted objects
- Existing `used_by_model` is preserved for compatibility, but the new fields make the semantics auditable instead of implying omitted/selected-only memory was used.
- Usage summaries now expose `model_visible_count`, `actually_used_count`, `last_activation_state`, `last_model_visible`, and `last_actual_use_observed`.
- Memory metadata written by `record_activation_usage(...)` stores the same latest activation-state/visibility fields.
- Read paths remain tolerant of historical usage events that lack the new fields; summaries fall back to `injected` for `model_visible_count` where needed.
- Desktop API types now include activation traces and the new usage-summary fields.

**Validation**
- `pytest apps/server/tests/test_knowledge_activation.py -q` → `67 passed`
- `pytest apps/server/tests/test_knowledge_routes.py -q` → `12 passed`
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `87 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- The important maintainability risk was semantic drift: another ambiguous boolean would make future review/debug tooling worse. Fixed by using one enum-like `activation_state` plus two direct booleans (`model_visible`, `actual_use_observed`) instead of trying to reinterpret legacy `used_by_model`.
- Historical tolerance is localized in summary aggregation (`model_visible` falls back to old `injected` only when the new field is missing), so old live events do not force write-path looseness.
- No hot-path processors or Review-pane calls were added.
- Known wart: `used_by_model` still exists as a legacy field and remains semantically imperfect. It should be treated as compatibility/debug data while new UI/workflow logic uses `activation_state` + `model_visible` + `actual_use_observed`.

**Remaining gaps**
- Wire Review/debug panes to display these clearer state fields where helpful.
- Add actual-use observation from outcome/citation/tool-result paths when there is real evidence; do not infer it merely from injection.

### Slice 45: show activation visibility semantics in Review usage summaries

**Date:** 2026-05-25

**Files changed**
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Review usage summaries now distinguish:
  - injected count
  - model-visible count
  - observed-used count
  - legacy used count only when it differs from the clearer model-visible count
- Latest attribution text now includes activation state, model visibility, and observed-use state when available.
- This makes omitted/selected-only memories visibly different from memories that were actually supplied to the model-visible context.

**Validation**
- `cd apps/desktop && npm run typecheck` → passed
- `pytest apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `87 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- Kept this as a display-only slice; no extra Review API calls and no hot-path processor changes.
- Avoided pretending `used_by_model_count` is trustworthy by showing it as `legacy-used` only when it diverges from the clearer `model_visible_count`.
- Wording is intentionally blunt/debug-oriented; future polish can make this nicer, but the core semantic distinction is now visible.

**Remaining gaps**
- Add real observed-use updates from evidence-bearing outcome paths; current activation-only events correctly report injected visibility as unknown actual use.

### Slice 46: mark observed actual use from explicit outcome feedback

**Date:** 2026-05-25

**Files changed**
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_memory_access_service.py`

**Behavior added / fixed**
- `MemoryAccessEventService.update_outcome(...)` now patches activation trace rows when explicit outcome feedback gives evidence of actual use.
- Conservative rule:
  - `helpful`, `harmful`, and `corrected` can mark `actual_use_observed=true`, but only for target objects that were model-visible/injected.
  - `irrelevant` marks targeted rows as `actual_use_observed=false`.
  - broad outcomes like `task_success` do not infer actual memory use.
- Selected-not-injected and omitted target rows remain `actual_use_observed=false` even if feedback targets them, because they were not supplied to the model-visible context.
- Patched events record `actual_use_signal` on the affected trace item and `actual_use_observed_target_object_ids` for visible targets where actual use was observed.

**Validation**
- `pytest apps/server/tests/test_memory_access_service.py -q` → `2 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `89 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- Kept inference deliberately narrow. The dangerous version would mark every successful task or every selected object as actually used; this slice only updates visible targets when the user/outcome signal is specific enough.
- Historical trace tolerance remains intact through `_trace_item_model_visible(...)`, which falls back across `model_visible`, `activation_state`, legacy `injected`, and legacy `used_by_model`.
- No Review hot-path calls were added. The summaries already read from event details, so the new evidence flows through existing usage-summary paths.
- New helper logic is isolated in `memory/service.py`; if it grows beyond outcome feedback it should move to a dedicated usage-event trace module.

**Remaining gaps**
- Propagate observed actual use into per-object metadata counters if we need object-level quality dashboards beyond event-derived usage summaries.
- Add observed-use updates from tool/citation paths if future traces can prove a memory was consumed without explicit user feedback.

### Slice 47: enrich skill activation visibility in Review

**Date:** 2026-05-25

**Files changed**
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Review skill activation rows now show the recorded activation surface, skill location, skill source, and truncated skill args in addition to skill path/session/run/tool IDs.
- This makes `use_skill` telemetry debuggable without opening raw JSON or guessing which skill variant/source was invoked.

**Validation**
- `cd apps/desktop && npm run typecheck` → passed
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `89 passed`
- `git diff --check` → passed

**Thermo review**
- Kept this as a cheap render-only change; it reuses already-fetched skill activation events and adds no API or processor load.
- Truncates args inline to avoid blowing up Review cards with prompt-sized skill args.
- No abstraction extracted because the display logic is still tiny; extracting now would be fake cleanliness.

**Remaining gaps**
- Skill-first runtime invocation is still not implemented; this only makes existing skill telemetry easier to audit.

### Slice 48: persist observed-use evidence into object metadata

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/memory/service.py`
- `apps/server/tests/test_memory_access_service.py`

**Behavior added / fixed**
- `record_usage_outcome(...)` now updates per-object actual-use metadata when explicit feedback proves a visible memory was actually used.
- New metadata fields:
  - `actual_use_observed_count`
  - `last_actual_use_observed`
  - `last_actual_use_observed_at`
  - `last_actual_use_signal`
  - `last_actual_use_outcome`
- The counter only increments when the feedback event matches the object’s latest activation event and `last_model_visible` is true. This prevents omitted or selected-not-injected memories from gaining actual-use credit just because feedback targeted them.
- Replacement/idempotency behavior decrements `actual_use_observed_count` when feedback changes from observed-use evidence (`helpful`/`harmful`/`corrected`/`used`/`wrong`) to non-use evidence (`irrelevant`/`not_helpful`).
- Usage-event trace patching now considers both `signal` and `outcome`, so a signal like `helpful` with generic `task_success` can still mark actual use when the target was model-visible.

**Validation**
- `pytest apps/server/tests/test_memory_access_service.py -q` → `5 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `92 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- Main risk was semantic overreach: object metadata could easily start counting “actual use” for every successful task. The implementation gates the counter on both explicit feedback evidence and matching latest model-visible activation event.
- Fixed a review finding before recording the slice: usage-event trace patching originally looked only at `outcome`; it now also respects explicit `signal`, matching the metadata path.
- Idempotency is handled for replacement feedback so observed-use counts do not grow when a Review action is edited.
- Known wart: using latest activation metadata means late feedback only works cleanly when the object’s latest activation is still the feedback event. That is intentionally conservative; if the object has since been activated elsewhere, this slice refuses to infer actual use rather than crediting the wrong event.

**Remaining gaps**
- If late feedback for older activation events matters, persist event-scoped visibility in the feedback object itself and derive object metadata from the event row instead of latest object metadata.
- Expose `actual_use_observed_count` in a future object-quality/dashboard view if useful.

### Slice 49: surface object-level use evidence in the Library inspector

**Date:** 2026-05-26

**Files changed**
- `apps/desktop/src/components/memory/KnowledgeLibraryPane.tsx`

**Behavior added / fixed**
- The selected object inspector now shows compact quality/use pills when metadata exists:
  - activation count
  - observed-use count
  - helpful count
  - harmful count
- Added a tiny metadata-number reader so malformed/historical non-number metadata does not render as bogus counts.
- This makes Slice 48’s object-level `actual_use_observed_count` visible without forcing users to open raw metadata JSON.

**Validation**
- `cd apps/desktop && npm run typecheck` → passed
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `92 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `git diff --check` → passed

**Thermo review**
- Kept it render-only; no new network request or expensive Review/Library path.
- Avoided repeating metadata extraction in JSX by computing selected-object counters once near `selected`.
- Historical metadata tolerance is explicit: only finite numeric metadata renders as a counter.
- This does not turn the Library into a full quality dashboard; it just exposes the strongest object-level closed-loop counters in the existing inspector.

**Remaining gaps**
- A future quality dashboard could sort/filter by observed-use/helpful/harmful ratios, but that should be a separate slice with API support rather than a heavy client-side scan.

### Slice 50: structured recall bundle payloads

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/activation_bundles.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/tests/test_knowledge_activation.py`
- `apps/desktop/src/api.ts`

**Behavior added / fixed**
- Activation responses now expose `recall_bundle`, a machine-readable structured bundle split into:
  - `facts`
  - `lessons`
  - `artifacts`
  - `episodes`
  - `warnings`
  - `skills`
- `recall_bundle.skills` reuses the existing approved `skills_to_use` suggestions, so skill-first guidance is structured instead of only embedded in prompt text.
- Access-event telemetry now stores compact `recall_bundle_ids` for the same groups, avoiding duplicated full candidate payloads while preserving attribution/debuggability.
- Desktop API types now include `ActivationRecallBundle` and the `recall_bundle` field.

**Validation**
- `pytest apps/server/tests/test_knowledge_activation.py -q` → `67 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py -q` → `92 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `git diff --check` → passed

**Thermo review**
- Ran the configured thermo-nuclear review skill plus strict local diff inspection.
- Finding fixed during review: the first pass duplicated the group-to-id mapping inline in `activation.py`; extracted `recall_bundle_object_ids(...)` in `activation_bundles.py` so structured recall grouping and compact telemetry stay centralized.
- No remaining slice-local maintainability blocker found.

**Remaining gaps**
- This is structured payload/readability work only; it does not yet implement real runtime skill invocation.
- Follow-up should wire skill-first runtime invocation so approved skills are actually invoked when activation selects them, rather than merely suggested in context.

### Slice 51: prompt-time runtime activation for selected skills

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/skills/registry.py`
- `apps/server/ntrp/skills/tool.py`
- `apps/server/ntrp/services/chat.py`
- `apps/server/tests/test_skills.py`

**Behavior added / fixed**
- Added `SkillRegistry.render_skill_xml(...)` as the single renderer for full skill-body XML, including `<skill_path>` substitution and optional argument labeling.
- `use_skill` now uses the registry renderer instead of hand-building skill XML.
- Chat activation now auto-injects the full body of the top activated approved skill from `bundle.skills_to_use` into a new `<activated_skills>` block in memory context.
- The activated skill body receives the current user request as runtime arguments, so chat can follow the selected skill immediately instead of only seeing a long advisory memory note.
- Slash-command skill expansion now reuses the same registry renderer, preserving the existing `User request: ...` label.

**Validation**
- `pytest apps/server/tests/test_skills.py -q` → `8 passed`
- `pytest apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `9 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `95 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the first implementation.
- Finding fixed during review: skill XML construction was still duplicated between `use_skill`, chat auto-activation, and slash-command expansion. Refactored all three through `SkillRegistry.render_skill_xml(...)`.
- No remaining slice-local maintainability blocker found.

**Remaining gaps**
- This is chat-surface prompt-time skill activation only; operator/background surfaces still only receive skill suggestions unless they explicitly call `use_skill`.
- Auto-activation telemetry currently rides on the activation access event (`skills_to_use` / `recall_bundle_ids`); a follow-up should add a distinct `skill_activation` event for auto-injected skills so Review can separate explicit tool calls from prompt-time auto-activation.

### Slice 52: telemetry for prompt-time auto-activated skills

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/services/chat.py`
- `apps/server/tests/test_skills.py`

**Behavior added / fixed**
- Chat prompt-time skill activation now records a distinct `skill_activation` access event with policy `skills.auto_activation.v1`.
- The event links the auto-activated skill back to:
  - the chat task/client id
  - session id
  - run id
  - triggering activation usage event id
  - triggering skill-promotion memory object id
  - selection score/reasons
  - skill path/location/source
- The prompt-time activated skill entries are computed once and reused for both context injection and telemetry, avoiding duplicate skill-body loading.

**Validation**
- `pytest apps/server/tests/test_skills.py -q` → `9 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `96 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- Finding fixed during review: initial telemetry code re-rendered/reloaded the selected skill after context rendering. Refactored to compute `_activated_skill_entries(...)` once, format context from those entries, and pass the same entries to telemetry.
- No remaining slice-local maintainability blocker found.

**Remaining gaps**
- Operator/background prompt surfaces still do not auto-inject selected skill bodies or record `skills.auto_activation.v1` events.
- Review UI can show generic skill activation cards, but it does not yet label auto-activation vs explicit `use_skill` as separate subtypes beyond the policy/source/details fields.

## Slice 53 — operator prompt auto-activates selected skills

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/skills/activation.py`
- `apps/server/ntrp/services/chat.py`
- `apps/server/ntrp/operator/runner.py`
- `apps/server/ntrp/server/runtime/core.py`
- `apps/server/tests/test_operator_activation_context.py`
- `apps/server/tests/test_skills.py`

**Behavior added / fixed**
- Extracted shared skill auto-activation helpers into `ntrp.skills.activation` so chat and operator prompt surfaces use the same code path for:
  - selecting/rendering the top approved activated skill body
  - appending `<activated_skills>` to memory context
  - recording `skill_activation` telemetry with policy `skills.auto_activation.v1`
- Operator prompt preparation now auto-injects the top selected approved skill into the system memory context when activation returns `skills_to_use`.
- Operator auto-activation telemetry records:
  - `task=operator_prompt_auto_skill_activation`
  - `activation_surface=operator_prompt`
  - operator task/source id, session id, run id
  - triggering activation usage event id
  - triggering skill-promotion memory object id
  - selection score/reasons
  - skill path/location/source
- Runtime dependency wiring now passes the shared `SkillRegistry` into `OperatorDeps`.
- Chat auto-activation kept the same behavior, but now calls the shared helper instead of owning chat-local duplicated helpers.

**Validation**
- `pytest apps/server/tests/test_operator_activation_context.py apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `11 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `97 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- Findings fixed during review:
  - Removed chat-local duplicated auto-activation rendering/telemetry helpers in favor of `ntrp.skills.activation`.
  - Removed obsolete chat wrapper functions after tests were moved to the shared helper.
  - Changed the shared helper's `MemoryService` import to `TYPE_CHECKING` so the skills package does not take a runtime dependency on memory service internals just for a type hint.
- No remaining slice-local maintainability blocker found.

**Remaining gaps**
- Background/non-operator autonomous surfaces still need explicit inspection before broadening skill auto-activation there; this slice intentionally covered only operator prompt preparation.
- Review UI can show skill activation details, but it still does not label explicit `use_skill`, chat auto-activation, and operator auto-activation as first-class subtypes.

## Slice 54 — Review UI labels skill activation subtypes

**Date:** 2026-05-26

**Files changed**
- `apps/desktop/src/lib/knowledgeViews.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
- `apps/desktop/tests/knowledgeViews.test.ts`

**Behavior added / fixed**
- Added `skillActivationSubtypeLabel(...)` so Review skill activation cards distinguish:
  - explicit `use_skill` telemetry (`skills.use.activation.v1`)
  - chat prompt auto-activation (`skills.auto_activation.v1`, `activation_surface=chat_prompt`)
  - operator prompt auto-activation (`skills.auto_activation.v1`, `activation_surface=operator_prompt`)
  - future auto-activation surfaces via a generic humanized fallback
- Review skill activation cards now show the subtype label as the primary pill instead of the generic `skill_activation` source.
- Auto-activation cards now surface the triggering activation usage event id and triggering skill-promotion memory object id when present.
- Review detail rendering now accepts numeric/boolean telemetry details, so numeric event ids are visible instead of silently disappearing.

**Validation**
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `4 pass`
- `cd apps/desktop && npm run typecheck` → passed
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `97 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- No structural blocker found: subtype policy logic is isolated in `knowledgeViews.ts`, covered by a focused test, and the Review pane only renders the derived label and IDs.
- Kept this as a UI/read-model slice; no backend telemetry shape changes were needed.

**Remaining gaps**
- Background/non-operator autonomous surfaces still need explicit inspection before broadening skill auto-activation there.
- Skill activation cards now label subtype and source links, but there is still no filtering/grouping by subtype in Review.

## Slice 55 — background tool auto-activates selected skills

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/tools/background.py`
- `apps/server/tests/test_background_agent_runs.py`
- `apps/desktop/tests/knowledgeViews.test.ts`

**Behavior added / fixed**
- The `background` tool now performs prompt-surface knowledge activation before spawning the child background agent when memory service is available.
- Background child system prompts now append the activation prompt context plus `<activated_skills>` for the top selected approved skill, using the same shared helper as chat/operator.
- Background auto-activation telemetry records a distinct `skill_activation` event with policy `skills.auto_activation.v1` and:
  - `task=background_prompt_auto_skill_activation`
  - `activation_surface=background_prompt`
  - background tool id, session id, run id
  - triggering activation usage event id
  - triggering skill-promotion memory object id
  - selection score/reasons and skill path/location/source
- Added a focused background-tool regression test that verifies activation request IDs, prompt injection, and telemetry linkage.
- Extended the Review label test to cover the new `background_prompt` auto-activation subtype fallback.

**Validation**
- `pytest apps/server/tests/test_background_agent_runs.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `14 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `100 passed`
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `4 pass`, `13 expect() calls`
- `cd apps/desktop && npm run typecheck` → passed
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- No remaining structural blocker found: background uses the same `ntrp.skills.activation` rendering/telemetry helper as chat/operator, and the new prompt builder is isolated from spawn execution.
- Kept the slice intentionally scoped to the `background` tool; research already has separate memory context behavior and should be reviewed separately before changing its prompt contract.

**Remaining gaps**
- Research subagents still only receive selected user facts, not full skill auto-activation; that path needs a separate design decision because research has its own prompt template and ledger helpers.
- Skill activation cards label subtypes but still lack filtering/grouping by subtype.

## Slice 56 — research subagents auto-activate selected skills

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/tools/research.py`
- `apps/server/tests/test_research_tools.py`

**Behavior added / fixed**
- Research subagent prompt construction now runs task-specific knowledge activation using the actual research task text instead of only the generic `user identity preferences current projects` query.
- Research prompt memory activation is now recorded with `surface=prompt`, because the selected memory is rendered into the child research agent's system prompt, not merely returned as a parent-tool output.
- Research prompts now append `<activated_skills>` for the top selected approved skill, using the shared `ntrp.skills.activation` helper already used by chat/operator/background.
- Research auto-activation telemetry records a distinct `skill_activation` event with policy `skills.auto_activation.v1` and:
  - `task=research_context_auto_skill_activation`
  - `activation_surface=research_context`
  - research tool id, session id, run id
  - triggering activation usage event id
  - triggering skill-promotion memory object id
  - selection score/reasons and skill path/location/source
- Added a focused regression test verifying task-specific activation query, prompt-surface attribution, skill XML injection, and telemetry linkage.

**Validation**
- `pytest apps/server/tests/test_research_tools.py -q` → `9 passed`
- `pytest apps/server/tests/test_research_tools.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `23 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_research_tools.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `109 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- Found and fixed one attribution issue: research context had historically logged `surface=tool`, but the selected memory is model-visible inside the spawned research agent's system prompt. The slice now records it as `surface=prompt`.
- No remaining structural blocker found: research uses the shared auto-activation rendering/telemetry helper instead of adding a fourth custom skill-injection path.

**Remaining gaps**
- Research still renders activated memory as a simple `USER CONTEXT` list rather than reusing the full structured `prompt_context` / `recall_bundle` output; that should be a separate slice because it changes research prompt shape more broadly.
- Skill activation Review UI still labels subtypes but lacks filter/group controls.

## Slice 57 — Review filters skill activation telemetry by subtype

**Date:** 2026-05-26

**Files changed**
- `apps/desktop/src/lib/knowledgeViews.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
- `apps/desktop/tests/knowledgeViews.test.ts`

**Behavior added / fixed**
- Added stable skill activation subtype keys for the Review control plane:
  - `explicit`
  - `chat_auto`
  - `operator_auto`
  - `background_auto`
  - `research_auto`
  - `other_auto`
  - `other`
- Review skill activation cards now expose count-bearing filter chips so explicit `use_skill`, chat auto-activation, operator auto-activation, background auto-activation, and research auto-activation can be inspected separately.
- Kept the existing human-readable subtype labels, and added a `research_context` label/key for the research auto-activation telemetry introduced in Slice 56.
- Added focused tests for subtype filter coverage and key assignment.

**Validation**
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `cd apps/desktop && npm run typecheck` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- No structural blocker found: subtype classification lives in `knowledgeViews.ts`, so the Review component does not duplicate policy/surface string logic.
- The UI filter state is local and non-persistent by design; no backend contract change needed.

**Remaining gaps**
- Review still does not show a grouped aggregate trend chart for skill activation outcomes; it only filters recent activation events.
- Research prompt memory rendering still uses a simple `USER CONTEXT` list rather than structured recall bundles.

## Slice 58 — research renders the logged activation prompt context

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/tools/research.py`
- `apps/server/tests/test_research_tools.py`

**Behavior added / fixed**
- Research subagent prompts now render `ActivationBundle.prompt_context` directly instead of independently flattening `bundle.candidates` into a separate `USER CONTEXT` bullet list.
- This makes the child research prompt match what activation telemetry records as injected/model-visible memory.
- It also preserves the structured activation bundle sections (`<skills_to_use>`, facts, lessons, artifacts, warnings, etc.) instead of smearing all candidates into flat text.
- Added a focused assertion that research prompts include the activation `prompt_context` alongside the full auto-activated skill body.

**Validation**
- `pytest apps/server/tests/test_research_tools.py -q` → `9 passed`
- `pytest apps/server/tests/test_research_tools.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_skills.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `23 passed`
- `pytest apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_research_tools.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `109 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- No structural blocker found: this removes duplicate research-only candidate rendering and relies on the same activation bundle formatting that telemetry already attributes.
- Kept the slice narrow: no changes to activation bundle formatting itself.

**Remaining gaps**
- Workflow mining is still mostly promotion-side clustering over lessons with explicit workflow metadata; it does not yet mine repeated workflows from raw usage traces/episodes.
- Review has subtype filters for skill activation events, but no aggregate trend chart.

## Slice 59 — workflow promotion infers clusters from repeated task metadata

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- Workflow skill promotion no longer requires lessons to carry an explicit `workflow_cluster_key` / `workflow_key` / `task_pattern` field.
- The promotion miner now also derives cluster keys from repeated task/workflow title metadata:
  - `workflow_title`
  - `task_title`
  - `task_name`
  - `task`
- This keeps the miner strict enough to avoid random title clustering: lessons still need repeated matching metadata and aggregated evidence (`success_count` / helpful evidence) to pass `min_successes`.
- Added a focused regression test where three successful lessons with the same `task_title` produce one workflow skill promotion candidate with `promotion_source=workflow_cluster`.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_creates_skill_promotion_candidate apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_infers_skill_promotion_from_repeated_task_title -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_research_tools.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `130 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- No structural blocker found: inference is limited to workflow/task metadata and still uses the existing cluster evidence gate, duplicate suppression, review-only `action_candidate` output, and skill promotion approval flow.
- Deliberately did not cluster arbitrary lesson titles; that would be noisy as hell.

**Remaining gaps**
- There is still no persisted `workflow_clusters` table/snapshot with `failure_count`, `correction_count`, and lifecycle status.
- The miner does not yet cluster directly from raw usage events or episodes unless those paths first emit lessons with stable task/workflow metadata.

## Slice 60 — workflow candidates carry failure and correction evidence

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- Workflow-cluster skill promotion candidates now aggregate negative/correction evidence as well as positive evidence.
- Candidate metadata now includes:
  - `failure_count`
  - `correction_count`
- `correction_count` accepts either `correction_count` or legacy-ish `corrected_count` on source lessons, taking the max per lesson to avoid double-counting alternate field names.
- `why_should_exist` now includes machine-readable count labels (`success_count=...`, `helpful_count=...`, `failure_count=...`, `correction_count=...`) instead of only a positive-outcome summary.
- Updated the workflow-cluster regression test to verify failure/correction aggregation.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_creates_skill_promotion_candidate apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_infers_skill_promotion_from_repeated_task_title -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_research_tools.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `130 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review on the slice.
- Fixed one wording smell during review: `why_should_exist` now uses explicit count labels instead of grammatically fragile prose like `1 failures`.
- No structural blocker found; this reuses the existing metadata-based evidence path and does not mutate source lessons.

**Remaining gaps**
- No persisted/cached `workflow_clusters` snapshot yet.
- Failure/correction counts depend on upstream lessons carrying those metadata fields; raw usage events are not mined directly yet.

## Slice 61 — derived workflow cluster snapshot/control-plane endpoint

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/__init__.py`
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/ntrp/knowledge/processors.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- Added a derived workflow-cluster snapshot model:
  - `KnowledgeWorkflowCluster`
  - `KnowledgeWorkflowClusterResult`
- Added `KnowledgeSkillPromotionService.list_workflow_clusters(...)` and processor wrapper `KnowledgeProcessorService.workflow_clusters(...)`.
- Added cached API endpoint:
  - `GET /knowledge/processors/workflow-clusters`
  - query params: `limit`, `min_successes`, `include_below_threshold`, `refresh`
- Snapshot entries expose control-plane evidence without creating candidates:
  - `key`
  - `title`
  - `promotion_status`: `ready | candidate_exists | below_threshold`
  - `lesson_count`
  - `source_lesson_ids`
  - `source_episode_ids`
  - `success_count`
  - `helpful_count`
  - `failure_count`
  - `correction_count`
  - `has_skill_candidate`
  - `skill_candidate_ids`
  - `why_should_exist`
- Reused the same workflow clustering helper for promotion and snapshot paths to avoid two subtly different miners.
- Candidate lookup now normalizes historical/raw `workflow_cluster_key` values with the same slugger used for lesson clustering, so duplicate suppression/status linking is less brittle.
- Fixed a thermo-found accounting smell in workflow candidate metadata:
  - skill body is still capped to the top 8 lessons for readability;
  - `workflow_cluster_size` and `source_lesson_ids` now preserve the full cluster, not just the capped skill-body subset;
  - added `skill_body_lesson_ids` to make that cap explicit.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_exposes_ready_and_existing_candidates apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_candidate_keeps_full_source_count_when_skill_body_is_capped -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_fact_consolidation_routes.py apps/server/tests/test_skills.py apps/server/tests/test_operator_activation_context.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_research_tools.py apps/server/tests/test_chat_inject.py::test_expand_skill_command_injects_skill_path -q` → `132 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the initial implementation and again after fixes.
- Fixed the concrete issue identified during review: candidate metadata previously risked reporting a capped cluster as the full cluster once there were more than eight source lessons.
- No remaining structural blocker found for this slice: snapshot is derived/cached, promotion remains review-only, and clustering logic is shared instead of forked.

**Remaining gaps**
- This is a derived snapshot, not a persisted `workflow_clusters` table with durable lifecycle history.
- The workflow miner still depends on lessons/action candidates; it does not directly mine raw usage-event sequences yet.
- Review UI does not yet expose the workflow cluster snapshot endpoint.

## Slice 62 — Review UI exposes workflow cluster snapshots

**Date:** 2026-05-26

**Files changed**
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Added desktop API types for workflow cluster snapshots:
  - `KnowledgeWorkflowCluster`
  - `KnowledgeWorkflowClusterResult`
- Added `getKnowledgeWorkflowClustersApi(...)` for `GET /knowledge/processors/workflow-clusters`.
- Review pane now loads the workflow-cluster snapshot alongside fact consolidation and usage telemetry.
- Review pane renders a **Workflow skill clusters** section showing:
  - promotion status (`ready`, `candidate_exists`, `below_threshold` if returned)
  - lesson count
  - success/helpful/failure/correction counts
  - source `knowledge:*` IDs
  - existing candidate IDs when a skill proposal already exists
  - cached/fresh snapshot label
- Header pending count now includes ready workflow clusters so repeated workflows are visible before a candidate is manually created.
- Renamed the Review reload option from `refreshConsolidation` to `refreshSnapshots` after thermo review because the refresh now applies to multiple cached processor snapshots, not just fact consolidation.

**Validation**
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- Server regression carried from Slice 61 after endpoint addition:
  - `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_exposes_ready_and_existing_candidates apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_candidate_keeps_full_source_count_when_skill_body_is_capped -q` → `2 passed`
  - Full focused suite → `132 passed`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the UI/API slice and again after the naming fix.
- Fixed the concrete naming smell: `refreshConsolidation` became `refreshSnapshots` so the option no longer lies about what it refreshes.
- No remaining structural blocker found for this UI slice. It reuses the heavy endpoint cache and does not put raw workflow mining on the UI hot path.

**Remaining gaps**
- The UI can view workflow clusters but cannot directly create/approve a workflow skill from a ready cluster; proposal creation still happens through the existing processor/action-candidate path.
- Workflow clusters are still derived snapshots, not persisted lifecycle records.

## Slice 63 — Review UI can create workflow skill proposal candidates

**Date:** 2026-05-26

**Files changed**
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Added desktop API type `KnowledgeSkillPromotionResult`.
- Added `proposeKnowledgeSkillPromotionsApi(...)` for `POST /knowledge/processors/skill-promotions`.
- Review pane now shows a **Create proposals** action when workflow clusters include ready clusters.
- The action runs the existing skill-promotion processor with the same evidence gate (`min_successes=3`), creates draft action candidates, then refreshes cached Review snapshots.
- Review pane now displays a small result summary (`created N; skipped M`) after the processor runs.

**Validation**
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_exposes_ready_and_existing_candidates apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_candidate_keeps_full_source_count_when_skill_body_is_capped -q` → `2 passed`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review for the UI proposal action.
- No structural blocker found: the button calls an existing evidence-gated draft-candidate processor, does not approve/publish skills, and reloads cached snapshots after mutation.
- Added explicit result feedback so the user can see whether proposals were created or skipped.

**Remaining gaps**
- Proposal creation is still batch-level for all ready workflow clusters rather than one-click per cluster.
- Workflow cluster lifecycle is still snapshot-derived; there is no persisted cluster approval state beyond the resulting action candidate objects.

## Slice 64 — Workflow clusters include raw activation usage-event evidence

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Workflow cluster snapshots now mine raw `MemoryAccessEvent` telemetry in addition to lesson metadata.
- Event mining extracts cluster keys from activation-event details:
  - `workflow_cluster_key`
  - `workflow_key`
  - `task_pattern`
  - `workflow_title`
  - `task_title`
  - `task_name`
  - `task`
- Raw activation event evidence now contributes to cluster counts:
  - `success_count`
  - `helpful_count`
  - `failure_count`
  - `correction_count`
- Added snapshot fields:
  - `usage_event_count`
  - `source_usage_event_ids`
- Review UI now displays usage event counts and event IDs alongside lesson sources.
- A cluster can become ready when it has at least two promotable lessons plus enough combined lesson/event success evidence.
- Event-only clusters remain non-promotable unless there are enough lesson sources; we avoid creating skills sourced only from raw telemetry.

**Thermo review fix**
- Initial version scanned `access_events.list_recent(source=None)` and keyed any event with task-ish metadata.
- Thermo review flagged false-positive clustering risk from non-activation access events.
- Fixed by accepting only events whose `policy_version` starts with `knowledge.activation`.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_adds_raw_usage_event_evidence -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_exposes_ready_and_existing_candidates apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_adds_raw_usage_event_evidence apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_candidate_keeps_full_source_count_when_skill_body_is_capped -q` → `3 passed`
- Focused server suite → `133 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Remaining gaps**
- Event scan is cached at the route level, but cluster lifecycle itself is still snapshot-derived and not persisted.
- Raw telemetry can strengthen an existing lesson-backed workflow cluster; it still does not synthesize the missing lesson/playbook by itself.

## Slice 65 — Workflow skill proposals preserve usage-event evidence

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- `propose_skill_promotions(...)` now mines activation usage-event workflow evidence once and passes it into workflow-cluster proposal creation.
- Draft workflow skill candidates now preserve raw telemetry evidence in metadata:
  - `usage_event_count`
  - `source_usage_event_ids` (capped to 25 IDs)
  - merged `success_count`, `helpful_count`, `failure_count`, `correction_count`
- `why_should_exist` now includes `usage_event_count`, so Review can explain why a workflow proposal exists when raw activation telemetry helped it pass the threshold.
- Added regression coverage that non-activation access events with task-ish metadata are ignored, preventing unrelated tool access logs from inflating workflow evidence.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_adds_raw_usage_event_evidence -q` → `1 passed`
- Focused server suite → `133 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the proposal metadata slice.
- No blocker found after adding the non-activation-event guard test.
- Current shape is intentionally conservative: raw telemetry can strengthen a lesson-backed workflow, but cannot create a skill candidate with no lesson/body source.

**Remaining gaps**
- Snapshot/proposal cluster lifecycle is still derived, not persisted as first-class cluster records.
- Per-cluster one-click proposal creation is still absent; Review creates all ready draft proposals through the existing batch processor.

## Slice 66 — Workflow clusters carry artifact provenance and clean episode refs

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Workflow clusters now expose `source_artifact_ids` alongside source lessons, episodes, and usage events.
- Workflow skill candidate metadata now includes `source_artifact_ids`; candidate `source_ids` and generated `SKILL.md` body include artifact provenance.
- `source_episode_ids` now only comes from explicit episode metadata or `episode:` / `memory_episode:` refs. It no longer mislabels generic `knowledge:`, `run:`, or `turn:` refs as episode IDs.
- Review UI now displays workflow cluster episode and artifact chips, so the operator can see more than just source lesson IDs before creating proposals.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_exposes_ready_and_existing_candidates -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_routes.py -q` → `36 passed`
- Focused server suite → `133 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the provenance slice.
- No blocker found.
- Ordering is deterministic through sorted workflow lessons; provenance lists remain capped to avoid metadata bloat.

**Remaining gaps**
- Workflow clusters are still derived/cached snapshots, not durable first-class records with reviewed/promoted/rejected/stale lifecycle.
- Workflow miner still does not extract tool/action sequences from traces; it uses lesson metadata/source refs plus activation usage-event task metadata.

## Slice 67 — Workflow clusters are scope-aware with stable IDs

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Workflow clusters now have stable scope-aware IDs shaped like `<scope>:<workflow-slug>` and expose both `id` and `scope` through the backend model/API.
- Lesson-backed workflow mining no longer collapses same-title workflows from different scopes/projects into one cluster.
- Skill promotion candidates now store `metadata.workflow_cluster_id`, while keeping legacy `workflow_cluster_key` for compatibility/debuggability.
- Duplicate skill-candidate detection checks the stable `workflow_cluster_id` first and falls back to legacy key matching for older candidates.
- Review UI uses the stable cluster `id` as the React key/display instead of the slug-only workflow key.
- Unscoped historical usage-event evidence still strengthens a single matching scoped lesson cluster, but is ignored when the same workflow key is ambiguous across multiple scopes. That avoids smearing one raw activation event across multiple projects.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_are_scope_aware -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `25 passed`
- Focused server suite → `134 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the scope-aware cluster slice.
- Review flagged the subtle leakage risk from unscoped historical usage evidence when multiple scopes share the same workflow key; fixed by ignoring unscoped fallback for ambiguous keys.
- Re-ran thermo review after that fix; no remaining blocker.

**Remaining gaps**
- Workflow clusters are still cached/derived snapshots, not durable records with reviewed/promoted/rejected/stale lifecycle state.
- Usage-event mining still relies on task/workflow metadata; it does not yet mine concrete tool/action sequences.

## Slice 68 — Workflow clusters expose recency (`last_seen_at`)

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Workflow cluster snapshots now expose `last_seen_at`.
- `last_seen_at` is derived from the newest lesson update timestamp plus any activation usage-event timestamp attached to the cluster.
- Workflow skill candidate metadata also stores `last_seen_at`, so Review-created proposals carry the same recency evidence.
- Review UI displays a lightweight “last seen” pill for workflow clusters.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `25 passed`
- Focused server suite → `134 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the recency slice.
- No blocker found.
- Kept this as cached snapshot metadata only; no durable cluster lifecycle state yet.

**Remaining gaps**
- Workflow clusters still do not persist reviewed/promoted/rejected/stale lifecycle state.
- The miner still does not derive workflow recency from tool/action traces beyond activation usage events and lesson updates.

## Slice 69 — Legacy workflow candidate fallback no longer smears across scopes

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- Legacy skill candidates that only have slug-only `metadata.workflow_cluster_key` no longer mark every same-title scoped workflow cluster as `candidate_exists`.
- The legacy fallback is still honored when a workflow key is unambiguous, but ignored when the same workflow key appears in multiple scopes.
- Removed an accidental extra `cluster_id=` kwarg from `KnowledgeWorkflowCluster(...)`; the model already has the canonical `id` field.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_ambiguous_legacy_workflow_candidate_key_does_not_block_scoped_clusters -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `26 passed`
- Focused server suite → `135 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the fallback-scope fix.
- No blocker found.

**Remaining gaps**
- Legacy slug-only candidates can still be ambiguous historical debt; they are intentionally not used to block scoped clusters when ambiguity exists.
- Durable workflow cluster lifecycle is still not implemented; this only makes the cached snapshot safer.

## Slice 70 — Workflow clusters expose lifecycle status and honor rejected proposals

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Cached workflow cluster snapshots now expose a spec-aligned lifecycle `status`: `candidate`, `reviewed`, `promoted`, `rejected`, or `stale`.
- Lifecycle status is derived from linked workflow skill `action_candidate` records:
  - approved candidates with created skill metadata → `promoted`;
  - draft candidates or threshold-ready clusters → `candidate`;
  - approved candidates without created skill metadata → `reviewed`;
  - rejected candidates → `rejected`;
  - below-threshold clusters → `stale`.
- Rejected workflow skill candidates now participate in duplicate detection, so rejected workflow proposals are not immediately re-created and re-spammed.
- Review API types and UI now surface the lifecycle status pill next to the existing promotion status.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_rejected_workflow_skill_candidate_blocks_reproposal_and_marks_cluster_rejected -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `27 passed`
- Focused server suite → `136 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the lifecycle-status slice.
- No blocker found.

**Remaining gaps**
- Workflow lifecycle state is still derived from `action_candidate` records in cached snapshots, not persisted in a dedicated `workflow_clusters` table.
- `stale` is currently below-threshold-derived; there is no time-based stale detection yet.

## Slice 71 — Workflow clusters expose summary, trigger, and metadata

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`

**Behavior added / fixed**
- Workflow cluster snapshots now include spec-aligned descriptive fields:
  - `summary`
  - `trigger_description`
  - `metadata`
- `summary` gives a compact repeated-workflow evidence sentence with lesson/usage-event/outcome counts.
- `trigger_description` states what task/scope shape should match the workflow.
- `metadata` carries canonical debug fields: `workflow_cluster_id`, `workflow_cluster_key`, `scope`, lifecycle status, promotion status, and linked skill candidate IDs.
- Review UI now displays the summary and trigger text for workflow clusters.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `27 passed`
- Focused server suite → `136 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the summary/trigger/metadata slice.
- No blocker found.

**Remaining gaps**
- Metadata is still derived at read/snapshot time rather than persisted as a dedicated workflow-cluster record.
- Trigger descriptions are simple key/scope summaries; they do not yet include learned procedural trigger conditions from action/tool traces.

## Slice 72 — Repeated usage-only workflows appear in workflow cluster snapshots

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- Workflow cluster snapshots now surface repeated activation usage-event workflows even when no lessons exist yet.
- Usage-only clusters require repeated evidence: at least 2 usage events and enough helpful/success evidence to meet `min_successes`.
- Usage-only clusters get lifecycle `status="candidate"` so the repeated workflow is visible for review/debugging.
- Usage-only clusters keep `promotion_status="below_threshold"` until there are enough lesson sources, so the Review “Create proposals” action does not pretend it can generate a good skill from raw usage evidence alone.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_surfaces_repeated_usage_only_workflows -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `28 passed`
- Focused server suite → `137 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the usage-only workflow slice.
- Review highlighted the UX/status risk that usage-only clusters would look proposal-ready even though promotion still needs lesson-backed skill-body material.
- Fixed by keeping usage-only clusters visible but `promotion_status="below_threshold"`.
- Re-ran thermo review after the fix; no blocker remained.

**Remaining gaps**
- Usage-only workflows are visible but not yet promotable into skills without lesson/artifact material.
- Tool/action sequence mining is still shallow; this slice uses repeated activation task metadata, not full action traces.

## Slice 73 — Workflow miner recognizes repeated action/tool sequences

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`

**Behavior added / fixed**
- Workflow usage-event mining can now derive a cluster key from explicit repeated action/tool sequences when task/workflow title metadata is absent.
- Supported sequence fields: `workflow_steps`, `action_sequence`, `tool_sequence`, `tool_names`, `actions`, `tools`, and `tool_calls`.
- Sequence extraction accepts strings and dict-style entries with `name`, `tool_name`, `action`, or `type`.
- To avoid single-tool spam, sequence-derived workflow keys require at least two steps and cap at five steps.
- These clusters follow the Slice 72 behavior: visible as workflow candidates, but not skill-proposal-ready until enough lesson material exists.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_clusters_snapshot_mines_repeated_tool_sequences -q` → `1 passed`
- `pytest apps/server/tests/test_knowledge_write_gate.py -q` → `29 passed`
- Focused server suite → `138 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the action/tool sequence mining slice.
- No blocker found.

**Remaining gaps**
- Action/tool sequence clusters are still derived from telemetry details already present in usage events; they do not reconstruct traces from external logs.
- Skill promotion still needs lesson-backed procedure material before generating a proposal.

## Slice 74 — Workflow cluster cache invalidates after promotion mutations

**Date:** 2026-05-26

**Files changed**
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`

**Behavior added / fixed**
- Cached workflow-cluster snapshots are invalidated after `POST /knowledge/processors/skill-promotions` creates skill-promotion candidates.
- Cached workflow-cluster snapshots are invalidated after `POST /knowledge/skill-promotions/{object_id}/create` successfully creates a skill from a candidate.
- Invalidation is scoped to the current memory service instance, matching the workflow-cluster cache key shape.
- Failure paths do not invalidate; the snapshot only changes after successful mutation.

**Validation**
- `pytest apps/server/tests/test_knowledge_routes.py::test_propose_skill_promotions_invalidates_workflow_cluster_cache apps/server/tests/test_knowledge_routes.py::test_create_skill_from_promotion_invalidates_workflow_cluster_cache -q` → `2 passed`
- Focused server suite → `140 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the cache invalidation slice.
- No blocker found.

**Remaining gaps**
- Workflow cluster snapshots are still cache-backed derived views; this slice only prevents stale lifecycle/status after promotion mutations.

## Slice 75 — Durable workflow-cluster lifecycle review markers (2026-05-26)

**Files changed**
- `apps/server/ntrp/knowledge/metadata.py`
- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/ntrp/knowledge/workflow_lifecycle.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/server/tests/test_knowledge_routes.py`

**Behavior added / fixed**
- Added durable workflow-cluster review markers using `promotion_kind=workflow_cluster_review` on `action_candidate` objects.
- Added `KnowledgeSkillPromotionService.mark_workflow_cluster_review(cluster_id, status, reason)` for `reviewed` and `rejected` lifecycle decisions.
- Added `POST /knowledge/processors/workflow-clusters/{cluster_id}/review` and invalidated cached workflow-cluster snapshots after successful review mutation.
- Workflow-cluster snapshots now fold durable review markers into lifecycle status and expose marker IDs in metadata.
- Reviewed/rejected clusters are not proposal-ready, and active review markers block duplicate workflow skill proposal generation.
- Repeated review calls update the existing marker for the cluster instead of accumulating duplicate marker objects.
- Review markers become stale when the cluster has newer evidence (`last_seen_at` after `workflow_reviewed_at`), so fresh lessons/usage can reopen a cluster for review instead of suppressing it forever.
- Active review markers also block single-lesson skill proposals for the reviewed workflow’s source lessons, avoiding a bypass around cluster-level rejection.
- Extracted review timestamp/currentness helpers into `apps/server/ntrp/knowledge/workflow_lifecycle.py` and kept `skill_promotions.py` under 1k lines after thermo flagged file growth.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_review_marker_persists_rejection_and_blocks_promotion` → passed
- `pytest apps/server/tests/test_knowledge_routes.py::test_review_workflow_cluster_route_invalidates_cache` → passed
- `pytest apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_knowledge_routes.py -q` → `45 passed`
- Focused server suite → `142 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/ntrp/server/response_cache.py apps/server/ntrp/skills apps/server/ntrp/services/chat.py apps/server/ntrp/operator/runner.py apps/server/ntrp/server/runtime/core.py apps/server/ntrp/tools/background.py apps/server/ntrp/tools/research.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the lifecycle-marker slice.
- Real issues found and fixed:
  - Duplicate review calls would have accumulated marker objects; fixed by updating the latest existing marker for the cluster.
  - Rejected/reviewed clusters could have been suppressed forever even after fresh evidence; fixed by treating review markers as stale when cluster evidence is newer than the review timestamp.
  - Active cluster review could have been bypassed by single-lesson skill proposals; fixed by excluding source lessons from single-lesson promotion while the review marker is current.
  - `skill_promotions.py` crossed the 1k-line maintainability threshold; fixed by extracting lifecycle helpers and compacting excess whitespace.

**Remaining gaps**
- Backend lifecycle state exists, but the Review UI does not yet expose controls for marking workflow clusters reviewed/rejected.
- Review markers are action-candidate-backed lifecycle records; there is still no dedicated workflow-cluster persistence table.

## Slice 76 — Review UI workflow-cluster lifecycle controls (2026-05-26)

**Files changed**
- `apps/desktop/src/api.ts`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`

**Behavior added / fixed**
- Added `reviewKnowledgeWorkflowClusterApi(...)` for `POST /knowledge/processors/workflow-clusters/{cluster_id}/review`.
- Added typed API result shape for workflow-cluster review mutations.
- Review pane workflow-cluster cards now expose `Mark reviewed` and `Reject` controls.
- Reject prompts for an optional reason; both actions force a refreshed workflow snapshot after the backend marker is written.
- Controls are disabled while a review mutation is in flight, and already reviewed/rejected/promoted clusters avoid redundant same-state actions.

**Validation**
- `pytest apps/server/tests/test_knowledge_routes.py::test_review_workflow_cluster_route_invalidates_cache apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_review_marker_persists_rejection_and_blocks_promotion -q` → `2 passed`
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after the UI/API slice.
- No blocker found. The UI uses a deliberately small inline control instead of a broad modal rewrite; backend remains the source of lifecycle truth and cache invalidation.

**Remaining gaps**
- Workflow cluster lifecycle is now controllable from Review, but there is still no dedicated workflow-cluster persistence table; lifecycle state is stored as review-marker knowledge objects.
- A richer UI could display stale-review history/reasons, but the core reviewed/rejected control loop is wired.

## Slice 77 — Workflow review marker evidence in snapshots and Review UI (2026-05-26)

**Files changed**
- `apps/server/ntrp/knowledge/skill_promotions.py`
- `apps/server/tests/test_knowledge_write_gate.py`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`

**Behavior added / fixed**
- Workflow-cluster snapshot metadata now includes active review marker details:
  - `workflow_review_object_id`
  - `workflow_review_object_ids`
  - `workflow_review_status`
  - `workflow_review_reason`
  - `workflow_reviewed_at`
- Stale review markers remain excluded from these active-review metadata fields, matching Slice 75’s fresh-evidence reopening behavior.
- Review pane workflow-cluster cards now display the current review marker status, marker ID, review date, and rejection/review reason when present.

**Validation**
- `pytest apps/server/tests/test_knowledge_write_gate.py::test_workflow_cluster_review_marker_persists_rejection_and_blocks_promotion apps/server/tests/test_knowledge_routes.py::test_review_workflow_cluster_route_invalidates_cache -q` → `2 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Ran strict thermo review after exposing marker details.
- No blocker found. The details are derived from the same active marker set used for lifecycle decisions, so stale reviews are not shown as current state.

**Remaining gaps**
- Dedicated workflow-cluster persistence is still not introduced; the spec allows cached processor output, and lifecycle is persisted as marker knowledge objects.

## Slice 78 — Restore Memory overview/library read routes (2026-05-26)

**Files changed**
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/ntrp/knowledge/store.py`
- `apps/server/tests/test_knowledge_routes.py`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`

**Behavior added / fixed**
- Restored `GET /knowledge/summary`, which the Memory Overview tab calls.
- Restored `GET /knowledge/objects`, which the Memory Library tab calls.
- `GET /knowledge/objects` supports the UI filters: `object_type`, `status`, `query`, `limit`, and `offset`.
- Knowledge store list queries now support title/text search instead of forcing the UI into a 404 path.
- Added aggregate count support for summary surfaces without materializing every object in the route.

**Validation**
- `pytest apps/server/tests/test_knowledge_routes.py::test_list_knowledge_objects_route_serves_memory_library apps/server/tests/test_knowledge_routes.py::test_knowledge_summary_route_serves_memory_overview -q` → `2 passed`
- `pytest apps/server/tests/test_knowledge_routes.py apps/server/tests/test_knowledge_write_gate.py apps/server/tests/test_memory_access_service.py apps/server/tests/test_knowledge_activation.py -q` → `119 passed`
- Focused closed-loop suite: `144 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/server/routers/knowledge.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Real issue found from manual UI report: Memory UI read endpoints were missing despite the closed-loop backend processors existing.
- Fixed by restoring the read API surface instead of papering over the frontend error.
- No blocker after validation.

**Remaining gaps**
- None for the reported `Not Found` Memory tab failure. The app/server process still needs a reload/restart by the user to pick up the route changes.

## Slice 79 — Fix Memory read-route service-wrapper regressions (2026-05-26)

**Files changed**
- `apps/server/ntrp/memory/service.py`
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/ntrp/knowledge/store.py`
- `apps/server/tests/test_knowledge_routes.py`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`

**Behavior added / fixed**
- Fixed runtime `TypeError: KnowledgeObjectService.list() got an unexpected keyword argument 'query'` by adding `query` to the service wrapper and passing it through to the repository.
- Fixed the same wrapper-layer risk for `GET /knowledge/summary` by adding `KnowledgeObjectService.count_by_type_and_status()` passthrough to the repository.
- Replaced weak route fakes with tests that exercise the real `KnowledgeObjectService` wrapper, so route/service signature mismatches fail in tests.
- Re-checked frontend `/knowledge/...` API paths against backend router declarations. All Memory tab API paths have matching backend routes; dynamic template bases map to the expected parameterized routes.

**Validation**
- `pytest apps/server/tests/test_knowledge_routes.py::test_list_knowledge_objects_route_uses_real_service_wrapper_query_signature apps/server/tests/test_knowledge_routes.py::test_knowledge_summary_route_uses_real_service_wrapper_counts_signature -q` → `2 passed`
- Focused closed-loop/memory route suite: `148 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Real issue: the previous Slice 78 tests mocked `knowledge_objects.list` with `**kwargs`, so they could not catch service-wrapper signature drift. That was garbage coverage.
- Fixed by adding regression tests that call the route through a real `KnowledgeObjectService` object with a fake repository.

**Remaining gaps**
- None known for the reported Memory tab 404/TypeError path. The running server still needs user-side restart/reload to pick up these Python route/service changes.

## Slice 80 — Normalize Memory summary count shapes (2026-05-26)

**Files changed**
- `apps/server/ntrp/server/routers/knowledge.py`
- `apps/server/tests/test_knowledge_routes.py`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`

**Behavior added / fixed**
- Fixed `/knowledge/summary` crash when `count_by_type_and_status()` returns the live nested shape:
  - `{ "fact": { "active": 4156, "superseded": 84 }, ... }`
- The summary route now normalizes both supported shapes:
  - repository tuple-key shape: `{(KnowledgeObjectType.FACT, KnowledgeObjectStatus.ACTIVE): 3}`
  - live/service nested shape: `{ "fact": { "active": 3 } }`
- Added a regression test using the exact nested payload shape seen in the runtime traceback.

**Validation**
- `pytest apps/server/tests/test_knowledge_routes.py::test_knowledge_summary_route_accepts_nested_live_count_shape apps/server/tests/test_knowledge_routes.py::test_knowledge_summary_route_uses_real_service_wrapper_counts_signature -q` → `2 passed`
- Focused memory route/closed-loop subset: `126 passed`
- Full focused closed-loop suite: `149 passed`
- `python -m compileall apps/server/ntrp/knowledge apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py` → passed
- `cd apps/desktop && npm run typecheck` → passed
- `cd apps/desktop && bun test tests/knowledgeViews.test.ts` → `5 pass`, `21 expect() calls`
- `git diff --check` → passed

**Thermo review**
- Real issue: route code assumed a tuple-key internal shape while the live service returned nested counts. Tests did not include the live shape.
- Fixed by normalizing at the route boundary and adding a regression test with the exact runtime shape.

**Remaining gaps**
- None known for the reported Memory summary crash. Server/app still needs user-side reload/restart to pick up Python changes.
