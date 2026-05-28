# Memory System Reference

Updated: 2026-05-24

This is the working reference for ntrp memory architecture and the improvement roadmap. Use this doc before changing memory extraction, aggregation, recall, or Memory UI.

## Current Mental Model

Memory is a single `knowledge_objects` store with typed rows, statuses, provenance links, entity refs, embeddings, and metadata.

The intended hierarchy is:

```text
messages / runs / tool calls
        ↓
run_provenance          archived receipts/evidence; not normal memory
        ↓
memory_episode          coherent multi-turn/task narrative; source-of-truth layer
        ↓
extracted durable memory:
  - fact                atomic durable user-specific info, preferences, decisions
  - lesson              reusable conclusions, behavior preferences, implementation patterns
  - artifact            durable reusable outputs
  - action_candidate    review-only follow-up candidate, not durable memory
```

Important: this is not a clean tree in storage. It is a flat typed knowledge table connected through `source_ids`, metadata, entity refs, and supersession fields.

## Active Retained Types

The retained active memory model should stay simple:

- `fact`
- `lesson`
- `artifact`
- `memory_episode`

Review / evidence / compatibility types:

- `action_candidate` — review-only follow-up affordance.
- `procedure_candidate` — legacy/review residue only; should not be regenerated as draft/active durable memory.
- `run_provenance` — archived evidence/receipt layer.
- `pattern`, `procedure`, `entity_profile`, legacy `episode` — compatibility/legacy only; should not be used for new active memory.

## Current Live Shape

Latest known live DB shape from `~/.ntrp/memory.db`:

| Type | Status | Count |
|---|---:|---:|
| `artifact` | active | 68 |
| `fact` | active | 4084 |
| `fact` | superseded | 59 |
| `lesson` | active | 49 |
| `lesson` | superseded | 9 |
| `memory_episode` | active | 191 |
| `memory_episode` | archived | 42 |
| `procedure_candidate` | archived | 6 |
| `run_provenance` | archived | 50 |

Re-query before making decisions; these numbers are a snapshot.

## Episodes

Episodes are the source-of-truth narrative layer.

A `memory_episode` should be a coherent task/event segment, usually spanning multiple turns/runs. It stores:

- `session_id`
- `episode_status`: `open` / `closed`
- `source_turn_ids`
- `source_run_ids`
- boundary reason/confidence
- extraction ids once closed: `extracted_memory_ids`

Rules:

- User-visible conversation narrative can become episode text.
- Tool-only runs must not create standalone episodes.
- Raw tool output must not become episode title/text.
- Tool/run output belongs in `run_provenance` and source traces, not the episode layer.
- Episodes should be readable as a human diary of what happened.

Good episode style:

> User and assistant worked on memory cleanup, backend guardrails, and Memory Library UI polish.

Bad episode style:

> tool: bash returned ...

## Episode Creation Flow

On each run:

1. Capture archived `run_provenance`.
2. Build episode text from user-visible narrative only.
3. If there is no narrative text, do not create a new episode; optionally append provenance/source refs to the current open episode.
4. Run boundary classification:
   - continue current episode
   - close current episode
   - open new episode
5. Create/update/close a `memory_episode`.
6. When closed, extract durable memories.

Primary code:

- `apps/server/ntrp/memory/service.py`
  - `create_memory_episode(...)`
  - `capture_run_episode(...)`
  - `close_memory_episode(...)`
  - `_extract_memories_from_closed_episode(...)`

## Extraction From Episodes

When an episode closes, extraction proposes durable memory.

Current mapping:

- facts/preferences/decisions → `fact`
- reusable observations / implementation patterns / behavior changes → `lesson`
- reusable outputs → `artifact`
- follow-ups → `action_candidate`

Extraction must be conservative:

- omit transient implementation steps
- omit generic knowledge
- omit CI/tool noise
- omit weak guesses
- every durable memory must be useful months later
- every durable memory must be grounded in episode provenance

Legacy model output normalization:

```text
pattern              → lesson
procedure            → lesson
procedure_candidate  → lesson
```

This normalization exists because the retained model is intentionally simpler than old profile/procedure/pattern experiments.

## Fact Aggregation: Current State

Facts are currently mostly flat. Existing support includes:

- source links back to episodes/runs/turns
- entity extraction and entity refs
- embeddings
- FTS/entity/temporal/vector retrieval
- status and supersession fields

What is missing: a strong durable consolidation layer that clusters duplicate/overlapping facts, creates canonical facts, rolls up evidence, and marks weaker facts as superseded.

Do not reintroduce broad auto-generated profiles yet. The previous profile-style synthesis created noisy memory and was intentionally disabled/cleaned up.

## Recall / Activation

Recall is retrieval-time aggregation, not durable aggregation.

Activation currently:

1. Chooses object types depending on the query.
2. Searches via FTS, entity retrieval, temporal retrieval, and vector retrieval when available.
3. Scores candidates.
4. Fits selected memory into a prompt budget.
5. Records access when requested.

Normal activation should favor `fact`, `lesson`, and `artifact`. Episodes and run provenance should be pulled when the user asks for history, evidence, sources, or temporal context.

