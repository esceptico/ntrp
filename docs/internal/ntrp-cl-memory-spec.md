# ntrp Continual-Learning Memory Spec

Date: 2026-05-25
Status: planning spec for implementation
Scope: ntrp personal assistant memory only, not Dex product memory.
Related: `docs/internal/ntrp-cl-memory-closed-loop-spec.md` expands the full usage/outcome/workflow/skill loop required to make this work as a real learning system.

## Summary

ntrp should implement a small, high-precision continual-learning (CL) loop on top of the current knowledge system:

```text
event / turn / run
→ provenance capture
→ episode synthesis
→ candidate extraction
→ write gate
→ consolidate / merge / conflict-check
→ bundled retrieval by task + scope
→ context assembly
→ memory usage/outcome logging
→ correction / delete / decay / skill promotion
```

This spec intentionally does **not** introduce a parallel generic memory model. It extends the existing ntrp model:

```text
retained durable: fact, lesson, artifact, memory_episode
review-only: action_candidate
provenance/evidence: run_provenance, outcome_feedback, sink_receipt, source/evidence refs
legacy/noisy: entity_profile, pattern, procedure, procedure_candidate, legacy episode
```

Design principle: **episodes are narrative source-of-truth; normal activation should mostly retrieve distilled facts, lessons, artifacts, and only pull episodes/provenance when evidence/history is useful.**

Compatibility principle: **do not preserve broken memory behavior for backward compatibility.** This is ntrp personal infrastructure; clean breaks are acceptable when they remove legacy/noisy types, prevent memory soup, or simplify the CL loop. Prefer explicit migrations and updated tests over compatibility shims.

## Research pass: existing implementation

### 1. Write/extraction pipeline and write gates

Current implementation:

- `KnowledgeObjectType` already contains the useful durable types plus legacy/provenance types in `apps/server/ntrp/knowledge/models.py:7`.
- The central write path is `KnowledgeObjectService.create()` in `apps/server/ntrp/memory/service.py:678`. It applies create policy, entity extraction, conflict annotation, embeddings, memory-episode retention, event logging, and commit.
- Current create-policy guardrails live in `_apply_create_policy()` in `apps/server/ntrp/memory/service.py:447`:
  - episode-close `procedure` / `procedure_candidate` outputs normalize to active `lesson`;
  - large active `pattern` rows are archived unless explicitly allowed;
  - active `entity_profile` rows must be source-backed.
- Run provenance is captured separately by `capture_run_provenance()` in `apps/server/ntrp/memory/service.py:744`.
- Narrative memory episodes are created by `create_memory_episode()` in `apps/server/ntrp/memory/service.py:781` and closed by `close_memory_episode()` in `apps/server/ntrp/memory/service.py:1188`.
- Episode-close extraction is handled by `_extract_memories_from_closed_episode()` in `apps/server/ntrp/memory/service.py:994`.
- Consolidation exists through `commit_fact_consolidation()` in `apps/server/ntrp/memory/service.py:331` and routes in `apps/server/ntrp/server/routers/knowledge.py:30` and `:45`.
- Processor health exposes duplicate/conflict/quality counters in `KnowledgeProcessorService.health()` in `apps/server/ntrp/knowledge/processors.py:191`.

Gaps:

- There is no single explicit CL write-gate object that returns `write | merge | ignore | expire | review` decisions.
- Duplicate/conflict handling is mostly post-write/review, not always pre-write.
- Source-backedness is enforced for some object types, but not uniformly for all durable extracted memories.
- `KnowledgeProcessorService.feedback()` can still create a draft `PROCEDURE_CANDIDATE` for negative procedure feedback in `apps/server/ntrp/knowledge/processors.py:166`; this conflicts with the current direction of keeping `procedure_candidate` legacy/noisy.
- Historical dangling `knowledge:*` refs are tolerated after API hardening, but not repaired.

### 2. Retrieval / activation / context assembly

Current implementation:

- Activation models are in `apps/server/ntrp/knowledge/models.py`:
  - `ActivationRequest` at `:84`
  - `ActivationCandidate` at `:100`
  - `ActivationBundle` at `:113`
