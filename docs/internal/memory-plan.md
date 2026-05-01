# Memory Improvement Plan

Date: 2026-05-01

This plan follows from the live DB review of `~/.ntrp/memory.db` and the current `ntrp/memory` implementation.

## Baseline

Current live shape:

```text
facts         4,334 total, 2,720 active, 1,614 archived, 82 unconsolidated
observations 6,379 total, 6,379 active, 0 archived
dreams          100 total
```

Important ratios:

```text
observations with access_count = 0: 5,203 / 6,379
zero-access observations with <=5 sources: 3,173
zero-access observations with <=3 sources: 1,289
observations over 1,000 chars: 389
observations over 3,000 chars: 59
max observation length: 21,718 chars
temporal_checkpoints: 10,199
```

The problem is not simply "bad retrieval". The data model lets the observation layer grow into a second free-text corpus, then recall treats that corpus as primary memory.

## Phase 0 Status

Implemented on 2026-05-01:

```text
backup: backups/memory-20260501-012739.db
GET  /memory/audit
POST /memory/prune/dry-run
GET  /memory/injection-policy/preview
GET  /memory/profile/policy/preview
GET  /memory/learning/events
GET  /memory/learning/candidates
```

The first implementation is read-only:

```text
no archive writes
no deletes
no schema changes
```

Current dry-run rule:

```text
active observation
AND access_count = 0
AND created_at older than 30 days
AND source_count <= 5
```

Live result from the first run:

```text
dry-run observation archive candidates: 1,046
```

The audit now also reports direct provenance health for generated memory:

```text
observations/dreams without source facts
source refs pointing at missing facts
source refs pointing at archived facts
duplicate source refs
```

The injection policy preview is also read-only. It scans recent memory access events and flags:

```text
empty recall queries
context bundles above the configured character budget
pattern-heavy bundles where derived observations dominate source facts
```

The profile policy preview is also read-only. It keeps profile as a projection over source facts and flags:

```text
pinned, important, or useful-and-repeatedly-used facts that are not profile kinds yet
profile facts that are too long for always-on memory
profile facts with low confidence
```

Continuous learning now has append-only storage primitives:

```text
learning_events      direct evidence signals such as corrections, tool results, task outcomes
learning_candidates  proposed policy/skill/prompt changes with status and rollback metadata
```

No candidate is auto-applied. The first contract is provenance and reviewability.

## Target Model

The memory system should have four clear layers:

```text
typed facts        source of truth
profile view       stable, small, always-on user memory
observations       derived patterns, aggressively prunable
prefetch context   per-turn query-specific context
```

Rules:

- Facts are the durable source of truth.
- Profile is a projection over facts, not a second place to manually edit truth.
- Observations are derived summaries/patterns. They can be deleted or regenerated.
- Prefetch is a delivery mechanism, not a storage layer.

## Provenance Invariant

All generated or consolidated memory must have direct provenance.

Direct provenance means:

```text
generated artifact -> source fact ids in the local memory DB
```

This applies to:

```text
observations / patterns
dreams / cross-domain insights
profile entries if profile is materialized
session digests if they are later added
```

Rules:

```text
1. Generated memory cannot be treated as source of truth.
2. Every generated artifact must point to the facts that support it.
3. Missing provenance is a defect, not a harmless nullable field.
4. Archived/superseded source facts must be visible in audit and UI.
5. UI detail panes must show supporting facts before allowing trust/edit decisions.
6. If the system cannot produce provenance, it should store a fact or skip the generated artifact.
```

The practical shape:

```text
facts are durable truth
generated artifacts are views over facts
provenance relations are mandatory edges between them
```

Do not use prompt text, hidden context, or vague "because the model said so" explanations as provenance. If an external source matters, first create/store a fact or artifact-backed fact, then point generated memory at that.

## Phase 0: Audit And Dry-Run Pruning

Before schema changes, add an audit path that prints what the system would keep/archive.

Suggested report:

```text
active facts by kind/source/access/age
active observations by access/source_count/age/length
zero-access observations older than N days
observations with <= N source facts
observations with source facts that are archived/deleted
observations/dreams with missing or empty provenance
top entities by fact refs and observation refs
retrieval sample for selected queries
```

Dry-run archive candidates:

```text
observation.access_count = 0
AND observation.created_at older than 30 days
AND evidence_count <= 5
AND pinned_at IS NULL
```

Expected result:

```text
active observations should drop from 6,379 toward hundreds/low-thousands
zero-access active observation ratio should drop below 30%
recall context should become shorter and less narrative-heavy
```

No delete first. Archive only.

## Phase 1: Fact Types

Status:

```text
schema/model fields added in migration v5
API returns the new fields on fact payloads
manual metadata update endpoint added
kind-review endpoint added for untyped active facts
automated classifier/backfill not changed yet
```

Add a small `kind` enum to facts. Do not make this an ontology project.

Initial kinds:

```text
identity             stable user identity/background
preference           stable preference or taste
relationship         people/org relationships
decision             chosen outcome, architectural choice, commitment
project              durable project/product/company context
event                dated event that may matter later
artifact             document, URL, file, repo, note, resource
procedure            reusable how-to or workflow
constraint           rule, legal/contractual/product constraint
temporary            short-lived state; must have expires_at
note                 fallback for explicit/manual memory
```

Add minimal metadata:

```text
facts.kind TEXT NOT NULL DEFAULT 'note'
facts.salience INTEGER NOT NULL DEFAULT 0      -- 0 normal, 1 useful, 2 important
facts.confidence REAL NOT NULL DEFAULT 1.0
facts.expires_at TIMESTAMP
facts.pinned_at TIMESTAMP
facts.superseded_by_fact_id INTEGER REFERENCES facts(id)
```

Why this shape:

