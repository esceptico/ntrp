# Knowledge System Architecture

This document is the current ntrp knowledge-system contract: internal flow, UX shape, data flow, processor lifecycle, activation policy, and verification boundary.

## Abstract

ntrp should not treat memory as one growing store. It should treat all durable context as typed knowledge objects that move through processors and are later activated.

```text
Evidence -> Objects -> Processors -> Objects -> Activation -> Feedback
```

The goal is not "remember more". The goal is to make future behavior better while keeping provenance, scope, review, sinks, feedback, and deletion clear.

## Research Synthesis

The design is grounded in five memory families:

| Criterion | Useful prior art | ntrp decision |
| --- | --- | --- |
| Stateful continuity | Letta persists messages, tool calls, memory blocks, and out-of-context history; important core memories are injected into context. | Keep a compact activated bundle, but persist every source/evidence/episode/object outside the prompt. |
| Scope boundaries | ChatGPT project memory separates project-only and default memory, with user controls for saved memory and chat history. | Every object carries scope; activation must prefer workspace/project/session scope before global context. |
| Temporal truth | Zep/Graphiti uses temporal knowledge graphs for dynamic facts and historical relationships. | Facts and patterns need lifecycle fields: active, superseded, archived, stale, verified_at, valid_from/valid_to when available. |
| Reflection loop | Generative Agents use observation, reflection, planning, and dynamic retrieval. | Run completion captures episodes; processors reflect them into lessons/candidates; activation feeds planning. |
| Procedural learning | Memp distills trajectories into step instructions and higher-level scripts, then updates/corrects/deprecates them. | Procedures are learned as candidates first, promoted only by review or explicitly trusted automation scope. |

The product rule from the research is simple:

```text
automatic capture and learning
small review queue for consequential changes
provenance on demand
raw objects as API/debug surface, not daily UX
```

## Problems Solved

The previous memory system had a useful pipeline, but it was too memory-specific:

```text
chat/session -> outbox automation -> source/evidence/episode objects -> reflection -> lessons/procedures/actions/artifacts -> activation -> prompt injection
```

The knowledge system addresses these issues:

- Object model: source, evidence, episodes, lessons, procedures, actions, artifacts, receipts, and feedback are first-class typed objects.
- Maintenance: review, feedback, and retention are explicit processors instead of hidden cleanup.
- Ranking: activation owns scoring, budget allocation, prompt context, and explanations.
- Bloating: source/evidence objects stay compact pointers; derived objects keep source IDs.
- Proactiveness: memory emits reviewable action candidates; execution remains policy-gated.
- Behavior changes: procedure candidates become active procedures only after approval.

## Target Model

```text
Source
  -> EvidenceRef
  -> Episode
  -> Fact / Pattern / Lesson
  -> ProcedureCandidate / ActionCandidate / Artifact
  -> ActivationBundle
  -> OutcomeFeedback
```

Object types:

- `Source`: chat, file, tool run, Obsidian note, Slack thread, browser page, calendar event, automation run.
- `EvidenceRef`: exact pointer into a source.
- `Episode`: compact task/run record: goal, context, actions, outputs, result, feedback.
- `Fact`: atomic evidence-backed claim.
- `Pattern`: consolidated understanding over facts or episodes.
- `Lesson`: reusable conclusion from one or more episodes.
- `Procedure`: approved behavior/workflow guidance.
- `ProcedureCandidate`: proposed behavior change awaiting review.
- `Artifact`: human-facing output such as note, brief, report, task list.
- `ActionCandidate`: proposed proactive action such as reminder, note, task, verification, automation.
- `SinkReceipt`: proof that an artifact/action was written or published.
- `OutcomeFeedback`: signal about whether activated context/action helped.

## Memory Classes

The object model is typed by use, not by storage table.

| Class | Role | Examples | Activation rule |
| --- | --- | --- | --- |
| Source of truth | Immutable or externally verifiable input | chat, tool run, file, Obsidian note, Slack thread | never injected directly unless requested |
| Evidence | Pointer into source of truth | message range, file line, tool output span | used to justify derived objects |
| Episodic | What happened in a task/run | goal, actions, result, feedback | useful for reflection and rare recall |
| Semantic | What is true | facts, entities, patterns | injected when relevant and scoped |
| Procedural | How to behave | procedures, workflows, skills | injected only when approved/active |
| Proactive | What might need action | reminders, stale checks, note drafts | shown as suggestions/review unless trusted |
| Artifact | Human-facing reusable output | notes, briefs, reports, task lists | published through sink adapters with receipts |
| Feedback | Whether memory helped | used, ignored, corrected, helpful, harmful | updates ranking and retention |