- The orchestration service is `KnowledgeActivationService` in `apps/server/ntrp/knowledge/activation.py:150`.
- `inspect()` in `apps/server/ntrp/knowledge/activation.py:154` retrieves candidates, scores/sorts, fits a budget, formats prompt context, and optionally records access.
- `_format_prompt_context()` in `apps/server/ntrp/knowledge/activation.py:109` currently renders a flat prompt context from selected candidates.
- `_fit_budget()` in `apps/server/ntrp/knowledge/activation.py:34` is a flat budget fitter.
- Candidate scoring is centralized in `object_candidate()` in `apps/server/ntrp/knowledge/activation_scoring.py:315`.
- Source relationship trace is available through `source_trace()` in `apps/server/ntrp/memory/service.py:1545` and `/knowledge/objects/{id}/sources` in `apps/server/ntrp/server/routers/knowledge.py:98`.
- The Memory Library UI already exposes source relationships in `apps/desktop/src/components/memory/KnowledgeLibraryPane.tsx:496`.

Gaps:

- Activation returns a useful `ActivationBundle`, but it is still mostly a flat ranked list rather than task-aware bundles.
- Prompt context does not yet preserve enough structured fields for trust/freshness reasoning: source summary, scope, confidence/salience, updated/expiry, why retrieved, conflicts, or replacement links.
- Budgets are flat, not bundle-aware.
- Episodes/provenance can be retrieved, but the normal assembler does not clearly separate `user_preferences`, `project_memory`, `procedural_lessons`, `recent_episode_context`, `artifacts/resources`, `warnings/conflicts`, and `source/evidence`.

### 3. Usage/outcome telemetry and correction loop

Current implementation:

- `ActivationRequest.record_access` exists at `apps/server/ntrp/knowledge/models.py:91`.
- `KnowledgeActivationService.inspect()` can record access via `_record_access()` in `apps/server/ntrp/knowledge/activation.py:175`.
- There is a feedback route at `/knowledge/feedback` in `apps/server/ntrp/server/routers/knowledge.py:165`.
- `KnowledgeProcessorService.feedback()` creates `OUTCOME_FEEDBACK` objects and updates feedback metadata/counts on targets in `apps/server/ntrp/knowledge/processors.py:126`.
- Archive/restore/detail/source-trace flows already exist in the Memory Library and backend object routes.

Gaps:

- Current access logging does not appear to capture the full CL outcome envelope:
  - retrieved memory IDs,
  - injected memory IDs,
  - cited memory IDs,
  - ignored/omitted memory IDs,
  - user correction flag,
  - final outcome: `helped | irrelevant | harmful | unknown`.
- User corrections are not yet a first-class high-signal write path.
- Feedback exists but is not tightly connected to every assistant run/context injection.
- Negative procedure feedback can create legacy `procedure_candidate`; it should instead create an `action_candidate` or a `lesson` revision proposal.

### 4. Skill/playbook promotion

Current implementation:

- Global/builtin skill infrastructure already exists. `SkillService` lives in `apps/server/ntrp/skills/service.py:25`, and `SkillService.create()` is at `:73`.
- The chat tool plane exposes `create_skill` through the built-in `propose-skill` flow.
- Memory review already has `action_candidate` and duplicate merge affordances. The Review UI's duplicate merge action is in `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx:222`.
- Current durable procedure-like memories are intentionally represented as `lesson`, not as active `procedure` / `procedure_candidate` rows.

Gaps:

- There is no memory-to-skill promotion candidate detector.
- There is no review affordance that says “this lesson/procedure has repeated enough; propose a skill/playbook.”
- Skill promotion should remain user-approved; automatic skill writes would be too risky.

## Target architecture

### CL memory decision

Add an explicit write-gate decision type. This can live in `apps/server/ntrp/knowledge/models.py` or a new `apps/server/ntrp/knowledge/write_gate.py`.