- `kind` makes retrieval/pruning deterministic.
- `expires_at` lets temporary facts die without prompt magic.
- `pinned_at` protects explicit user-approved facts.
- `superseded_by_fact_id` handles corrections without deleting history.
- `salience` is simpler than inventing many priority tables.

Avoid:

- separate subclasses/tables per fact type
- deeply nested JSON payloads
- LLM-only "importance" with no auditable field

## Phase 2: Extraction Shape

Status:

```text
chat extraction prompt tightened to source-of-truth facts only
chat extraction now returns typed facts with kind/salience/confidence/entities
explicit remember tool can pass typed metadata into the same fact ingestion path
legacy note facts have a review-only typed metadata suggestion endpoint
consolidation prompt tightened to skip atomic facts and require direct provenance
temporal/dream prompts tightened around concrete support and concise generated memory
legacy fact auto-apply/backfill still pending
```

Chat extraction now uses one extraction result instead of `facts: list[str]` plus a separate entity pass:

```json
{
  "facts": [
    {
      "text": "User prefers raw SQL over ORMs",
      "kind": "preference",
      "salience": 1,
      "confidence": 1.0,
      "happened_at": null,
      "expires_at": null,
      "entities": ["User", "SQL", "ORMs"]
    }
  ]
}
```

For explicit `remember()`, allow kind override later, but default through the same classifier. One ingestion path.

Extraction policy:

- `identity`, `preference`, `relationship`, `decision`, `constraint` are usually long-lived.
- `project`, `event`, `artifact`, `procedure` are query-retrievable but not always profile-worthy.
- `temporary` must include `expires_at`; otherwise skip it.
- Tool logs, debugging chatter, and active tasks are not memory unless the user explicitly asks to remember them.

## Phase 3: Profile Memory

Status:

```text
read-only profile projection added over typed facts
GET /memory/profile returns profile-worthy facts
system prompt memory can format profile sections separately from legacy user facts
no materialized profile table yet
```

Profile should answer: "What should the assistant always know about the user?"

Do not create a separate editable profile table first. Start with a projection over typed facts:

```text
profile facts =
  active facts
  WHERE kind IN ('identity', 'preference', 'relationship', 'constraint')
  AND archived_at IS NULL
  AND superseded_by_fact_id IS NULL
  AND (expires_at IS NULL OR expires_at > now)
  ORDER BY pinned_at DESC, salience DESC, access_count DESC, created_at DESC
  LIMIT small budget
```

Then format into sections:

```text
Identity
Preferences
Relationships
Standing constraints
```

Only materialize a `profile_entries` cache if the projection becomes too slow or needs manual UI editing.

If materialized later:

```text
profile_entries
  key TEXT PRIMARY KEY
  fact_id INTEGER NOT NULL REFERENCES facts(id)
  section TEXT NOT NULL
  text TEXT NOT NULL
  updated_at TIMESTAMP NOT NULL
```

The source of truth remains the fact. The profile row is a cache/projection.

## Phase 4: Generated Memory Provenance

Status:

```text
observation_facts and dream_facts added in migration v6
legacy JSON source_fact_ids is still kept during transition
repositories write both JSON and relation-table provenance for existing valid facts
```

Real-data migration check on backup copy:

```text
schema_version: 6
observation_facts: 39,239 rows
dream_facts: 574 rows
skipped invalid legacy refs: 1 observation ref, 22 dream refs
```

Replace JSON source ids with real relations. Start with observations, then dreams.

```text
observation_facts
  observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE
  fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE
  role TEXT NOT NULL DEFAULT 'support'
  created_at TIMESTAMP NOT NULL
  PRIMARY KEY (observation_id, fact_id)
```

```text
dream_facts
  dream_id INTEGER NOT NULL REFERENCES dreams(id) ON DELETE CASCADE
  fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE
  role TEXT NOT NULL DEFAULT 'support'
  created_at TIMESTAMP NOT NULL
  PRIMARY KEY (dream_id, fact_id)
```

Keep JSON `source_fact_ids` temporarily during migration, then remove it after code paths move.

Observation fields to add:

```text
observations.kind TEXT NOT NULL DEFAULT 'pattern'   -- pattern, trajectory, summary
observations.confidence REAL NOT NULL DEFAULT 1.0
observations.pinned_at TIMESTAMP
```

Generated artifact creation should fail or skip if it has no source facts, except for manually entered explicit memories that are stored as facts directly.

Do not add many observation types. Observations are derived. If they become complicated, the underlying fact model is probably wrong.

## Phase 5: Observation Creation Policy

Status:

```text
migration v8 adds observations.created_by and observations.policy_version
new/updated consolidation patterns are stamped with memory.pattern.v2
temporal patterns are stamped with memory.temporal.v1
legacy patterns backfill as created_by=legacy, policy_version=legacy
per-fact consolidation now blocks only narrow low-value creates:
  - temporary facts
  - low-salience chat notes
updates still apply, and temporal multi-fact pattern creation is unchanged
skipped pattern creates are aggregated into one memory event per pass
```

Real-data migration check on a copy of `~/.ntrp/memory.db`:

```text
schema_version: 8
observations: 6,528
legacy/legacy observations: 6,528
```

Current consolidation is too eager. New policy:

```text
create observation only if:
  explicit pattern/trajectory
  OR >=3 supporting facts
  OR contradiction/transition requires synthesis
  OR fact.salience >= 2 and consolidation model says pattern is real
```

Never create observations for:

```text
single preference
single identity fact
single deadline
single artifact/resource
temporary state
debugging/session chatter
```

Those remain facts.

Observation text budget:

```text
soft max: 500 chars
hard max: 1,000 chars
```

If an observation wants to become a 5,000-char essay, the model is doing document generation, not memory consolidation.

## Phase 6: Retrieval

Status:

```text
direct fact recall no longer hides consolidated facts
archived, expired, and superseded facts are filtered from recall candidates
consolidated facts get a small ranking penalty instead of hard exclusion
```

Current recall searches observations first and filters consolidated facts out of direct fact recall. That makes consolidated facts too dependent on observation quality.

Change retrieval to:

```text
1. profile projection, always-on and tiny
2. query-specific facts, hybrid vector + FTS
3. query-specific observations, only if high confidence/support or directly relevant
4. source facts bundled only as evidence, capped
```

Important rule:

```text
consolidated_at means "processed", not "hide from recall"
```

Use ranking penalties, not hard exclusion:

```text
base_score
* kind_weight
* salience_weight
* freshness_or_happened_at_weight
* access_decay
* support_weight_for_observations
```

Kind weights should be boring config, not another LLM call.

## Phase 7: Dex-Style Prefetch

Dex's useful pattern:

```text
start early
run retrievers in parallel
race against a latency budget
dedupe surfaced items
inject compact hidden context
never block the user turn
```

For ntrp, start smaller than Dex:

### V0: Memory-only prefetch

Trigger:

```text
new user message
```

Retrievers in parallel:

```text
profile projection
fact recall for current user text
observation recall for current user text
```

Budget:

```text
target 250-500ms if embeddings are warm
hard timeout 1,000ms
on timeout: drop prefetch context and continue
```

Output shape:

```text
hidden context block before latest user message:

Memory that may be relevant:

Profile:
- ...

Facts:
- ...

Patterns:
- ...
```

Caps:

```text
profile:      <= 6 bullets
facts:        <= 5 facts
observations: <= 3 observations
total chars:  <= 2,000 initially
```

Dedup:

```text
per session/run:
  fact ids already surfaced
  observation ids already surfaced
  profile fact ids already surfaced
```

After compaction, dedup can reset. If a topic matters again, prefetch should re-surface it.

### V1: Query resolver

Add a small resolver for short follow-ups:

```text
"yes send it"
"what about him?"
"same thing for Dex"
```

Use previous visible user/assistant turns to build an effective query. Do not use hidden prefetch blocks as query context.

### V2: Selector, only if needed

Dex uses an LLM selector over retrieved candidates. For ntrp, do not start there unless raw retrieval creates too much noise.

Start with deterministic caps and scores. Add selector later only if metrics show:

```text
high candidate quality but bad final surfaced set
```

## Phase 8: UI And API

Expose memory quality instead of hiding it. The current TUI already has a usable data-browser shape:

```text
tabs: Facts / Observations / Dreams
list + detail pane
edit/delete for facts and observations
supporting facts for observations
source filter for facts
```

That is a decent base, but it is not enough for the new memory model. The UI needs to make memory legible and controllable, not just editable.

### UX Research Takeaways

These are UI trust patterns, not architecture guidance. Observed patterns from ChatGPT/OpenAI, Letta ADE, LangGraph/LangChain docs, Mem0, and AI UX writeups:

```text
1. Separate always-visible memory from searchable archive.
2. Let users inspect, edit, delete, and clear memory.
3. Show whether memory is enabled and whether the current chat uses it.
4. Show what is "top of mind" versus background/archive.
5. Keep core/profile memory under explicit character budgets.
6. Provide search/sort/filter for large memory stores.
7. Make memory updates visible enough to build trust, but not noisy.
8. Provide temporary/no-memory mode.
9. Preserve provenance and source links for correction.
10. Show relation/support context, but avoid graph theater.
```

The important product idea: memory is not just backend storage. It is a user-facing control surface for trust.

### Observation Research Update, 2026-05-01

Sweep notes checked:

```text
2026-04-11, 04-13, 04-15, 04-16, 04-17, 04-18, 04-19,
2026-04-20, 04-21, 04-22, 04-24, 04-28, 04-29, 04-30
```

The useful signal is not "use memory framework X". The useful signal is a set of data-structure rules that show up repeatedly across the papers and production writeups.

The target split:

```text
semantic facts    durable, typed, user-controllable truth
profile/core      tiny always-visible projection over facts
observations      derived episodic/reflection layer, renamed to Patterns in UI
skills/rules      higher-compression procedural memory, not truth
```

#### Paper-derived rules

| Signal | Memory rule for ntrp |
| --- | --- |
| Mem0 v2/v3 ADD-only extraction, OpenClaw Dreaming, MuninnDB Dream Engine | Capture is append-only. Consolidation is async, retryable, and reviewable. Do not block the chat turn on merge/update/delete policy. |
| MemReader-4B, DeltaMem, Response-Utility Selection | A memory write or injection needs a gate. The gate asks whether the item has information value, resolves ambiguity, or would change the response. Similarity alone is not enough. |
| FOCAL, StructMem, GAM, ADEMA | Segment by task/time/semantic shift before summarizing. A single global summarizer over the whole chat is the wrong abstraction; it erases task boundaries. |
| FSFM, Adaptive Memory Crystallization, IE-as-Cache, ZenBrain | Memory needs hot/warm/cold tiers and forgetting. Reinforcement by actual reuse is a pruning signal; safety-triggered forgetting is a separate hard rule. |
| Experience Compression Spectrum, ContextWeaver, PhysNote | Facts, patterns, skills, and notes are the same evidence at different compression levels. Promotion requires provenance, not vibes. |
| SkillLearnBench, AJ-Bench, VLAA-GUI, AgentSearchBench | Self-review drifts. Derived knowledge should be promoted or ranked using external signals: user approval, execution result, repeated retrieval/use, or deterministic checks. |
| SRA-Bench, Decoupled Memory Control, SAGER | Retrieval is not the real bottleneck. The harder problem is deciding when to inject memory and which layer to inject. |
| Memanto, WUPHF, Anthropic CMA memory | Typed schema plus audit/provenance can beat vector-heavy graph theater. BM25/entity/time filters are worth exhausting before adding more infrastructure. |
| Hierarchical Persona Induction, Bian Que | User/profile patterns must stay evidence-aligned. A correction should update both the derived memory and the procedural rule/skill that caused the mistake. |
| AEL "less is more" | Do not ship a maximal memory architecture first. Nail facts, provenance, simple retrieval, and simple reflection before adding planners, judges, or RL policy loops. |

