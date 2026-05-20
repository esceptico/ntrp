# Memory Architecture Scratchpad

Date: 2026-05-20

## TL;DR

Separate the system into five layers:

```txt
Session/thread  = whole conversation or source container
Turn            = one user input and resulting assistant response cycle
Run             = one assistant execution attempt
Trace/log       = model calls, tool calls, errors, usage, spans
Episode         = coherent task/event segment across one or more turns/runs
Durable memory  = extracted fact, preference, decision, lesson, procedure, artifact pointer
```

Do **not** treat every turn or run as an episode. A 300-turn chat should become a small number of meaningful episodes, e.g. “debug memory bug”, “design entity resolution”, “implement migration”, “resolve user correction”.

Raw evidence is stored liberally. Durable memories are extracted conservatively and always point back to episodes/raw evidence.

## Target architecture

```txt
sessions
  └── turns
       └── runs
            └── traces/spans/tool calls/model calls/errors

raw_events
  └── messages, tool outputs, external source records, file/doc/email/slack/calendar events

memory_episodes
  └── grouped coherent task/event segments with source refs

durable_memories
  ├── semantic: facts, preferences, entities, relationships, project state
  ├── episodic: summarized experiences/examples/outcomes
  ├── procedural: rules, workflows, lessons, skills/procedure candidates
  └── artifacts/actions: created docs/files/tasks and follow-ups
```

## Definitions

### Session

Human-visible container:

- chat thread
- Slack channel/DM container
- mailbox/thread context
- calendar series context
- document/file workspace context

A session/container is not itself a memory. It scopes and organizes source events.

### Turn

One conversational exchange:

```txt
user message -> assistant/tool work -> assistant response
```

Turns are transcript structure, useful for UI, replay, and source references. They are not episodes.

### Run

One execution attempt by the assistant/agent.

A run can complete, fail, cancel, retry, branch, call tools, spawn subagents, or emit background work. Runs are provenance/observability, not durable memory.

### Trace/log

OpenTelemetry-style execution detail:

- model call spans
- tool call spans
- retrieval spans
- memory write proposals
- errors
- latency
- tokens/usage

This belongs in trace/provenance storage, not in semantic memory.

### Episode

A coherent task/event segment across one or more turns/runs.

Examples:

```txt
Episode: debug activation scope bug
  turns: 12-29
  runs: run_a, run_b, run_c
  outcome: fixed and tested

Episode: define entity-resolution architecture
  turns: 30-71
  outcome: schema and tests implemented

Episode: user correction on episode semantics
  turns: 72-80
  outcome: model corrected; architecture refined
```

An episode is where durable extraction usually happens.

### Durable memory

A reusable extracted object:

- fact
- preference
- decision
- project state
- event
- lesson
- procedure candidate
- approved procedure
- artifact pointer
- action candidate

Every durable memory should include provenance:

```txt
source_episode_ids[]
source_turn_ids[]
source_run_ids[]
source_message_ids[]
source_external_refs[]
confidence
valid_from / valid_until
supersedes / superseded_by
created_by: user | assistant | background | migration
review_state
```

## Episode boundary policy

No fixed “every N turns” rule as source of truth. Constants can exist only as operational backpressure, not semantic boundaries.

Use an LLM episode-boundary classifier plus deterministic signals.

Inputs to boundary classifier:

- current open episode summary
- last few turns/events as context
- current user message
- run outcome
- tool/artifact outcomes
- idle gap metadata
- explicit user markers
- topic/entity/task shift signals

Classifier output:

```json
{
  "boundary": true,
  "boundary_type": "task_completed | topic_shift | decision_made | artifact_delivered | correction_resolved | failure_resolved | idle_gap | explicit_switch | source_closed",
  "close_current_episode": true,
  "open_new_episode": true,
  "episode_title": "...",
  "confidence": 0.0,
  "evidence": ["..."]
}
```

Good boundary signals:

- task completed
- user changes topic
- explicit “now do X” / “new topic”
- decision made
- artifact delivered
- PR merged / issue closed / thread resolved
- user says “that worked” or “that failed”
- error/failure loop resolved
- correction resolved
- long idle gap with topic discontinuity
- meeting ended
- email/slack thread becomes inactive/resolved
- doc revision published/meaningfully changed

Not sufficient alone:

- one user turn
- one assistant run
- one tool call
- arbitrary N-turn count
- arbitrary token threshold

## Durable extraction policy

### 1. Hot-path extraction

Only for explicit/directive memory:

```txt
remember X
forget X
always do X
never do X
my preference is X
actually/correction: X
this is wrong; use Y instead
```

Action:

- write/update/supersede immediately
- source-link exact turn/message
- mark as user-stated

### 2. Episode-close extraction

When an episode closes, run extraction over:

- episode source turns/events
- episode summary
- artifacts/tool results
- outcome/failure/success signal
- relevant prior memories for dedupe/supersession

Extract:

- decisions
- durable facts
- preferences
- project state
- artifacts produced
- lessons from success/failure
- procedure candidates
- unresolved tasks/action candidates

### 3. Background consolidation

Run async/scheduled consolidation over multiple episodes:

- repeated patterns
- stale or contradicted facts
- supersession chains
- stronger procedures
- cross-session lessons
- entity resolution / alias cleanup
- memory quality audits

Do not silently promote risky procedural changes. Use review gates for procedures and standing behavior changes.

## Source-specific episode mapping

| Source | Raw event | Episode | Boundary | Durable extraction |
|---|---|---|---|---|
| Chat | message, tool output, run result | coherent task/topic segment across turns/runs | task done, topic shift, decision, artifact, correction/failure resolved | user facts, preferences, decisions, lessons, project state, procedures |
| Slack thread | message/reply/edit/reaction/file | Slack thread | thread resolved/inactive, decision/action, reaction/checkmark, handoff | decision, commitment, blocker, team preference, action item |
| Slack unthreaded channel | message burst | bounded topic/time/participant burst | topic shift, idle gap, thread/doc/PR handoff | lower-confidence decisions/actions unless explicit |
| Slack DM | message burst | task/topic exchange | task done, idle gap, topic switch | preferences, commitments, private task state |
| Email | message/label/history event | email thread/conversation | final reply, resolution, stale thread, explicit follow-up | commitment, deadline, requirement, stakeholder preference |
| Calendar | event/update/RSVP/cancel | meeting occurrence | event ended/cancelled/rescheduled; notes delivered | meeting decisions, commitments, follow-ups, attendee context |
| Recurring calendar | occurrence/update | each occurrence; series is context | per occurrence end/cancel/skip | per-meeting facts; series-level pattern only after repetition |
| Documents/files | revision/change/comment | meaningful revision, section change, edit batch | published version, major edit, resolved comment, stable revision | requirements, definitions, procedures, project decisions |
| GitHub PR | commits/comments/reviews/status | PR/review cycle | merged/closed/approved/changes addressed | accepted code/design decision, bug lesson, team convention |

## Retrieval model

Retrieval should query multiple indexes and rerank:

```txt
semantic vector
+ BM25/FTS keyword
+ entity match
+ temporal match
+ graph/episode proximity
+ scope boost
+ salience/importance
+ recency when query asks for recent/current
+ source trust
- stale/superseded/conflicted penalties
```

Use episodes mostly as provenance/context. Inject durable memories by default; pull episode evidence when needed.

## Code naming and implementation status

Phase 1 implementation landed the non-destructive naming cleanup:

```txt
session_episodes             -> session_turns
KnowledgeObjectType.EPISODE  -> KnowledgeObjectType.MEMORY_EPISODE
per-run capture              -> KnowledgeObjectType.RUN_PROVENANCE
```

Phase 2 added conservative episode grouping:

```txt
RunCompleted -> RUN_PROVENANCE -> assimilate into open MEMORY_EPISODE
explicit switch -> close current episode + open new episode
completion/outcome marker -> append evidence + close current episode
no strong boundary -> keep appending to current open episode
```

The fallback classifier deliberately does not split on arbitrary turn/run counts; idle gaps alone are not semantic boundaries.

Phase 3 wires the Memory v1 hot path:

```txt
model-backed EpisodeBoundaryClassifier -> deterministic fallback on provider/error/weak signal
close_memory_episode(...) -> conservative episode-close extraction with source_episode_id/source_run_ids/source_turn_ids
explicit user commands -> immediate durable writes/archive/supersession
activation default -> durable memories first; episodes/run provenance only for source/evidence/context queries
```