```py
class MemoryWriteAction(StrEnum):
    WRITE = "write"
    MERGE = "merge"
    IGNORE = "ignore"
    EXPIRE = "expire"
    REVIEW = "review"

class MemoryWriteDecision(BaseModel):
    action: MemoryWriteAction
    object_type: KnowledgeObjectType | None = None
    target_id: int | None = None
    candidate: KnowledgeObjectCreate | None = None
    patch: dict[str, Any] | None = None
    reason: str
    confidence: float = Field(ge=0, le=1)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

The write gate should answer:

```text
Should this become durable memory?
Is it still useful in 6+ months?
Is it user/project/tool specific?
Is it source-backed?
Is it duplicate or near-duplicate?
Does it conflict with active memory?
Should it expire?
Should it become a review item instead of active memory?
Should it become a skill/playbook candidate?
```

### ntrp memory mapping

Do not add `semantic`, `episodic`, `procedural`, `preference`, `resource`, or `integration` as new persisted object types.

Map concepts to current types:

| CL concept | Persisted ntrp type |
|---|---|
| user preference | `fact` or `lesson` |
| stable project fact | `fact` |
| reusable procedure/playbook | `lesson`, later skill candidate |
| resource/config/link/artifact | `artifact` |
| event/task history | `memory_episode` |
| correction | high-salience `fact` or `lesson` |
| integration quirk | `lesson` or `artifact`, scoped by project/tool |
| follow-up/review need | `action_candidate` |

### Source and relationship model

Use plural sources and typed links. Do not collapse provenance to one `source` field.

Required for durable writes:

```text
source_ids: ["session:...", "turn:...", "run:...", "knowledge:..."]
metadata.source_episode_ids: [...]
metadata.write_gate: "knowledge.write_gate.v1"
metadata.write_gate_reason: "..."
metadata.conflict_ids: [...]
metadata.duplicate_candidate_ids: [...]
metadata.expires_at: optional
```

Existing source trace fields should remain:

```text
derived_objects
related_objects
superseded_versions
superseded_by_object
```

## Implementation plan

### Phase 1: Central write gate

Goal: make durable memory admission explicit and testable.

Tasks:

1. Add `MemoryWriteDecision` models.
2. Add `KnowledgeWriteGate` service.
3. Route all episode-close extracted durable candidates through it before `KnowledgeObjectService.create()`.
4. Gate all direct durable-memory creation paths where practical.
5. Normalize/replace legacy outputs:
   - `procedure` → `lesson` or archived legacy residue
   - `procedure_candidate` → `action_candidate` or `lesson` candidate
   - `pattern` → `lesson` unless explicitly archived historical residue
   - `entity_profile` → archive unless source-backed and explicitly allowed
6. Require source-backed durable extracted memories unless there is a manual/user-authored exception.
7. Pre-check near-duplicate and conflict candidates before writing.
8. Emit metadata on every decision.

Acceptance criteria:

- No episode-close path can create active/draft `procedure`, `procedure_candidate`, `pattern`, or `entity_profile`.
- Negative feedback no longer creates `PROCEDURE_CANDIDATE`; it creates `ACTION_CANDIDATE` or a reviewable lesson revision.
- Active durable extracted memories have source episode/provenance refs unless explicitly marked manual.
- Duplicate candidates prefer `merge`/`review`, not blind write.
- Conflicts become review candidates, not auto-merged active facts.

Suggested tests:

- Episode-close extraction with legacy model output normalizes to `lesson`.
- Feedback on legacy procedure does not create `procedure_candidate`.
- Unsourced extracted durable candidate is ignored/reviewed, not active.
- Duplicate candidate returns merge/review decision.
- Conflicting candidate returns review decision.
- Manual user `remember` path can still write when explicitly source/intent backed.

### Phase 2: Memory usage telemetry

Goal: make memory improvement measurable.

Add a run-level usage record, probably separate from durable `KnowledgeObject`s. If using `knowledge_objects`, keep it provenance/audit-only and excluded from normal activation.

Proposed record:

```py
class MemoryUsageEvent(BaseModel):
    run_id: str | None
    session_id: str | None
    turn_id: str | None
    query: str
    task: str | None
    retrieved_memory_ids: list[int]
    injected_memory_ids: list[int]
    cited_memory_ids: list[int]
    omitted_memory_ids: list[int]
    bundle_counts: dict[str, int]
    user_corrected_answer: bool = False
    outcome: Literal["helped", "irrelevant", "harmful", "unknown"] = "unknown"
    reason: str | None = None
    created_at: datetime