#### Direct-source paper pass, 2026-05-01

The current implementation is deliberately limited to review/provenance UI. It does not depend on reproducing any paper algorithm yet.

The direct-source pass confirms the boring direction: fix the data shape first, make provenance mandatory, then add small background policies with dry-runs and metrics. Do not build a memory research framework inside the product.

Paper sources were checked from the April sweep notes first, then verified against primary sources where possible. The strongest signal is convergent: the system needs better data contracts and evaluation before it needs clever memory machinery.

| Source | Useful idea for ntrp | What not to copy |
| --- | --- | --- |
| Mem0 token-efficient memory algorithm, <https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm> | ADD-only extraction, async memory processing, multi-signal retrieval, and explicit token/latency measurement. Agent-generated facts are first-class, not ignored. | Do not hide policy inside a black-box memory service. Keep local facts auditable. |
| Mem0 state of AI agent memory, <https://mem0.ai/blog/state-of-ai-agent-memory-2026> | Memory quality needs accuracy, token cost, and latency metrics. Full-context memory is a benchmark ceiling, not a production design. | Do not optimize recall alone and pretend the system is good. |
| Experience Compression Spectrum, <https://arxiv.org/abs/2604.15877> | Facts, patterns, skills, and rules are different compression levels over experience. This supports one evidence model with multiple projections. | Do not force all layers into one table or one UI concept. The shared part is provenance and lifecycle, not identical storage. |
| FOCAL, <https://arxiv.org/abs/2604.19541> | Filter noisy streams before summarization, attribute events to tasks, and isolate task memory to avoid cross-task pollution. | Do not add a multi-agent logging stack before we have explicit task/session segments. |
| RUMS, <https://arxiv.org/abs/2604.14473> | Similarity is not enough. Inject memory only when it changes or sharpens the response. | Do not implement mutual-information machinery now. Start with retrieved/injected/used/corrected telemetry. |
| SRA-Bench, <https://arxiv.org/abs/2604.24594> | Retrieval and incorporation are separate problems. The system must decide whether a skill or memory should be loaded at all. | Do not enumerate every memory/skill in context because retrieval exists. |
| SkillLearnBench, <https://arxiv.org/abs/2604.20087> | Continual learning needs external feedback. Self-feedback alone can drift; reusable workflows learn better than open-ended vibes. | Do not auto-promote skills or rules from self-review. Require evidence. |
| TACO, <https://arxiv.org/abs/2604.19572> | Terminal agents benefit from learned compression rules over observations. Rules should preserve task-relevant output and drop low-value noise. | Do not let learned compression rules rewrite source facts. Compression is a view/policy layer. |
| AEL, <https://arxiv.org/abs/2604.21725> | Split fast runtime memory use from slow reflection. The useful result is "less is more": memory plus reflection helped, extra planner/tool/skill mechanisms degraded. | Do not add planners, judges, RL loops, or per-tool policy knobs until simple memory telemetry proves the need. |
| FSFM, <https://arxiv.org/abs/2604.20300> | Forgetting has distinct classes: passive decay, active deletion, safety-triggered forgetting, and adaptive reinforcement. | Do not collapse all cleanup into one "old/noisy" flag. |
| StructMem, <https://arxiv.org/abs/2604.21748> | Preserve temporal anchors and event relationships for multi-hop/temporal questions. | Do not summarize away time and source boundaries just to reduce rows. |
| Memanto, <https://arxiv.org/abs/2604.22085> | Typed semantic memory, temporal versioning, conflict resolution, and lower-complexity retrieval can beat graph-heavy designs. | Do not add graph theater before typed facts, time, and conflict state are boring. |
| ContextWeaver, <https://arxiv.org/abs/2604.23069> | Preserve dependency structure and execution feedback, not just summaries. This matters for multi-step tool work. | Do not turn this into a generic graph database. Store direct evidence and dependency ids. |
| AJ-Bench, <https://arxiv.org/abs/2604.18240> | Evaluation should acquire verifiable evidence from the environment, not just ask another model to judge. | Do not trust an LLM-only reviewer for promotion or cleanup. |
| ZenBrain, <https://arxiv.org/abs/2604.23878> | Multi-layer routing, hot-path salience, and sleep/idle consolidation are useful ideas. | Do not copy the 7-layer neuroscience stack. It is too much machinery for ntrp right now. |
| ADEMA, <https://arxiv.org/abs/2604.25849> | Segment-level condensation and checkpoint/resume matter more than global summaries for long-horizon work. | Do not make every memory task a multi-agent governance workflow. |
| Hierarchical Persona Induction, <https://arxiv.org/abs/2604.26120> | Profile/persona generation must be evidence-grounded and truthfulness-scored against behavior logs. | Do not let profile/core memory become a generated biography with no direct fact support. |
| Bian Que, <https://arxiv.org/abs/2604.26805> | Skills can declare their own retrieval requirements; one correction signal should update both derived memory and the procedural rule that caused the miss. | Do not centralize all retrieval policy in one omniscient router if skill-local requirements are clearer. |
| PageGuide, <https://arxiv.org/abs/2604.23772> | Memory UX should show evidence in place and support guided/manual modes. Users need to see why a memory was used. | Do not hide memory behavior behind chat transcripts or abstract scores. |

