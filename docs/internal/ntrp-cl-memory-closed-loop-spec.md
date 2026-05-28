# ntrp Closed-Loop Memory System Spec

Date: 2026-05-25
Status: design/specification
Related docs:

- `docs/internal/ntrp-cl-memory-spec.md`
- `docs/internal/ntrp-cl-memory-implementation-notes.md`
- `docs/internal/knowledge-system-architecture.md`
- `docs/internal/memory.md`

## Goal

Make ntrp memory work as a closed feedback loop, not just a searchable knowledge table.

The target system should:

1. remember durable, source-backed knowledge;
2. retrieve the right knowledge for a task;
3. record which memories/skills were used;
4. observe whether they helped, hurt, or were corrected;
5. update/supersede stale knowledge;
6. detect repeated successful workflows;
7. propose skills/playbooks for user approval;
8. use approved skills in future matching tasks.

This is continual learning at the application/memory layer. It is not RL or model weight training.

## Current honest state

Current memory is mostly a structured knowledge store with review gates.

Existing durable/review objects:

```text
retained durable: fact, lesson, artifact, memory_episode
review-only: action_candidate
legacy/noisy: entity_profile, pattern, procedure, procedure_candidate, legacy episode
```

What exists now:

- `memory_episode` can represent narrative provenance for tasks/conversations.
- `fact`, `lesson`, and `artifact` represent durable memory.
- `action_candidate` is the review-only type for follow-ups, corrections, duplicates, and skill candidates.
- A central write gate blocks/normalizes noisy writes.
- Review UI can approve/reject some candidates and handle duplicate fact merges.
- Skill promotion scaffolding exists:
  - active/approved `lesson` rows can become draft `action_candidate` rows with `metadata.promotion_kind = "skill"`;
  - the draft contains `skill_name`, `skill_description`, and full `skill_body`;
  - approval calls `SkillService.create(...)` and links metadata back to the source memory.

Important caveat: the actual learning loop is underwired. In particular, skill promotion currently depends on metadata such as `success_count` or `feedback_counts.helpful`. If those counters are not reliably populated from real usage, nothing useful emerges.

## Target loop

```text
conversation / run / tool activity
        ↓
close episode
        ↓
extract candidates
        ↓
write gate
        ↓
durable memory: fact / lesson / artifact / memory_episode
        ↓
activation bundle for future task
        ↓
assistant uses memory and/or skill
        ↓
usage log records what was selected and used
        ↓
outcome feedback: helped / irrelevant / harmful / corrected / task success / task failure
        ↓
quality updates: counters, confidence, supersession, stale marking
        ↓
workflow mining over episodes + lessons + usage traces
        ↓
skill/playbook candidate in review
        ↓
user approves full draft
        ↓
approved skill is invoked on future matching tasks
```

If any of these links are missing, the system degenerates into searchable notes instead of learning.

## Core concepts

### Episode

A `memory_episode` is the narrative source-of-truth for what happened.

It should capture:

- user goal/request;
- relevant project/session context;
- important tool actions and artifacts;
- outcome or current status;
- corrections/preferences revealed by the user;
- links to raw provenance where available.

Normal activation should mostly retrieve distilled facts, lessons, artifacts, and skills. Episodes should be pulled when evidence/history is useful, not dumped into every prompt.

### Durable memory

Durable memory is the stable layer:

- `fact`: a source-backed truth.
- `lesson`: a reusable conclusion, preference, procedure, or behavioral rule.
- `artifact`: a reusable output/reference/doc/code asset.
- `memory_episode`: source narrative/provenance.

Procedure-like memory should be represented as `lesson` until it graduates into a skill.

### Review-only candidate

`action_candidate` is the only review-only bucket.

It can represent:

- possible follow-up;
- duplicate/conflict review;
- correction review;
- artifact publication review;
- skill/playbook promotion candidate.

Do not add another durable memory type for `skill_candidate`. Use `action_candidate` with metadata.

## Required system components

### 1. Intentional activation bundles

Activation must return a structured bundle, not a pile of semantically similar memories.

A good activation result should separate:

```text
facts_to_trust
lessons_to_follow
artifacts_to_reference
skills_to_consider
episodes_for_evidence
excluded_or_conflicting_memory
```

Each selected item should include:

- object id;
- score/rank;
- selection reason;
- scope/project/session match;
- whether it is required, advisory, or evidence-only.

Bad behavior:

```text
Here are 20 vaguely similar memories. Good luck.
```

Good behavior:

```text
This task matches a project constraint, a user preference, a prior lesson, and an approved skill.
```

### 2. Memory usage logging

Every activation that reaches the model/tool plane must be logged.

Required fields:

```text
usage_id
run_id
session_id
project_id/scope
memory_object_id
object_type
surface: prompt | context | tool | skill | review
rank
score
selection_reason
activation_bundle_id
used_by_model: unknown | yes | no
created_at
```

This is the most important missing signal. Without it, the system cannot know which memories are useful or harmful.

### 3. Outcome feedback

The system needs explicit and implicit outcome events.

Outcome event fields:

```text
outcome_id
usage_id nullable
memory_object_id nullable
run_id/session_id
outcome: helpful | irrelevant | harmful | corrected | task_success | task_failure | user_rejected | user_approved
source: user | review | tool | evaluator | system
confidence
quote/evidence nullable
created_at
```

Outcome sources:

- user says “yes”, “wrong”, “no actually”, “remember this”, “forget that”;
- user corrects assistant behavior;
- Review approve/reject/merge actions;
- task completion/failure;
- tool error or successful tool result;
- optional evaluator/judge, never trusted alone.

Memory metadata should eventually accumulate:

```json
{
  "used_count": 12,
  "helpful_count": 8,
  "irrelevant_count": 2,
  "harmful_count": 1,
  "correction_count": 1,
  "last_used_at": "...",
  "last_helpful_at": "...",
  "last_corrected_at": "..."
}
```

### 4. Correction engine

Corrections must update memory, not just add another contradictory note.

When the user says “no, actually X”:

1. identify related active memories;
2. detect likely contradiction/supersession;
3. create a corrected candidate with source refs to the correction episode;
4. mark old memory as superseded/stale after review or high-confidence explicit command;
5. link old and new objects.

Required relationships:

```text
corrects
supersedes
superseded_by
derived_from
conflicts_with
```

Bad behavior:

```text
old fact: user prefers A
new fact: user prefers not A
both remain active forever
```

Good behavior:

```text
old fact superseded by corrected fact, both source-linked and auditable
```

### 5. Candidate extraction from episodes

Extraction should operate from closed episodes, not random isolated chat snippets.

For each episode, extract:

- durable facts;
- reusable lessons/preferences/procedures;
- reusable artifacts;
- corrections;
- follow-up candidates;
- possible repeated workflow signals.

Each extracted object must include source refs back to the episode and/or raw provenance.

### 6. Workflow mining

The system needs a repeated-workflow miner. This is the missing bridge between memory and useful skills.

Inputs:

- `memory_episode` objects;
- active/approved `lesson` objects;
- artifact usage;
- memory usage logs;
- outcome feedback;
- tool/action traces;
- existing skills and their invocation history.

Detect repeated patterns by:

- similar trigger/request;
- same project/domain/scope;
- repeated sequence of tools/files/apps;
- same user constraints/preferences;
- successful or approved outcomes;
- repeated manual instructions by user;
- repeated assistant behavior that later gets approved.

Output candidates:

- update an existing `lesson`;
- create a new `lesson`;
- create `action_candidate` with `promotion_kind = "skill"`;
- suggest merging/superseding redundant lessons.

The miner must be conservative. It should propose, not silently create skills.

### 7. Skill promotion

Skill promotion is how procedural memory graduates out of context stuffing.

Current scaffold:

```text
lesson with repeated evidence
        ↓
draft action_candidate
metadata.promotion_kind = "skill"
metadata.approval_flow = "memory_review_create_skill"
metadata.skill_name
metadata.skill_description
metadata.skill_body
metadata.source_lesson_ids
        ↓
Review UI: Create skill
        ↓
SkillService.create(...)
```

Required improvements:

- populate success/helpful counters from real usage/outcomes;
- generate skill drafts from multiple source lessons/episodes/artifacts, not just one lesson;
- include failure cases and user preferences in the draft;
- show evidence in Review:
  - source lessons;
  - representative episodes;
  - success/failure counts;
  - why this should become a skill;
- prevent duplicate skills for the same workflow;
- after skill creation, link skill metadata back to source memories;
- future activation should prefer “invoke this skill” over injecting the full playbook.

Skill candidates must be user-approved. No silent skill writes.

### 8. Skill activation

Creating skills is useless unless future tasks use them.

Activation should return candidate skills:

```text
skill_name
match_confidence
why_matched
source_memory_ids
required_inputs/constraints
```

Runtime behavior:

1. match current task to approved skills;
2. invoke the skill before responding when match is strong;
3. log skill activation;
4. log outcome;
5. use feedback to improve/deprecate skills.

If a skill exists, activation should avoid dumping the entire procedural lesson into context unless evidence is needed.

### 9. Background processors and cached health

Heavy processors must not run inline with hot UI requests.

Background/cached processors:

- memory health counters;
- duplicate fact clusters;
- conflict clusters;
- stale memory detection;
- dangling source detection;
- workflow mining;
- skill promotion candidates.

UI should read cached snapshots and trigger refresh explicitly. It must not block Memory page load on scans over thousands of facts.

### 10. Review UI as control plane

Memory Review should become the operator surface for the loop.

It should show:

- pending facts/lessons/artifacts;
- corrections and conflicts;
- duplicate merge proposals;
- skill/playbook candidates;
- source episodes and quotes;
- usage/outcome stats;
- why the candidate exists;
- approve/reject/edit/supersede controls.

For skill candidates, Review must show the full draft `SKILL.md` before creation.

## Data model additions

### Memory usage event

Logical table/model: `memory_usage_events`.

```text
id
run_id
session_id
project_id nullable
activation_bundle_id
memory_object_id
object_type
surface
rank nullable
score nullable
selection_reason nullable
used_by_model nullable
created_at
metadata json
```

### Memory outcome event

Logical table/model: `memory_outcome_events`.

```text
id
usage_id nullable
memory_object_id nullable
run_id nullable
session_id nullable
outcome
source
confidence
quote nullable
evidence_ref nullable
created_at
metadata json
```

### Workflow cluster

Logical table/model or cached processor output: `workflow_clusters`.

```text
id
scope
cluster_key
summary
trigger_description
source_episode_ids
source_lesson_ids
source_artifact_ids
usage_event_ids
success_count
failure_count
correction_count
last_seen_at
status: candidate | reviewed | promoted | rejected | stale
metadata json
```

### Skill promotion candidate metadata

Stored on `action_candidate`:

```json
{
  "promotion_kind": "skill",
  "approval_flow": "memory_review_create_skill",
  "skill_name": "...",
  "skill_description": "...",
  "skill_body": "...",
  "source_lesson_ids": [123],
  "source_episode_ids": [456],
  "source_artifact_ids": [789],
  "workflow_cluster_id": "...",
  "success_count": 4,
  "failure_count": 0,
  "correction_count": 0,
  "write_gate_reason": "repeated_successful_workflow"
}
```

## Implementation order

### Phase A — Activation logging

Add `memory_usage_events` and log every memory/skill injected into context or proposed to runtime.

Done means:

- every activation bundle has an id;
- every selected memory has a usage row;
- skill invocation is logged too;
- UI/debug route can show “why was this memory used?”

### Phase B — Outcome capture

Add `memory_outcome_events` and wire obvious signals:

- Review approve/reject;
- explicit correction commands;
- explicit “that helped / that was wrong” user language;
- task success/failure where known.

Done means useful/harmful/correction counts are populated from real events, not fake metadata.

### Phase C — Correction/supersession loop

Implement correction processing over active memories.

Done means explicit corrections produce corrected candidates and stale/conflicting memories do not stay equally active forever.

### Phase D — Cached health and processors

Move expensive health/consolidation/workflow scans to cached background snapshots.

Done means Memory UI never waits on full duplicate/conflict/health scans.

### Phase E — Workflow miner

Cluster repeated episodes/lessons/actions/outcomes into workflow candidates.

Done means the system can say:

```text
This workflow happened 5 times, succeeded 4 times, and has 3 source lessons. Propose a skill?
```

### Phase F — Real skill promotion

Upgrade skill promotion from single-lesson metadata threshold to workflow-cluster-based drafts.

Done means skill candidates contain:

- generated skill body;
- sources;
- usage/outcome evidence;
- why it should exist;
- duplicate-skill checks.

### Phase G — Skill-first activation

Activation should prefer approved skills for matching workflows.

Done means future tasks invoke skills and log outcomes, closing the loop.

## Evaluation

Do not measure success by unit tests alone. Measure whether memory reduces user friction and improves answers/actions.

Metrics:

- activation precision: selected memories that were actually useful;
- harm rate: selected memories that made output worse;
- correction closure: corrected memory stops reappearing incorrectly;
- review precision: approved vs rejected candidates;
- skill promotion precision: proposed skills that user approves;
- skill reuse: approved skills actually invoked later;
- context efficiency: token reduction from using skill references instead of long playbooks;
- repeat-friction: user repeats the same instruction less over time.

## Non-goals

- No model fine-tuning.
- No RL loop.
- No silent skill creation.
- No preserving broken legacy memory behavior for compatibility.
- No dumping raw history into prompts as “memory”.

## Summary

Current memory has the storage model, write gate, review scaffolding, and early skill-promotion path. The missing work is the closed loop:

```text
use memory → log usage → observe outcome → update/correct memory → mine repeated workflows → propose skill → use skill next time
```

Until that loop is wired, memory remains useful searchable context, but not a real learning system.