```

Tasks:

1. Extend activation inspection to return stable IDs for retrieved/selected/omitted memories.
2. Log selected/injected IDs whenever context is assembled for an actual assistant run.
3. Add an endpoint/service method to update outcome after user feedback/correction.
4. Connect `/knowledge/feedback` to usage events, not only individual target objects.
5. Exclude usage events from normal activation unless debugging/auditing.

Acceptance criteria:

- Each memory-injected run has a usage event.
- Feedback can mark a usage event as `helped`, `irrelevant`, or `harmful`.
- Health can report recent memory-helpfulness counts.
- No usage telemetry appears as normal remembered content.

Suggested tests:

- Activation with `record_access=True` creates/updates usage/access record with selected and omitted IDs.
- Feedback updates usage outcome.
- Harmful memory feedback decreases target score or marks review metadata.
- Usage event is excluded from normal prompt activation.

### Phase 3: Retrieval bundles and context assembler

Goal: replace flat memory soup with structured task-aware bundles.

Add bundle names:

```text
active_user_preferences
active_project_memory
procedural_lessons
recent_episode_context
task_relevant_facts
artifacts_resources
warnings_conflicts
source_evidence_context
```

Extend `ActivationBundle` with:

```py
bundles: dict[str, list[ActivationCandidate]]
why_retrieved: dict[str, list[str]]
source_summaries: dict[str, list[str]]
conflict_warnings: list[str]
```

Context rendering should include compact headers and provenance hints, not raw JSON spam.

Example prompt shape:

```text
<active_user_preferences>
- [fact:123 score=.91 source=episode:456] Keep replies concise and casual.

<procedural_lessons>
- [lesson:789 source=episode:456] For memory roadmap work, update implementation notes after each verified change.