Still worth a later skim, but not blockers for the current slice:

```text
DeltaMem, Decoupled Memory Control, SAGER, WUPHF, Anthropic CMA memory.
```

Those can influence later policy, but they should not block the next implementation slice unless the slice touches their domain.

#### Consolidated paper read

The practical architecture is:

```text
raw events       append-only evidence, enough to reconstruct provenance
facts            typed source-of-truth rows over evidence
patterns         derived episodic/behavioral claims over facts/events
profile          tiny always-loaded projection over selected facts
skills/rules     procedural compression over repeated successful behavior
policies         versioned retrieval/injection/compression/prune rules
```

This is not six independent memory systems. It is one evidence/provenance spine with multiple compression levels. Coupling stays low if each layer points down to evidence ids and never silently rewrites the lower layer.

Adoption order:

```text
1. Finish facts/profile/pattern provenance and cleanup review.
2. Add retrieval/injection telemetry: retrieved, injected, omitted, used, corrected.
3. Add task/session segmentation for new observations before more summarization.
4. Add dry-run policy evaluation for prune, profile promotion, and injection.
5. Add idle consolidation only after the review and metric surfaces are boring.
6. Add skill-local retrieval requirements later, when skills are back in scope.
```

Implementation status:

```text
2026-05-01: memory_access_events records prompt/tool context access.
2026-05-01: Memory UI has a Used tab for recent injected bundles.
2026-05-01: read-only injection and profile policy previews are exposed in API/UI.
2026-05-01: learning_events and learning_candidates provide the continuous-learning audit spine.
2026-05-01: learning review scan proposes deduplicated memory-policy candidates from existing telemetry; it never auto-applies them.
2026-05-01: chat prompt assembly adds bounded current-message memory prefetch (`chat_prefetch`) with duplicate filtering against the always-visible session memory.
2026-05-01: Memory UI has a Learning tab for candidate review and approve/reject status changes.
```

Rejected for now:

```text
generic knowledge graph
large multi-agent memory manager
self-review-only continuous learning
LLM-written profile truth
hard deletes from automatic cleanup
one global summarizer over all observations
```

#### Implementation gates

No automatic archive/apply until:

```text
1. prune dry-run exists in UI
2. candidate reasons are explicit
3. affected item details show direct provenance
4. apply writes are archive/supersede-only, never hard-delete
5. apply endpoint has tests against real-ish memory data
6. memory event log records who/what/why/policy_version
```

No automatic pattern creation rewrite until:

```text
1. source_fact_ids are mandatory
2. task/session segment boundaries are explicit
3. pattern has created_by, policy_version, support_count, and confidence basis
4. pattern correction creates/supersedes facts or marks the pattern stale
5. no pattern can become profile truth without an explicit fact update
```

No retrieval/injection rewrite until:

```text
1. telemetry records retrieved, injected, omitted, used, corrected, and stale
2. baseline token/latency/answer-quality counters exist
3. profile, facts, patterns, and skills have separate budgets
4. the UI can inspect the final injected context bundle
```

No profile/persona promotion until:

```text
1. profile rows point to source facts
2. corrections supersede the source fact or exclude it from profile
3. contradictory facts are visible, not silently overwritten
4. user-facing delete/archive remains stronger than automation
```

#### Practical implications

```text
facts       source of truth, typed, editable, provenance-bearing
profile     tiny projection over high-salience identity/preference/constraint facts
patterns    derived claims over facts; useful for retrieval, not authoritative
skills      procedures with activation conditions; promoted only after validation
events      raw-ish append log for reconstruction, audit, and future consolidation
```

Do not make observations a second editable truth store. They are derived artifacts over fact provenance. If the user corrects a pattern, the correction should either create/update facts or mark the pattern as wrong/stale; it should not silently rewrite history.

### Continuous Learning

Continuous learning is allowed only as a small, auditable improvement loop. It is not "the agent edits itself". It is a background system that proposes versioned policy changes from evidence, validates them, and keeps rollback cheap.

The data model should be explicit:

```text
learning_event
  id
  created_at
  source_type            user_correction | tool_result | task_success | task_failure | repeated_retrieval | prune_review
  source_id              message id, run id, tool call id, memory event id, or review id
  scope                  memory_extraction | retrieval | injection | compression | profile | skill | prompt
  signal                 what happened, in plain text
  evidence_ids           direct source ids, never just a summary
  outcome                success | failure | corrected | ignored | unknown

learning_candidate
  id
  created_at
  status                 proposed | approved | applied | rejected | reverted
  change_type            retrieval_rule | injection_rule | compression_rule | prune_rule | skill_note | prompt_note
  target_key             stable id for the rule/skill/prompt section
  proposal               small text or structured patch
  rationale              why this should help
  evidence_event_ids
  expected_metric        fewer tokens, fewer stale injections, better task success, less user correction
  policy_version
  applied_at
  reverted_at
```

Rules:

```text
1. Learning candidates are append-only records.
2. Applying a candidate creates a new policy version.
3. Reverting switches the active policy version back; it does not delete history.
4. A candidate needs direct provenance, not a model-generated story about why it is good.
5. Self-feedback may propose, but user correction, tool results, replay, or review must validate.
```

Good automatic-improvement targets:

```text
retrieval ranking weights
memory injection budgets
compression rules for noisy tool output
prune/archive thresholds
prefetch templates for recurring workflows
skill activation hints
```

Bad automatic-improvement targets:

```text
profile truth
system prompt authority
tool permissions
hard deletion
unreviewed skill creation
unreviewed code changes
```

The continuous-learning UI should be boring:

```text
Learning tab:
  Proposed
  Applied
  Rejected
  Reverted

Candidate detail:
  proposed change
  evidence
  expected metric
  current metric if available
  approve / reject / revert
```