## Internal Flow

```text
1. Capture
   session/tool/source events become EvidenceRefs and Episodes

2. Extract
   evidence becomes Facts, entities, timestamps, lightweight metadata, or source-backed knowledge objects

3. Reflect
   episodes/facts/artifacts/procedures produce Lessons or candidates

4. Consolidate
   facts and lessons become Patterns when support is strong enough

5. Propose / Publish
   repeated signals create ProcedureCandidates or ActionCandidates
   approved artifacts write to configured sink folders and create SinkReceipts

6. Activate
   request-specific bundle is selected for prompt, UI, task, note, or reminder

7. Feedback
   used/ignored/corrected/helpful/harmful signals update future activation and object score
```

Continual-learning loop:

```text
Episode
  -> Reflection
  -> Lesson / ProcedureCandidate / ActionCandidate
  -> Review or trusted automation policy
  -> Procedure / Scheduled Action / Artifact
  -> Activation
  -> OutcomeFeedback
  -> Ranking + Retention + Deprecation
```

Important rule:

```text
Evidence is source of truth.
Memory is for future behavior.
Artifacts are for human reuse and external sink publication.
Procedures require review before changing behavior.
```

## Ranking And Activation

Ranking should move out of "memory retrieval" and into a generic activation service.

```text
ActivationRequest
  -> CandidateGenerators
  -> ScopeFilters
  -> Reranker
  -> BudgetAllocator
  -> ActivationBundle
```

Signals:

- relevance: does it answer the current request?
- scope: global, workspace, project, session, source, person, task.
- temporal validity: current, stale, superseded, expired.
- importance: stable preference, decision, failure, blocker, repeated pattern.
- evidence strength: direct source, multiple sources, derived only.
- outcome score: helped before, ignored before, corrected before.
- interruption cost: should this be injected, shown quietly, or proposed?

Current scoring:

- type weight: procedures and lessons rank above raw episodes.
- status weight: approved and active objects rank above draft objects.
- lexical match: query/title/text overlap raises local relevance.
- evidence strength: objects with source references receive support.
- outcome score: helpful/not-helpful feedback adjusts future ranking.
- lifecycle filter: rejected, archived, and superseded objects are excluded from activation.
- temporal scope: valid/current objects outrank stale or expired objects.
- diversity: final bundle avoids same-source or same-type near duplicates without collapsing useful fact/pattern/lesson role diversity.
- interruption cost: proactive items are held for review unless policy allows inline suggestion or execution.

Keep ranking boring:

```text
candidate generation = broad recall
reranking = precision
budget allocation = final context shape
feedback = future activation scoring
```

Do not solve ranking by adding more constants to one retrieval path. Different object types need different ranking rules.

## Proactiveness

Memory should not own proactive behavior. Memory should emit signals. The agent decides whether to act, and policy decides whether action needs approval.

```text
MemorySignal -> AgentEvaluation -> ActionCandidate -> Review -> Execution -> SinkReceipt
```

Proactiveness levels:

- `L0`: silent retrieval only.
- `L1`: inline suggestion in chat.
- `L2`: review queue item.
- `L3`: reminder or scheduled follow-up.
- `L4`: draft external action, such as Obsidian note or Slack/email draft.
- `L5`: auto-execute only for explicitly approved automation scopes.

Good proactive signals:

- "This chat contains a durable project decision."
- "This repeated failure should become a procedure candidate."
- "This fact is stale and needs verification."
- "This looks like a note/artifact candidate."
- "This open loop should become a reminder or task."
- "This project context should be promoted to project notebook."

Bad proactive shape:

- memory directly sends messages
- memory silently edits procedures
- memory injects large context because it is vaguely related
- memory creates notes/files without a sink receipt and review policy

## Automation Ownership

Background work belongs to automations or explicitly spawned background agents, not to Memory UI buttons.

Built-in processors:

- `knowledge_reflection`: `knowledge_event` plus count/idle and sweep triggers; converts new episodes into semantic/procedural/proactive candidates.
- `knowledge_retention`: daily/idle trigger; archives stale generated objects and records why.
- `knowledge_health`: daily read-only audit; reports counts, missing provenance, stale objects, and activation drift.

Custom automation/subagent shape:

- A custom automation may run an agent prompt over scoped knowledge when the task needs judgment.
- A background/research subagent may produce an artifact or action candidate, but the sink write still requires the artifact path and receipt policy.
- `knowledge_event` is the data-change trigger for memory itself. It fires from `knowledge_objects` lifecycle changes and is filtered by action, object type, status, and scope.
- Time, event, idle, and count triggers still cover retention, health, sweeps, and user-created recurring checks.

## UX Shape

The UI should expose the pipeline without making users manage the database.

Primary user surfaces:

- **Overview**: review only exceptions: procedure candidates, action candidates, and artifact drafts.
- **Search**: ask what would be recalled and why.
- **Provenance**: source trace on demand for any surfaced item.

Internal/API surfaces:

- **Sent**: what was actually injected.
- **Evidence**: source-backed facts and episodes.
- **Patterns**: derived context with provenance.
- **Lessons**: reusable conclusions from prior episodes.
- **Artifacts / Receipts / Audit**: sink outputs and lifecycle history.

These internal surfaces must not become a manual database UI. Automations and processors own extraction, reflection, consolidation, retention, and health checks. The user reviews only items that can change behavior or produce external artifacts.

Default view should be action-oriented:

```text
Memory
  Overview | Search

Today
  2 suggested notes
  1 stale project fact
  1 procedure candidate
  3 memories injected in last chats
```

## Draft UI

```text
+--------------------------------------------------------------+
| Memory                                                       |
+--------------------------------------------------------------+
| Overview | Search                                             |
+--------------------------------------------------------------+
| Query: "dex automation alerts"                              |
|                                                              |
| Activation Preview                                           |
|  [Pattern] Alerting work prefers structured DB metadata       |
|    why: relevance + project scope + repeated evidence         |
|    sources: 7 facts, 2 episodes                              |
|                                                              |
|  [Lesson] Broken links should be treated as UX defects        |
|    why: prior correction + high outcome score                 |
|    sources: 1 episode                                        |
|                                                              |
|  [Action] Verify stale Trigger.dev URL behavior               |
|    level: L2 review queue                                    |
+--------------------------------------------------------------+
```

Overview review item:

```text
Procedure Candidate
  Situation: user asks to inspect prod run
  Proposed behavior: check real run/DB before static reasoning
  Evidence: 4 successful corrections, 1 user complaint
  Scope: dex project only
  Risk: medium
  Actions: approve | edit | reject | archive | sources
```

Artifact review item:

```text
Action Candidate
  Type: Obsidian note draft
  Trigger: long conceptual memory discussion
  Proposed artifact: "ntrp memory architecture"
  Evidence: current chat + existing concept doc
  Level: L4 draft external action
  Actions: preview | edit | publish | dismiss | sources
```

## Data Flow

Write path:

```text
session/tool/source event
  -> Source + EvidenceRef
  -> Episode
  -> object extraction
  -> entity/time/scope metadata
  -> indexed objects
  -> audit event
```

Learning path:

```text
Episode + OutcomeFeedback
  -> reflection processor
  -> Lesson
  -> ProcedureCandidate or ActionCandidate
  -> review
  -> approved Procedure / scheduled Action / Artifact
```

Activation path:

```text
agent request
  -> ActivationRequest(scope, task, query, budget, policy)
  -> candidates from facts/patterns/lessons/procedures/episodes/actions
  -> filters for scope/time/trust
  -> rerank
  -> budget allocation
  -> prompt context + UI explanation
  -> access event
```

Artifact path:

```text
selected objects
  -> render processor
  -> Artifact
  -> review policy
  -> publish processor
  -> file-backed sink adapter
  -> SinkReceipt
```

Sink path:

```text
Artifact
  -> publish(sink, sink_ref)
  -> ~/.ntrp/knowledge-sinks/<sink>/<sink_ref-or-artifact-title>.md
  -> SinkReceipt(path, bytes, source artifact)
```

Retention path:

```text
KnowledgePruneRequest(older_than_days, limit, apply)
  -> candidate selection
  -> archive stale generated objects when apply=true
  -> KnowledgePruneResult
```

## Implemented Contract

Backend:

- `knowledge_objects` is the canonical object table.
- Legacy `facts` and `observations` are migrated into `knowledge_objects` as `fact` and `pattern` objects by schema v20.
- `/knowledge/activation/inspect` returns `ActivationBundle` and prompt-ready context.
- `/knowledge/summary` returns surfaces and review prompts.
- `/knowledge/objects` lists and creates typed objects.
- `/knowledge/objects/{id}` edits lifecycle/content/score/metadata.
- `/knowledge/objects/{id}/sources` returns provenance.
- `/knowledge/processors/reflect` creates lessons, procedure candidates, and action candidates from episodes.
- `/knowledge/processors/prune` applies retention policy.
- `/knowledge/processors/health` reports counts, review queue size, missing provenance, and stale objects.
- `/knowledge/artifacts/render` creates artifacts from selected objects.
- `/knowledge/artifacts/publish` writes an artifact through the sink adapter and records a receipt.
- `/knowledge/feedback` records outcome feedback and adjusts target score.
- `knowledge_event` automation triggers fire from knowledge object create/update and can be filtered by object type, status, action, and scope.

Runtime:

- Chat and operator prompts use `ActivationBundle.prompt_context`.
- Activation reads persisted knowledge objects only.
- Completed runs capture `Source`, `EvidenceRef`, and `Episode`.
- Approved procedure candidates produce active procedures.
- Rejected, archived, and superseded objects are not activated.
- Expired, invalidated, or not-yet-valid objects are not activated.
- Activation applies a small diversity pass so one source does not flood the prompt with duplicate fact/pattern copies.
- Procedure ranking uses feedback counters from successful and failed prior uses.

Desktop:

- Memory has Overview, Library, Review, and Activation.
- Overview shows object counts, next actions, and recent knowledge.
- Library browses typed knowledge objects: episodes, facts, patterns, lessons, procedures, actions, artifacts, and activation feedback.
- Review contains only draft procedure/action/artifact decisions.
- Activation previews activated knowledge and reasons.
- Procedure/action candidates can be approved or dismissed.
- Artifact drafts can be published or dismissed.
- Source tracing is available on surfaced review objects.
- Reflection, retention, and health are automation-owned, not user buttons.
- The Automations panel exposes a System tab for power users to inspect, pause, and manually run built-in knowledge automations.

TUI:

- Memory has Overview, Library, Review, and Activation.
- It uses `/knowledge/*` routes only.
- It does not expose facts, observations, prune, audit, or sent logs as manual tabs.

Testing:

- Server full suite: `uv run pytest`.
- Server knowledge lint: `uv run ruff check ...`.
- Desktop typecheck: `bun run typecheck`.

## Replacement Boundary

The product-facing memory path is now the knowledge system.

- `remember()`, `recall()`, and `forget()` operate on `knowledge_objects`.
- Chat/operator prompt assembly uses `ActivationBundle.prompt_context`.
- Built-in background jobs run knowledge reflection, retention, and health handlers.
- Desktop and TUI Memory use `/knowledge/*` routes and typed overview/library/review/activation surfaces.
- The legacy `/facts`, `/observations`, `/memory/recall/*`, and `/memory/prune/*` router is no longer mounted.
- Legacy fact/observation tables may remain as migration/storage internals until the SQLite schema can be compacted, but they are not the runtime or UI contract.

## Sources

- Local concept: `docs/internal/knowledge-pipeline.md`
- Local memory guide: `docs/guides/memory.mdx`
- Local prior plan: `docs/internal/memory-plan.md`
- Generative Agents: memory stream, reflection, planning, dynamic retrieval. https://arxiv.org/abs/2304.03442
- Reflexion: verbal feedback/reflection as memory rather than weight updates. https://arxiv.org/abs/2303.11366
- Self-Refine: iterative feedback/refinement without training. https://arxiv.org/abs/2303.17651
- MemGPT / Letta: core memory, archival memory, recall/message history separation. https://arxiv.org/abs/2310.08560
- LangMem: semantic, episodic, procedural memory managers and prompt optimization. https://github.com/langchain-ai/langmem
- DSPy: metric-driven prompt/program optimization with bootstrapped demos and MIPRO. https://dspy.ai/
- Zep / Graphiti: temporal knowledge graph, episodes, entities, facts, invalidation. https://help.getzep.com/v2/concepts
- Zep facts: temporal `valid_at` / `invalid_at` fact history. https://help.getzep.com/facts
- Mem0: scoped search, filters, thresholds, reranking. https://docs.mem0.ai/core-concepts/memory-operations/search
- MemReranker: memory-specific reranking for temporal, causal, and coreference-heavy recall. https://arxiv.org/abs/2605.06132
- Voyager: lifelong skill library and automatic curriculum. https://arxiv.org/abs/2305.16291
- Memp: procedural memory build/retrieve/update/deprecate loop. https://arxiv.org/abs/2508.06433