<warnings_conflicts>
- Possible conflict: fact:111 vs fact:222 about preferred verbosity. Prefer newer source unless user clarifies.
```

Tasks:

1. Add bundle classifier for candidates.
2. Replace flat `_fit_budget()` with bundle-aware budget fitting.
3. Make budgets dynamic by task, not fixed global percentages.
4. Add source summary/freshness/conflict metadata to `ActivationCandidate` or a new wrapper.
5. Replace the flat activation response/context shape when needed; update in-repo callers/tests instead of preserving compatibility shims.

Acceptance criteria:

- Context is grouped by bundle.
- User preference and project/procedure memories are not drowned out by flat semantic matches.
- Conflict warnings are visible when relevant.
- Sources are compact and auditable.
- In-repo `/knowledge/activation/inspect` consumers are updated to the new bundle shape; no stale flat-context compatibility contract remains.

Suggested tests:

- Query about user preference prioritizes `active_user_preferences`.
- Project-scoped query prioritizes project memory and procedural lessons.
- Conflict metadata appears in `warnings_conflicts`.
- Budget fitter preserves at least one high-score item from required bundles when available.
- Prompt context remains under requested char budget.

### Phase 4: Correction memory loop

Goal: treat user corrections as high-value CL data.

Correction triggers include phrases/intents like:

```text
"no, not that"
"that's wrong"
"don't do that"
"remember this instead"
"you keep ..."
"from now on ..."
```

Tasks:

1. Add correction detector in the message/episode-close pipeline.
2. If correction targets a retrieved/injected memory, link it to that memory and usage event.
3. Route correction candidates through write gate.
4. Prefer `lesson` for behavioral corrections and `fact` for stable explicit preferences.
5. Mark corrected/harmful memories for review or score decay.
6. Add UI review affordance for correction-derived candidates.

Acceptance criteria:

- Explicit user corrections produce reviewable high-salience memory candidates.
- Corrections are source-backed to turn/session/episode and any target memory.
- Harmful/rejected memories are decayed, archived, or superseded after approval.
- Correction candidates do not auto-create broad generic memories.

Suggested tests:

- “No, I meant X” creates/link correction candidate.
- Correction tied to injected memory marks usage event `harmful` or `irrelevant`.
- Correction candidate routes to `lesson`/`fact`, not `procedure_candidate`.
- Vague one-off irritation is ignored or review-only, not active durable memory.

### Phase 5: Skill/playbook promotion

Goal: stable repeated procedures become skills/playbooks instead of bloating memory.

Detector candidates:

```text
- repeated lesson used successfully N times
- same procedure-like lesson appears across multiple episodes
- user asks “do this like last time” repeatedly
- feedback marks a workflow helpful multiple times
- lesson text has stepwise reusable procedure shape
```

Tasks:

1. Add a `skill_candidate` metadata/review path using `action_candidate`, not a new durable type.
2. Surface “Propose skill” in Review UI for eligible lessons/action candidates.
3. Generate a draft `SKILL.md` body from linked lessons/episodes/artifacts.
4. Use existing `create_skill` approval flow; never auto-write skills silently.
5. On approval, link skill metadata back to source lessons/episodes.
6. Optionally archive/supersede redundant procedural lessons after skill creation, preserving source links.

Acceptance criteria:

- ntrp proposes skill promotion only after repeated evidence.
- User reviews full skill before write.
- Created skill cites/source-links back to memory objects.
- Normal activation can retrieve “there is a skill for this” rather than stuffing the full playbook into context.

Suggested tests:

- Repeated successful lesson creates `action_candidate` with `promotion_kind=skill`.
- Review UI displays skill-promotion candidate.
- Approval calls existing skill creation path with source-backed body.
- Redundant lessons remain auditable after skill promotion.

### Phase 6: Quality/health counters

Goal: make regressions obvious.

Extend `/knowledge/processors/health` with counters such as:

```text
memory_usage_events_7d
memory_helped_7d
memory_irrelevant_7d
memory_harmful_7d
correction_candidates_pending
skill_candidates_pending
dangling_source_refs
unsourced_active_durable_objects
active_legacy_objects
```

Acceptance criteria:

- Existing counters remain: active legacy rows, tool-looking episodes, duplicate clusters, conflict clusters, extracted-without-source-episode.
- New counters are low-noise and actionable.
- Historical debt is clearly distinguished from new regressions.

## Migration strategy

Back compatibility is **not** a goal for this layer. Prefer a clean schema/API and update in-repo callers in the same change. Do not keep legacy memory behavior alive behind compatibility adapters.

1. Add write gate in observe/log mode only where useful for measurement; enforcement is allowed immediately for known-bad legacy/noisy paths.
2. Switch episode-close extraction to enforced gate.
3. Switch feedback/correction paths to enforced gate.
4. Add usage telemetry and context bundle fields using the clean target API, even if it breaks old internal callers.
5. Update UI and tests to read the new bundle/source/outcome fields.
6. Add explicit migrations/cleanup scripts for obsolete rows/fields when needed.
7. Only then consider cleanup/repair of historical dangling refs or unsourced extracted objects.

## Non-goals for now

- No token compression/TokMem/tokenizer adaptation/PEFT work.
- No Dex product memory implementation in this spec.
- No broad profile-generation revival.
- No new first-class `procedure`, `pattern`, or `procedure_candidate` durable memory rows.
- No silent automatic skill creation.

## Open decisions

1. Where should usage events live?
   - Option A: dedicated table, cleaner and excluded from activation by construction.
   - Option B: `knowledge_objects` with audit-only type, easier but risks activation leakage.
   - Recommendation: dedicated table if implementation cost is reasonable.
2. Should write gate run synchronously in the hot path or asynchronously during episode close?
   - Recommendation: synchronously for episode-close extracted candidates; direct user `remember` can be synchronous too because quality matters more than speed.
3. How aggressive should duplicate pre-merge be?
   - Recommendation: never auto-merge conflicts; auto-suggest merge for high-confidence duplicates, user approval for canonicalization.
4. How should historical debt be treated?
   - Recommendation: tolerate and count first; repair only after new write path is stable.

## First implementation slice

Build this first:

1. Add `KnowledgeWriteGate` and decision models.
2. Route episode-close extracted candidates through it.
3. Replace feedback-created `PROCEDURE_CANDIDATE` with `ACTION_CANDIDATE`/lesson-revision candidate.
4. Add regression tests for legacy type prevention and source-backed durable writes.
5. Add health counter for write-gate decisions and unsourced active durable objects.
6. Update implementation notes after verification.

This slice directly improves memory quality without needing UI redesign or token-space experiments.