This gives us auto-improvement without hardcoding one magical "evolve memory" path. Policies can evolve, but every change has provenance, status, version, and rollback.

Live ntrp sample from `~/.ntrp/memory.db` after the first cleanup work:

```text
facts:                   4,340
observations:            6,379 active
zero-access observations: 5,198
empty-source observations:   2
```

This confirms the issue is not lack of storage. The derived layer is too large and mostly unproven by use.

Near-term implementation direction:

```text
1. Rename the UI concept to Patterns while keeping observation as the backend table name.
2. Make patterns filterable by active/archive/all, used/never-used, and support count.
3. Show full supporting fact metadata in pattern details.
4. Add dry-run prune and review before any archival writes.
5. Add pattern creation policy:
   - minimum direct supporting facts
   - no pattern without source fact IDs
   - no promotion from pattern to profile without explicit fact update
   - no consolidation write without provenance
6. Add injection policy metrics:
   - retrieved but not injected
   - injected and used by the model
   - injected and later corrected by the user
   - stale pattern suggested
```

The first code slices in this direction are intentionally boring:

```text
1. Make Patterns visible, filterable, and provenance-backed.
2. Make prune candidates visible as a dry-run review tab.
3. Add memory_events audit log for manual writes, remember(), consolidation, and decay archives.
4. Add prune apply writes only for still-valid dry-run candidates.
5. Defer broader automatic writes until the review surface is boring.
```

### Proposed Memory Viewer

Status:

```text
Profile tab added as a read-only projection over source facts
Pattern rows/details expose creator and policy metadata
top-level tabs are now Overview, Profile, Facts, Patterns, Cleanup, Log
Cleanup can archive the selected candidate or all currently matching candidates
Dreams are hidden from the main memory nav for now
Recall Inspector is still pending
```

Replace the current 3-tab shape with:

```text
Overview | Profile | Facts | Patterns | Cleanup | Log
```

Optional/secondary:

```text
Dreams
```

Dreams are interesting but should not occupy equal navigation weight with source-of-truth memory if the goal is robustness.

### Overview

Purpose:

```text
show memory health at a glance
```

Content:

```text
active facts
active observations
zero-access observation ratio
archived counts
unconsolidated backlog
missing embeddings / stale index warnings
last automation run status
memory enabled / prefetch enabled / profile enabled
```

Actions:

```text
run audit
run dry-run prune
open settings
open latest warnings
```

This should be the default memory screen. A list of facts is not the highest-level mental model anymore.

### Profile

Purpose:

```text
show always-visible memory, with tight budget and provenance
```

Layout:

```text
Identity
Preferences
Relationships
Standing constraints
```

Each row should show:

```text
text
source fact id
kind
salience
pinned/prioritized state
last changed
```

Actions:

```text
pin / unpin
archive source fact
edit source fact
open provenance
exclude from profile
```

Important: editing profile should edit/supersede the source fact, not create a second source of truth.

### Facts

Purpose:

```text
browse and fix durable source-of-truth memory
```

Filters:

```text
kind
source
status: active / archived / superseded / temporary / pinned
accessed: never / used
entity
date range
```

Columns/list metadata:

```text
kind
salience
source_type
access_count
created_at / happened_at
expires_at if temporary
profile marker
superseded marker
```

Actions:

```text
edit
pin
archive
supersede
change kind
change salience
open source/session
test recall for this fact
```

### Patterns

Purpose:

```text
inspect derived observations without mistaking them for truth
```

Rename UI label from `Observations` to `Patterns`. "Observation" is implementation language and sounds like raw truth. "Pattern" better communicates derived/inferred memory.

Each row should show:

```text
summary
support_count
confidence
access_count
updated_at
archival/prune candidate marker
```

Detail pane:

```text
summary
supporting facts
history
why it exists
last retrieved
```

Actions:

```text
archive
pin
edit summary
split later if needed
open support fact
mark noisy/wrong
```

### Cleanup

Purpose:

```text
make cleanup reviewable before writes
```

Content:

```text
dry-run candidates grouped by reason:
  zero-access low-support pattern
  too long
  mostly archived support
  duplicate
  expired temporary fact
  missing provenance
```

Actions:

```text
select all in group
preview affected counts
archive selected
ignore selected
open item details
```

This is where trust comes from. Auto-cleanup without a review screen will feel like data loss.

### Log

Purpose:

```text
timeline of memory changes and automation outcomes
```

Rows:

```text
remembered fact
updated fact
superseded fact
created pattern
archived pattern
profile refreshed
prefetch bundle used
prune dry-run generated
```

Use this for debugging "why did it remember that?" and "when did it change?".

### Recall Inspector

Add a small test panel, either under Overview or as a hidden command.

Input:

```text
query
```

Output:

```text
profile facts selected
fact results with score components
pattern results with support/confidence
prefetch bundle preview
final formatted context
```

This should answer:

```text
why would the agent see this memory?
why did this not appear?
```

Without this, memory tuning becomes vibes.

### Chat-Side UX

Memory should surface in chat only when useful:

```text
short "remembered" status after explicit remember
short "memory updated" status when background extraction saves high-salience memory
optional memory trace toggle to show prefetched facts/patterns
temporary/no-memory mode indicator
```

Do not show every background extraction. That becomes notification spam.

For hidden prefetch, add a debug-visible trace:

```text
Memory prefetched: 2 profile, 3 facts, 1 pattern
```

Only show expanded details when the user opens the trace or enables a debug setting.

### Keyboard Model

Keep the TUI predictable:

```text
1-6             switch tabs
/               search/filter
enter           open details
e               edit
p               pin/prioritize
a               archive
k               change kind
s               source/provenance
r               run audit / recall test depending tab
space           select prune candidate
?               tab-specific help
```

### API additions

API additions:

```text
GET /memory/audit
GET /memory/profile
GET /memory/facts/kind-review
POST /memory/facts/kind-review/suggestions
GET /facts?kind=&source_type=&status=&accessed=&entity=&limit=&offset=
GET /memory/observations?min_sources=&accessed=&archived=
GET /memory/events
POST /memory/recall/inspect
POST /memory/prune/dry-run
POST /memory/prune/apply
PATCH /facts/{id}/metadata
```

UI should show:

```text
fact kind
salience
source
supporting observation links
profile inclusion
archive/supersede state
```

Manual actions:

```text
pin fact
change kind
archive fact
supersede fact
remove observation
clear low-value observations by dry-run batch
```

### Non-Goals For UI

```text
no graph visualization in v1
no fancy memory map
no separate profile editor that bypasses facts
no auto-prune without dry-run review
no huge prompt/debug dumps by default
```

Graph UI is tempting, but currently the backend graph is just entity refs. A pretty graph over weak entities would be bogus shit. Fix data first.

## Phase 9: Built-In Memory Automations

The current built-ins are too coarse:

```text
Chat Extraction       extract durable facts from conversations
Memory Consolidation  consolidate, merge, archive
```

Keep those, but split memory maintenance into explicit jobs with narrow invariants. One omnibus "consolidation" job is hard to reason about and easy to make slow.

Status:

```text
2026-05-01: builtin jobs split into:
  - Memory Consolidation: pending fact -> supported pattern work
  - Memory Maintenance: merge/archive passes
  - Memory Health Audit: read-only health/provenance snapshot
```

### 1. Memory Health Audit

Purpose:

```text
detect memory drift before recall quality degrades
```

Trigger:

```text
daily, idle-only
manual run from UI/CLI
```

Checks:

```text
active facts / active observations
zero-access observation ratio
observation length distribution
source-count distribution
unconsolidated fact backlog
missing embeddings
orphan observation_facts links
orphan entities
temporal checkpoint growth
archived rows still present in vec tables
```

Output:

```text
health summary + warning thresholds
no writes
```

This should exist before any auto-pruning. Show numbers or stop pretending the cleanup is safe.

Status:

```text
/memory/audit now reports storage integrity:
  facts/observations missing or stale vec rows
  facts/observations missing or stale FTS rows
  orphan relation rows for entities, generated-memory provenance, and temporal checkpoints
POST /memory/repair/embeddings adds dry-run-first missing-embedding repair
```

### 2. Fact Type Backfill

Purpose:

```text
classify legacy facts into the new `kind` model
```

Trigger:

```text
idle batches, newest/high-access facts first
```

Rules:

```text
only touches kind='note' rows
small batches
stores classifier confidence
does not rewrite fact text
```

This job should be boring and resumable. If classification fails, keep `kind='note'`.

### 3. Profile Refresh

Purpose:

```text
rebuild the always-visible user profile projection
```

Trigger:

```text
after new profile-worthy fact
after fact kind/salience/pin change
daily fallback
```

Input facts:

```text
identity
preference
relationship
constraint
high-salience decision if it affects assistant behavior
```

Output:

```text
small profile sections under a strict char budget
```

Important: this is a projection/cache. Facts remain source of truth.

### 4. Temporary Fact Expirer

Purpose:

```text
remove short-lived state from active memory
```

Trigger:

```text
hourly or daily
```

Rule:

```text
archive facts where kind='temporary' AND expires_at <= now
remove archived rows from vector/search tables
```

This is the clean replacement for hoping prompts skip temporary state forever.

### 5. Observation Pruner

Purpose:

```text
keep the derived pattern layer small
```

Trigger:

```text
daily dry-run
auto-apply only after thresholds are trusted
```

Initial archive rule:

```text
access_count = 0
AND created_at older than 30 days
AND support_count <= 5
AND pinned_at IS NULL
```

Later archive rule:

```text
low confidence
OR source facts mostly archived/superseded
OR summary over hard length cap
OR duplicate/near-duplicate with stronger observation
```

No hard delete until archive behavior is boring.

### 6. Supersession Resolver

Status:

```text
read-only supersession candidate endpoint added
manual apply path exists via PATCH /facts/{id}/metadata superseded_by_fact_id
no automatic supersession yet
```

Purpose:

```text
handle corrections and changed preferences without keeping contradictory active facts
```

Trigger:

```text
after new identity/preference/constraint fact
daily fallback
```

Candidate examples:

```text
"User prefers X" vs "User now prefers Y"
"User works at A" vs "User joined B"
"User's primary email is A" vs "User's primary email is B"
```

Output:

```text
set old_fact.superseded_by_fact_id = new_fact.id
archive old temporary/event facts when safe
leave audit trail
```

Current rule: produce review candidates instead of writing. Automatic supersession needs an explicit slot/key or stronger typed extraction so unrelated preferences do not become fake contradictions.

### 7. Episodic Session Digest

Purpose:

```text
preserve useful "how this was solved" context without polluting semantic facts
```

Trigger:

```text
after session idle
after long-running automation completes
```

Output shape:

```text
session_id
title
summary
outcome
projects/entities
important tool calls
created_at
embedding
```

This is separate from facts. Do not turn every session digest into observations. Episodic memory is for searching past work patterns and decisions; semantic facts are for durable truth.

### 8. Search/Embedding Repair

Purpose:

```text
keep FTS/vector/search indexes consistent with archived and updated memory
```

Trigger:

```text
daily
after embedding model change
manual
```

Checks:

```text
facts with embedding but no vec row
observations with embedding but no vec row
archived facts/observations still in vec rows
FTS row count mismatches
search index stale memory source rows
```

This is infrastructure hygiene. It should never call an LLM.

### 9. Upcoming Context Prefetch

Purpose:

```text
prepare memory context for scheduled/proactive automations before they run
```

Trigger:

```text
before calendar monitor events
before built-in briefings/digests
before user-defined automations with known prompt
```

Examples:

```text
meeting with Kevin in 30 minutes -> prefetch facts/profile/project context for Kevin + related project
morning briefing -> prefetch current profile constraints + recent high-salience facts + calendar-linked people
review automation -> prefetch project facts and previous review outcomes
```

Output:

```text
small cached context bundle with source ids and expiry
```

Rules:

```text
cache expires quickly
run retrieval only, no writes
automation uses the bundle if still fresh
fallback to normal retrieval if cache missing
```

This is Dex-style prefetch applied to backend automations: do useful retrieval before the run's hot path, but never make correctness depend on the cache.

### 10. Memory Feedback Collector

Purpose:

```text
turn user corrections into measurable memory quality signals
```

Trigger:

```text
when user says memory is wrong/noisy/stale
when user edits/deletes/pins memory in UI
```

Writes:

```text
memory_feedback
  target_type: fact | observation | profile_entry
  target_id
  signal: wrong | stale | noisy | useful | pinned | deleted
  source_ref
  created_at
```

Use feedback to tune pruning and retrieval. Do not use it to silently delete source facts.

## Phase 10: System-Wide Memory Flow

Desired end-to-end flow:

```text
chat/session/run
  -> chat extraction creates typed facts
  -> profile refresh updates always-visible memory
  -> temporary expirer removes short-lived state
  -> consolidation creates only real supported observations
  -> observation pruner keeps derived layer small
  -> prefetch surfaces relevant context before hot path
  -> recall can still find facts directly
```

The important system rule:

```text
writes are background and auditable
reads are fast, capped, and non-blocking
derived memory is disposable
facts are source of truth
```

## Phase 11: Migration Order

Safe order:

1. Add audit report and dry-run pruning.
2. Add fact columns with defaults.
3. Backfill `kind='note'`, then classify recent/high-access facts first.
4. Add profile projection from typed facts.
5. Let direct fact retrieval include consolidated facts again.
6. Add `observation_facts` and backfill from `source_fact_ids`.
7. Move observation code to the join table.
8. Tighten observation creation policy.
9. Split memory built-ins into health audit, prune, profile refresh, expirer, and repair.
10. Add memory-only prefetch.
11. Add upcoming-context prefetch for scheduled automations.
12. Archive low-value observations using dry-run results.
13. Remove legacy `source_fact_ids` only after all reads/writes move.

Do not combine all of this into one migration. Each step must have a visible count before and after.

## Verification Metrics

Track these after every phase:

```text
active facts
active observations
zero-access observation ratio
average observation length
observation source-count distribution
profile context char count
prefetch hit count per turn
prefetch timeout/drop count
manual recall needed after prefetch
wrong/noisy memory reports from user
```

Success target:

```text
active observations: hundreds/low-thousands, not 6k+
zero-access observations: below 30% active
profile context: stable and below 1,000 chars
prefetch: no visible latency regression
recall: facts can be found even when no observation is good
```

## Non-Goals

- Do not create a separate table per fact kind.
- Do not make profile a second source of truth.
- Do not rely on more consolidation prompts to fix bad data shape.
- Do not inject huge memory essays into the prompt.
- Do not make prefetch required for correctness.
- Do not delete memory before archive/prune dry-run is visible.

## Open Questions

- Should explicit `remember()` default to `pinned_at`?
- Should user-approved corrections automatically supersede old facts?
- Should profile facts require manual approval, or can high-salience extracted facts enter automatically?
- Should temporary facts default to 7-day expiry when the extractor detects transient state?
- Should dreams survive this cleanup as-is, or become an optional separate feature with its own retention?

## References Checked

ntrp:

```text
ntrp/memory/facts.py
ntrp/memory/retrieval.py
ntrp/memory/consolidation.py
ntrp/memory/consolidation_runner.py
ntrp/memory/store/base.py
ntrp/memory/store/observations.py
ntrp/memory/chat_extraction.py
```

Dex prefetch:

```text
~/src/dex/docs/prd-224-proactive-prefetch.md
~/src/dex/docs/prd-224-hybrid-retrieval.md
~/src/dex/apps/dashboard/app/api/ai/_agents/orchestrator/context/proactive-attachments.ts
~/src/dex/apps/dashboard/app/api/ai/_libs/prefetch/retrieve.ts
~/src/dex/apps/dashboard/app/api/ai/_libs/prefetch/types.ts
~/src/dex/apps/dashboard/app/api/ai/_libs/prefetch/dedup.ts
```

External references:

```text
Letta memory overview and archival/core memory docs
LangGraph/LangChain memory docs
Mem0 graph memory docs
Generative Agents / MemGPT
```

- Letta: core memory blocks are always visible; archival memory is searchable and on-demand.
  - https://docs.letta.com/guides/agents/memory
  - https://docs.letta.com/guides/agents/archival-memory
  - https://docs.letta.com/guides/ade/core-memory/
- LangGraph/LangChain: split short-term vs long-term memory; long-term memory includes semantic, episodic, and procedural memory; writes can happen in the hot path or in background jobs.
  - https://docs.langchain.com/oss/javascript/concepts/memory
  - https://docs.langchain.com/oss/python/langchain/long-term-memory
- Mem0: vector search can be enriched with extracted entities/relations, but graph growth needs confidence thresholds and cleanup.
  - https://docs.mem0.ai/platform/features/graph-memory
  - https://docs.mem0.ai/core-concepts/memory-types
- Generative Agents / MemGPT: useful precedent for memory streams, reflection, recency/importance/relevance scoring, and memory hierarchy.
  - https://papers.cool/arxiv/2304.03442
  - https://huggingface.co/papers/2310.08560