Implemented explicit commands are intentionally conservative: `remember ...`, `always ...`, `never ...`, `forget ...`, `actually ...`, and `correction: ...`. They write/archive immediately with source refs when observed on the run assimilation path. Corrections create a new durable fact and mark matching older fact/lesson/pattern rows superseded.

Compatibility kept intentionally:

- existing `/session/episodes` and `list_session_episodes(...)` aliases still work, but return turn-shaped rows with `turn_id` plus legacy `episode_id` alias;
- legacy SQLite `session_episodes` rows migrate into `session_turns` at startup;
- `capture_episode_from_run(...)` remains as a deprecated wrapper over `capture_run_provenance(...)`.

Canonical target naming:

```txt
sessions
session_turns
agent_runs
run_traces / run_provenance
raw_events
memory_episodes
semantic_memories
procedural_memories
```

## Implementation plan

1. Keep current raw messages/runs/traces append-only.
2. Rename or conceptually deprecate `session_episodes` as turn slices.
3. Add true `memory_episodes` table/object:
   - title
   - summary
   - status: open/closed/abandoned/superseded
   - start/end turn IDs
   - run IDs
   - source raw refs
   - entities
   - outcome
   - boundary reason/confidence
   - extracted memory IDs
4. Add LLM boundary classifier after each turn/run and on external-source ingestion.
5. Maintain open episode per session/source container.
6. Close/open/merge/split episodes based on classifier output and user corrections.
7. Run durable extraction only:
   - explicit hot-path directive
   - episode close
   - background consolidation
8. Require provenance links for all durable memories.
9. Use supersession/validity windows, never blind overwrite.
10. Add eval harnesses for:
   - segmentation quality
   - extraction precision/recall
   - stale memory suppression
   - temporal update correctness
   - retrieval grounding
   - poisoning resistance

## Research sources

- Generative Agents: memory stream, recency/relevance/importance, reflection  
  https://arxiv.org/abs/2304.03442
- Reflexion: reflection after feedback/outcomes  
  https://arxiv.org/abs/2303.11366
- MemGPT / Letta: tiered/core/archival memory  
  https://arxiv.org/abs/2310.08560  
  https://docs.letta.com/guides/core-concepts/memory/context-hierarchy/
- LangGraph / LangMem: thread memory vs long-term semantic/episodic/procedural memory; hot-path/background writes  
  https://docs.langchain.com/oss/python/langgraph/memory  
  https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- Zep / Graphiti: raw episodes as provenance, temporal validity, graph memory  
  https://github.com/getzep/graphiti  
  https://arxiv.org/abs/2501.13956
- Mem0: extraction/update/search memory layer, graph/entity memory  
  https://github.com/mem0ai/mem0  
  https://arxiv.org/abs/2504.19413
- OpenAI Agents SDK sessions/tracing: session memory and trace spans  
  https://openai.github.io/openai-agents-python/sessions/  
  https://openai.github.io/openai-agents-python/tracing/
- AWS Bedrock AgentCore Memory: actor/session/event organization; episodic strategy detects completed episodes  
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html  
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html
- CoALA: working/episodic/semantic/procedural memory taxonomy  
  https://arxiv.org/abs/2309.02427
- EM-LLM: event segmentation with surprise and graph refinement  
  https://arxiv.org/abs/2407.09450
- LoCoMo / LongMemEval: long conversation memory evaluation  
  https://arxiv.org/abs/2402.17753  
  https://arxiv.org/abs/2410.10813
- Slack conversations.replies/history/permalinks  
  https://docs.slack.dev/reference/methods/conversations.replies/  
  https://docs.slack.dev/reference/methods/conversations.history/  
  https://docs.slack.dev/reference/methods/chat.getPermalink/
- Gmail threads/messages  
  https://developers.google.com/workspace/gmail/api/guides/threads  
  https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages
- Google Calendar events/recurring events  
  https://developers.google.com/workspace/calendar/api/v3/reference/events  
  https://developers.google.com/workspace/calendar/api/guides/recurringevents
- Google Drive changes/revisions/activity  
  https://developers.google.com/workspace/drive/api/guides/change-overview  
  https://developers.google.com/workspace/drive/api/guides/manage-revisions  
  https://developers.google.com/workspace/drive/activity/v2/reference/rest/v2/activity/query