Primary code:

- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/activation_scoring.py`
- `apps/server/ntrp/knowledge/store.py`

## Next Improvement Roadmap

### 0. Activate latest backend guard

The newest backend guard for stripping bundled leading `tool:` transcript lines from episode text requires a server restart/reload before it protects future runs.

Constraint: the assistant must not restart the server itself. Ask the user to restart/reload.

### 1. Stabilize episode quality

Before improving aggregation, ensure the source layer is clean.

Checks:

- no tool-only episodes
- no `tool:`-prefixed episode text/title
- no raw provenance pretending to be narrative
- newest episodes read like coherent task summaries
- episode boundaries are neither too fragmented nor too broad

Useful DB check:

```sql
SELECT id, status, substr(content,1,500), metadata, created_at, updated_at
FROM knowledge_objects
WHERE object_type='memory_episode'
  AND (
    lower(content) LIKE 'tool:%'
    OR lower(content) LIKE 'episode: tool%'
    OR lower(content) LIKE '%tool result%'
    OR lower(content) LIKE '%tool_result%'
    OR lower(content) LIKE '%tool call%'
    OR lower(content) LIKE '%role: tool%'
  )
ORDER BY updated_at DESC
LIMIT 50;
```

### 2. Kill stale legacy extraction paths

`procedure_candidate` draft rows have regenerated before from stale `episode.close.model.v1`-style extraction. This must stay impossible.

Tasks:

- search all creation paths for `procedure_candidate`, `pattern`, `procedure`, and `entity_profile`
- enforce final write-boundary normalization/archival for legacy output if needed
- add tests proving episode-close extraction cannot create active/draft legacy retained types
- keep archived legacy rows only as residue/history

Expected durable retained types after normal usage:

```text
fact
lesson
artifact
memory_episode
```

### 3. Build fact consolidation

This is the largest missing layer.

Desired first pass:

#### A. Duplicate / near-duplicate detection

Cluster facts that say essentially the same thing.

Example:

```text
User prefers concise answers.
User likes short readable responses.
User asked not to over-explain.
```

These should become one stronger canonical fact or lesson.

#### B. Supersession flow

When a better memory exists:

```text
old fact      → superseded
canonical fact → active
```

Use existing supersession fields instead of hard-deleting.

#### C. Evidence rollup

A canonical fact should preserve provenance:

```text
canonical fact
  sources:
    episode 123
    episode 150
    turn xyz
```

#### D. Conflict detection

If candidate facts disagree, do not auto-merge.

Example conflict:

```text
User prefers verbose answers.
User prefers concise answers.
```

Route conflicts to review.

### 4. Add Memory UI support for hierarchy

Memory Library should expose relationships, not just rows.

Useful UI additions:

- Episode detail:
  - source turns/runs
  - extracted facts/lessons/artifacts
  - extraction status
- Fact detail:
  - source episode
  - related facts
  - superseded versions
  - canonical/replaced-by link
- Review queue:
  - merge duplicate facts
  - supersede old fact
  - reject noisy extraction
  - inspect conflicting memory
- Optional graph-ish view:

```text
Episode → Fact → Canonical Fact
Episode → Lesson
Episode → Artifact
```

### 5. Add memory quality checks/evals

Quality checks should prevent another noisy-memory regression.

Minimum checks:

- no tool-only episodes
- no active/draft legacy retained types
- no extracted durable memory without source episode/provenance
- duplicate fact rate
- contradiction/conflict rate
- extraction precision sample: out of 50 extracted memories, how many are useful 6+ months later?
- activation precision sample: when a query retrieves memory, was it actually helpful?

## Recommended Next Sprint

1. User restarts/reloads server so latest backend guard is active.
2. Verify DB health and newest episode quality.
3. Fix any remaining stale `procedure_candidate`/legacy extraction path.
4. Implement first-pass fact consolidation:
   - duplicate clusters
   - canonical fact proposal
   - supersede old facts
   - preserve source evidence
   - review UI for merge/conflict decisions
5. Add targeted tests and small quality metrics.

Do not build fancy profiles yet. Clean episodes plus clean fact consolidation come first.

## Source Map

Backend:

- `apps/server/ntrp/knowledge/models.py`
- `apps/server/ntrp/knowledge/store.py`
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/activation_scoring.py`
- `apps/server/ntrp/memory/service.py`
- `apps/server/ntrp/server/routers/knowledge.py`

Desktop:

- `apps/desktop/src/components/MemoryModal.tsx`
- `apps/desktop/src/components/memory/KnowledgeHomePane.tsx`
- `apps/desktop/src/components/memory/KnowledgeLibraryPane.tsx`
- `apps/desktop/src/components/memory/KnowledgeReviewPane.tsx`
- `apps/desktop/src/components/memory/RecallPane.tsx`
- `apps/desktop/src/lib/knowledgeViews.ts`

Related docs:

- `docs/internal/knowledge-system-architecture.md`
- `docs/internal/knowledge-pipeline.md`
- `docs/internal/knowledge-system-implementation-notes.md`
- `docs/internal/memory-benchmark-plan.md`
