# Slice 03 — Retrieval layer (`memory_items` hybrid query)

**Owner**: PM (ntrp) writes; tim approves; PM fires `codex exec`.
**Status**: DRAFT — awaiting tim approval.
**Spec ref**: `docs/internal/ntrp-memory-redesign-spec.md` §3.6, §2.4, §2.5.
**Predecessor**: slice 2 (chat connector). `memory_items`, `memory_items_fts`, `memory_items_vec` populated and live (verified: 3 episode rows present at brief time).
**Successor**: slice 4 (pattern finder).

---

## 1. Goal

Build a hybrid retrieval layer over `memory_items` and **burn `KnowledgeActivationService`** outright. The whole old activation stack (FACT/PATTERN/LESSON enum, `KnowledgeObjectRepository`, `MemorySearchSource`'s `knowledge_objects` query, `_object_candidates`) is dead code post slice 1 — `knowledge_objects` table does not exist. We replace it, we do not migrate it.

After this slice:

- New module `apps/server/ntrp/memory/retrieval.py` exposes `MemoryRetrieval.search(...)` over `memory_items`.
- New types `MemoryActivationRequest` / `MemoryActivationCandidate` / `MemoryActivationBundle` (kind = new enum: episode/observation/claim/skill/proposal/artifact_ref).
- `recall()`, `forget()`, `research`, `background`, HTTP `/knowledge/activation` route, and any other live caller of the old `KnowledgeActivationService` are repointed at the new bundle.
- `KnowledgeActivationService`, `KnowledgeObjectRepository`, `activation_scoring.object_candidate`, `MemorySearchSource` (the legacy one), and supporting helpers are deleted.
- ≥18 new unit tests in `apps/server/tests/memory/test_retrieval.py` pass.
- The broken `test_knowledge_activation.py` (35 failing) is **deleted** along with the code it tested. Tests for the new bundle stand in.

---

## 2. Scope — locked

### IN
- `apps/server/ntrp/memory/retrieval.py` — `MemoryRetrieval` class with `search(query, *, scope, kinds, limit, now=None) -> MemoryActivationBundle`.
- `apps/server/ntrp/memory/activation.py` — Pydantic types `MemoryActivationRequest`, `MemoryActivationCandidate`, `MemoryActivationBundle`, `MemoryActivationSelectionTrace`. No reuse of `KnowledgeObjectType`.
- Wire `MemoryRetrieval` into `KnowledgeRuntime` (alongside the chat connector from slice 2). Construct it once, share the `Embedder` + `aiosqlite.Connection`.
- Repoint these callers to `MemoryRetrieval` + `MemoryActivationBundle`:
  - `apps/server/ntrp/tools/memory.py` — `recall`, `forget`
  - `apps/server/ntrp/tools/research.py` — knowledge activation block
  - `apps/server/ntrp/tools/background.py` — knowledge activation block
  - `apps/server/ntrp/services/chat.py` — chat prompt-injection (the real hot path)
  - `apps/server/ntrp/operator/runner.py` — operator agent injection
  - `apps/server/ntrp/server/routers/knowledge.py` — `/knowledge/activation` endpoint
  - `apps/server/ntrp/memory/search_source.py` — `MemorySearchSource.scan()` rewritten to read `memory_items` (used by `apps/server/ntrp/search/` for the unified search index).
  - `apps/server/ntrp/benchmarks/longmemeval.py` — bench harness; pass new request shape.
  - `apps/server/ntrp/knowledge/evals.py` — protocol stub; update type imports to new bundle/request.
  - `apps/server/ntrp/skills/activation.py` — change `ActivationBundle` import to `MemoryActivationBundle`; logic stays (it short-circuits on `bundle.skills_to_use` being empty, see §3.5).
- Delete: `apps/server/ntrp/knowledge/activation.py`, `apps/server/ntrp/knowledge/activation_scoring.py`, `apps/server/ntrp/knowledge/store.py`'s search methods (`search_text`, `search_vector`, `search_entities`, `search_temporal`) — and any `KnowledgeObjectRepository` references the removed callers needed.
- Delete `apps/server/tests/test_knowledge_activation.py` (all 35 already broken).

### OUT
- Pattern finder, observation/claim generation (slice 4).
- Re-embedding pipeline / vector backfill (slice 1 territory).
- Graph walks, provenance traversal (later).
- UX/desktop changes. The desktop already uses `object_type` as a free string in TypeScript; new enum values will pass through. If a desktop pane explicitly switches on FACT/PATTERN/etc., it will silently render nothing — acceptable, fixed in UX slices 8/9.
- Editing `apps/server/ntrp/memory/service.py` beyond removing `knowledge_objects` repo wiring if it blocks deletions. Do not touch `FactMemory`, episode boundary classifier, embedder.
- Editing `apps/server/ntrp/memory/facts.py`.
- Editing `apps/server/ntrp/memory/connectors/*` (slice 2 territory).

### Cleanup philosophy
Hard swap. Delete the old stuff in the same diff. Do not leave commented-out code, do not feature-flag the old path back in. If a caller is too entangled to repoint cleanly, **comment in §9** before pressing on — do not silently leave a broken caller.

---

## 3. API contract

### 3.1 `MemoryRetrieval`

```python
# apps/server/ntrp/memory/retrieval.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Sequence

import aiosqlite
import numpy as np

from ntrp.embedder import Embedder
from ntrp.memory.activation import (
    MemoryActivationBundle,
    MemoryActivationCandidate,
    MemoryActivationRequest,
)


@dataclass(slots=True)
class _ScoreBreakdown:
    fts: float       # BM25 → normalized [0, 1]
    vector: float    # cosine sim [0, 1] (already normalized; vec0 stores cosine distance)
    recency: float   # Ebbinghaus exp(-age_days / TAU) ∈ (0, 1]
    feedback: float  # tanh-clamped usage signal ∈ [0, 1]
    confidence: float  # raw memory_items.confidence ∈ [0, 1]


class MemoryRetrieval:
    def __init__(
        self,
        conn: aiosqlite.Connection,
        embedder: Embedder,
        *,
        # weights are tunable but locked for slice 3; tests pin them
        w_fts: float = 0.35,
        w_vec: float = 0.35,
        w_recency: float = 0.10,
        w_feedback: float = 0.10,
        w_confidence: float = 0.10,
        recency_tau_days: float = 30.0,  # Ebbinghaus S ≈ month
        fts_top_k: int = 100,
        vec_top_k: int = 100,
    ): ...

    async def search(
        self,
        request: MemoryActivationRequest,
        *,
        now: datetime | None = None,
    ) -> MemoryActivationBundle: ...
```

### 3.2 Types

```python
# apps/server/ntrp/memory/activation.py
from typing import Literal
from pydantic import BaseModel, Field

MemoryItemKind = Literal[
    "episode", "observation", "claim", "skill", "proposal", "artifact_ref"
]

class MemoryActivationRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    scope: str | None = Field(default=None, max_length=500)
    kinds: list[MemoryItemKind] | None = None  # None = all kinds
    limit: int = Field(default=5, ge=1, le=50)
    task: str | None = Field(default=None, max_length=500)
    task_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    run_id: str | None = Field(default=None, max_length=200)
    surface: Literal["prompt", "context", "tool", "skill"] = "prompt"
    budget_chars: int = Field(default=1_200, ge=200, le=20_000)
    record_access: bool = False

class MemoryActivationCandidate(BaseModel):
    item_id: str
    kind: MemoryItemKind
    content: str
    score: float
    score_breakdown: dict[str, float]  # {fts, vector, recency, feedback, confidence}
    reasons: list[str]                   # ["fts_match", "vector_match", "recency_boost", ...]
    confidence: float
    scope: str
    tags: list[str]
    source_refs: list[dict]              # passthrough from memory_items.source_refs
    valid_from: str                      # ISO
    invalid_at: str | None
    created_at: str

class ActivationSkillSuggestion(BaseModel):
    # copied verbatim from knowledge/models.py — kept for slice 7 wiring.
    skill_name: str
    reason: str
    confidence: float = 0.5

class MemoryActivationBundle(BaseModel):
    query: str                                  # echoed back so callers can pass it to skill formatters
    scope: str | None
    kinds: list[MemoryItemKind] | None
    candidates: list[MemoryActivationCandidate]
    omitted: list[MemoryActivationCandidate]   # ranked but cut by budget_chars/limit
    used_chars: int
    prompt_context: str                         # markdown-formatted, ready to inject
    skills_to_use: list[ActivationSkillSuggestion] = []  # always [] in slice 3, populated by slice 7
```

### 3.3 Scoring formula

Final score (per candidate):

```
score = (w_fts * fts_norm)
      + (w_vec * vec_cos)
      + (w_recency * exp(-age_days / TAU))
      + (w_feedback * usage_weight)
      + (w_confidence * confidence)
```

where:
- `fts_norm` — normalize BM25 to [0,1] over the candidate pool (max-divide; if all zero, all zero).
- `vec_cos` — `1.0 - distance` from `vec0` (distance is cosine ∈ [0,2]; cosine *similarity* = `1 - distance/2`? Verify with vec0 docs — see §11 below. Pin the math in a test.)
- `age_days` — `(now - created_at).total_seconds() / 86400`.
- `usage_weight` — `tanh((helped - hurt) / 3) / 2 + 0.5` from `memory_items.usage` JSON → [0,1] with neutral=0.5.
- `confidence` — straight from column.

**Filters applied BEFORE scoring** (cheap SQL filters, narrow the candidate set):
- `status = 'active'`
- scope filter: `scope = ? OR scope = 'user'` if request scope is project; `scope = 'user'` if request scope is None.
- validity window: `julianday(valid_from) <= julianday(?)  AND (invalid_at IS NULL OR julianday(invalid_at) > julianday(?))`.
- kind filter: `kind IN (...)` if `request.kinds` provided.

**Hybrid candidate union**:
1. Run FTS top-K (default 100) with the filters above.
2. Embed the query, run vec0 top-K with `LIMIT ?` and stored embeddings.
3. UNION the two id sets, score each candidate fully (re-fetch row by id batch), rank by combined score, return `limit` selected + the rest as `omitted` (up to 50 omitted for trace).

**Important**: the vec0 search by itself does NOT see the SQL filters — we have to **filter post-vec by joining back to `memory_items`**. Same for FTS: `memory_items_fts` is content-only; join to `memory_items` for the WHERE clause.

### 3.4 `prompt_context` formatting

For each selected candidate, emit:

```
[{kind} · conf={confidence_bucket}]
{content_trimmed_to_budget_share}
```

Concatenate with `\n\n` between. `confidence_bucket` per spec §3.7: `low` if <0.4, `med` if <0.7, `high` otherwise.

Total length must be ≤ `request.budget_chars`. Greedy: fit candidates in score order, drop overflow into `omitted`.

### 3.5 Auto-skill activation — DEFERRED to slice 7

The old `ActivationBundle` carried `skills_to_use: list[ActivationSkillSuggestion]`. `services/chat.py` and `operator/runner.py` consume that list via `activated_skill_entries(bundle, registry)` to auto-fire skills based on memory hits. Per spec §3.5, the skill inducer + `is_toolable` gate is a separate slice (build order #7) — that's where this lives.

For slice 3:
- `MemoryActivationBundle.skills_to_use` is a typed field on the bundle, **always empty** (`= []`).
- `MemoryActivationBundle.query` is set (used by `activated_skill_entries` for skill arg formatting).
- `activated_skill_entries()` in `skills/activation.py` keeps its current logic; it short-circuits on `not bundle.skills_to_use` and returns `[]`. **Net behavior change**: auto-skill activation stops firing in chat / operator paths until slice 7 ships. Manual skill invocation via `use_skill` tool is unaffected.
- `record_auto_activated_skill_events()` stays callable; it will simply record zero entries.

Import in `skills/activation.py`: change
```python
from ntrp.knowledge.models import ActivationBundle, ActivationSkillSuggestion
```
to
```python
from ntrp.memory.activation import MemoryActivationBundle, ActivationSkillSuggestion
```

…and re-export `ActivationSkillSuggestion` from `apps/server/ntrp/memory/activation.py` (it's still a useful type for slice 7). The Pydantic model itself can be copied verbatim from `knowledge/models.py`.

---

## 4. SQL — exact queries

### 4.1 FTS top-K (filtered)

```sql
SELECT
    m.id,
    m.kind,
    m.content,
    m.confidence,
    m.scope,
    m.tags,
    m.source_refs,
    m.valid_from,
    m.invalid_at,
    m.created_at,
    m.usage,
    bm25(memory_items_fts) AS bm25_score
FROM memory_items_fts
JOIN memory_items m ON m.id = memory_items_fts.item_id
WHERE memory_items_fts MATCH ?
  AND m.status = 'active'
  AND (
        m.scope = 'user'
     OR m.scope = COALESCE(?, m.scope)
  )
  AND julianday(m.valid_from) <= julianday(?)
  AND (m.invalid_at IS NULL OR julianday(m.invalid_at) > julianday(?))
  -- kind filter applied in Python after fetch if request.kinds is set, OR inline below
ORDER BY bm25_score
LIMIT ?
```

If `request.kinds` is set, append `AND m.kind IN (?, ?, ...)` with parameterized placeholders.

Note: `bm25()` lower = better. We invert in scoring (smaller bm25 → higher fts_norm).

### 4.2 Vector top-K — two-step (vec0 KNN, then row fetch)

**Important**: vec0 virtual tables cannot be joined in a single query with `WHERE embedding MATCH ?` filters mixed with column predicates from the joined table. The existing pattern in `observations.py:500` and `facts.py` is two queries:

```sql
-- Step 1: vec0 KNN (no other predicates allowed in the WHERE)
SELECT v.item_id, v.distance
FROM memory_items_vec v
WHERE v.embedding MATCH ? AND k = ?
ORDER BY v.distance
```

```sql
-- Step 2: fetch + filter
SELECT id, kind, content, confidence, scope, tags, source_refs,
       valid_from, invalid_at, created_at, usage
FROM memory_items
WHERE id IN ({placeholders})
  AND status = 'active'
  AND (scope = 'user' OR scope = COALESCE(?, scope))
  AND julianday(valid_from) <= julianday(?)
  AND (invalid_at IS NULL OR julianday(invalid_at) > julianday(?))
```

Implementation notes:
- Serialize query vector with `ntrp.database.serialize_embedding(emb)` (existing helper at `apps/server/ntrp/database.py:8` — handles normalization + float32 + tobytes).
- `k = ?` is the vec0 KNN parameter — set to `vec_top_k` (default 100). vec0 returns top-K by distance; we re-filter in step 2.
- **Cosine similarity = `1.0 - distance`** (codebase convention — see `observations.py:518` `1 - distances[oid]`). Pin in test 15.
- If kind filter is set, include `AND kind IN (?, ?, ...)` in step 2.

---

## 5. Files (final paths)

### Created
- `apps/server/ntrp/memory/retrieval.py` — `MemoryRetrieval` class.
- `apps/server/ntrp/memory/activation.py` — Pydantic types.
- `apps/server/tests/memory/test_retrieval.py` — 18+ tests.

### Modified
- `apps/server/ntrp/server/runtime/knowledge.py` — construct `MemoryRetrieval` next to `ChatConnector`; expose as `runtime.memory_retrieval`.
- `apps/server/ntrp/server/runtime/__init__.py` (or wherever services dict is built) — register `memory_retrieval` for tool execution context. Verify the exact path via grep before editing.
- `apps/server/ntrp/tools/memory.py` — `recall`, `forget` switch to `MemoryRetrieval.search()`.
- `apps/server/ntrp/tools/research.py` — same.
- `apps/server/ntrp/tools/background.py` — same.
- `apps/server/ntrp/server/routers/knowledge.py` — `/knowledge/activation` route returns `MemoryActivationBundle`.
- `apps/server/ntrp/memory/search_source.py` — `MemorySearchSource.scan()` reads `memory_items` with `status='active'`.

### Deleted (full dead cluster — verified pre-flight by PM)
- `apps/server/ntrp/knowledge/activation.py`
- `apps/server/ntrp/knowledge/activation_scoring.py`
- `apps/server/ntrp/knowledge/activation_bundles.py`
- `apps/server/ntrp/knowledge/activation_query.py`
- `apps/server/ntrp/knowledge/activation_evidence.py`
- `apps/server/tests/test_knowledge_activation.py`
- `apps/server/ntrp/knowledge/store.py`: remove `search_text`, `search_vector`, `search_entities`, `search_temporal` methods. If `KnowledgeObjectRepository` ends up with no live callers, delete the file. Verify with `grep -rn KnowledgeObjectRepository apps/server/` before final delete.
- Any imports/re-exports in `apps/server/ntrp/knowledge/__init__.py` referencing the deleted symbols.

PM pre-flight verified these files form a closed cluster: each is only imported by another file in this cluster or by `KnowledgeActivationService` itself.

### NOT TOUCHED (DO NOT FIX)
- `apps/server/ntrp/memory/service.py` — already heavily dirty in working tree; leave the broken legacy methods alone. They will go away in a later slice. If Codex sees imports break because of deletions above, it should add `# noqa`-style stubs ONLY if the file is otherwise un-touchable. Prefer: delete the failing import + the dead method on `service.py`. **Coordinate with tim if unclear.**
- `apps/server/ntrp/memory/facts.py`.
- `apps/server/ntrp/memory/connectors/*` (slice 2).
- `apps/server/ntrp/memory/items_store.py`, `buffers_store.py` (slice 2).
- Anything under `apps/desktop/`.

---

## 6. Schema reference (live-verified)

`memory_items` (live, `~/.ntrp/memory.db` schema_version=31):

```
id            TEXT PK
kind          TEXT CHECK ∈ {episode, observation, claim, skill, proposal, artifact_ref}
content       TEXT
provenance    TEXT CHECK ∈ {recorded, inferred, user_authored, external}
source_refs   TEXT (JSON array of {kind, ref, captured_at})
confidence    REAL CHECK [0, 1] DEFAULT 0.5
status        TEXT CHECK ∈ {active, superseded, archived} DEFAULT 'active'
valid_from    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
invalid_at    TIMESTAMP NULL
scope         TEXT DEFAULT 'user'
tags          TEXT (JSON array) DEFAULT '[]'
artifact_ref  TEXT NULL
usage         TEXT (JSON {activated, helped, hurt, ignored}) DEFAULT '{"activated":0,"helped":0,"hurt":0,"ignored":0}'
feedback      TEXT (JSON {thumbs_up, thumbs_down, corrections})
created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

Indexes already present (verified):
- `idx_memory_items_status_scope_kind` — primary hot path
- `idx_memory_items_valid_from`, `idx_memory_items_invalid_at`
- `idx_memory_items_updated_at`

FTS: `memory_items_fts(item_id UNINDEXED, content)`, tokenize unicode61.
Vec: `memory_items_vec(item_id TEXT PK, embedding float[1536] distance_metric=cosine)`.

**Live embedding dim = 1536.** Tests must use 1536-dim vectors (cheap — same as slice 2).

`MemoryItemsRepository` (slice 2) is the canonical reader/writer for `memory_items`. **Do NOT bypass it for writes.** For reads, `MemoryRetrieval` will issue SQL directly (justified — joins to FTS/vec are hot path and the repo doesn't have a hybrid surface).

---

## 7. Tests (final list)

File: `apps/server/tests/memory/test_retrieval.py`

Pattern: in-memory aiosqlite with `sqlite-vec` extension loaded, schema bootstrapped via the same migration entry as slice 2's tests use, then seed `memory_items` + FTS + vec rows directly, then call `MemoryRetrieval.search(...)`.

1. `test_search_empty_returns_empty_bundle` — zero rows in `memory_items` → bundle with empty `candidates`, empty `prompt_context`, `used_chars=0`.
2. `test_search_fts_only_match` — seed 3 rows; query matches one by content lexically; only that one in candidates with `reasons=["fts_match"]`.
3. `test_search_vector_only_match` — seed 3 rows with distinct vectors; query embedding near one; that one ranks first with `reasons=["vector_match"]`.
4. `test_search_hybrid_fts_and_vector` — seed rows where one matches FTS only, another matches vector only, a third matches both; the both-match item ranks highest (boosted by sum).
5. `test_search_status_filter_active_only` — seed `active`, `superseded`, `archived`; only `active` returned.
6. `test_search_scope_filter_user_and_project` — seed scope='user' and scope='proj_abc'; request scope='proj_abc' → both 'user' and 'proj_abc' returned; request scope=None → only 'user'.
7. `test_search_kind_filter_subset` — request `kinds=["claim", "skill"]` → episodes excluded.
8. `test_search_validity_window_excludes_future_valid_from` — seed row with `valid_from > now`; not returned.
9. `test_search_validity_window_excludes_expired_invalid_at` — seed row with `invalid_at < now`; not returned. Seed row with `invalid_at > now`; included.
10. `test_search_recency_decay_orders_newer_higher` — two rows identical except `created_at` (one 7d ago, one 90d ago); newer ranks higher when all else equal.
11. `test_search_usage_feedback_boosts_helpful_items` — two rows identical; one has `usage={"activated":10,"helped":8,"hurt":1,"ignored":1}`, other neutral; helpful ranks higher.
12. `test_search_confidence_factor_pulls_high_confidence_up` — two rows tied on all else; higher `confidence` wins.
13. `test_search_respects_limit` — seed 10 matching rows; `limit=3` → 3 in `candidates`, 7 in `omitted` (capped at 50).
14. `test_search_respects_budget_chars` — seed 5 rows each 500 chars; `budget_chars=600` → 1 selected, rest omitted.
15. `test_score_breakdown_shape_and_components` — every candidate has all 5 keys in `score_breakdown`; values ∈ [0,1]; sum-weighted equals `score`.
16. `test_prompt_context_format_includes_kind_and_confidence_bucket` — output contains `[claim · conf=high]` etc.
17. `test_search_handles_no_vec_rows_gracefully` — content rows exist but no vec rows (simulate pre-embed); FTS-only path still returns sensible results.
18. `test_search_vector_dim_mismatch_raises_clear_error` — embedder returns dim=768, table is dim=1536 → `MemoryRetrieval.search` raises `ValueError` with explicit message (do NOT silently degrade).

Required output:
```text
============================== 18 passed in <2s ==============================
```

(More tests welcome — these are the floor.)

---

## 8. Out of scope

- Re-embedding pipeline. We assume vec rows are written by `MemoryItemsRepository.insert()` (slice 2). If they aren't there, FTS-only mode kicks in (test 17).
- Backfill of vec rows for items already in DB without vectors.
- Replacing the embedder. Whatever `KnowledgeRuntime` injects today is what we use.
- Pattern finder / observation creation (slice 4).
- Editing the desktop UI to consume new kinds.
- Graph walks, parent/child traversal, contradictions surfacing.
- Replacing the unified search system (`apps/server/ntrp/search/`) beyond repointing `MemorySearchSource`.
- Re-running the broken `test_knowledge_activation.py` tests — they are deleted, not fixed.

---

## 9. Open clarifications (resolve in Codex inspection or callout)

1. **vec0 distance → similarity math.** RESOLVED pre-flight: codebase convention is `cos_sim = 1.0 - distance` (see `apps/server/ntrp/memory/store/observations.py:518`). Embedder normalizes (verified in `embedder.py:19-21`). Pin in test 15 with a hand-crafted vector pair so future regressions show up.
2. **`MemorySearchSource` rewrite.** Today's `scan()` returns *all* knowledge objects (≤10k). New version reads `memory_items` `WHERE status='active'`. Confirm the `apps/server/ntrp/search/` indexer can handle the new `RawItem.source_id="memory_item:{id}"` shape without dedupe collisions against old IDs in its index. If the search index has stale `knowledge:NNN` entries, they will become orphans — acceptable (search index rebuilds).
3. **Deletion of `KnowledgeObjectRepository`.** Some `memory/service.py` methods import it for completely unrelated purposes (the dirty-tree `KnowledgeConflictReviewService` etc.). Confirm whether deleting the file breaks `service.py` compilation. If yes, leave `store.py` in place but with only the non-search methods. **Codex: report which option you took.**
4. **Recording usage events.** Slice 2 brief mentioned a usage-event flow. For slice 3, when `request.record_access=True`, write a row to... what? There is no `memory_activation_events` table. **Decision: log via `_logger.info("memory_activation", ...)` only; no DB write in slice 3.** Slice 6+ adds a real events table.
5. **HTTP route response shape.** `/knowledge/activation` callers (desktop) currently expect `ActivationBundle` fields. New `MemoryActivationBundle` has different field names. Desktop will see 4xx field validation errors on the response IF it's typed strictly. **Codex: verify the desktop's `apps/desktop/src/api.ts` whether it parses the response strictly. If yes, document the break in the brief output, do not fix.**

---

## 10. Migration / DB impact

- No schema changes.
- No data writes.
- No new indexes (existing slice-1 indexes are sufficient per §6).
- Reads only, plus deletion of dead Python files.

---

## 11. Codex prompt (verbatim — paste into `codex exec`)

```
You are implementing slice 3 of the ntrp memory redesign. Read this brief end-to-end before writing code:

  docs/internal/slices/slice-03-retrieval.md

Authoritative spec (only relevant sections — §3.6, §2.4–2.5):
  docs/internal/ntrp-memory-redesign-spec.md

You are working in the repo at /Users/escept1co/src/ntrp. The default cwd for tools is /Users/escept1co/src/ntrp.

GOAL
Build a hybrid retrieval layer over memory_items and BURN the old KnowledgeActivationService outright. The old knowledge_objects table no longer exists — every code path in apps/server/ntrp/knowledge/activation.py is dead. Do not migrate it. Delete it. Replace with new types and a new query path.

HARD CONSTRAINTS — VIOLATING ANY OF THESE FAILS THE SLICE
- DO NOT edit apps/server/ntrp/memory/service.py except to remove imports broken by deletions in this slice. If service.py is too entangled, document the entanglement at the top of your final summary instead of touching it.
- DO NOT edit apps/server/ntrp/memory/facts.py at all.
- DO NOT edit apps/server/ntrp/memory/connectors/* (slice 2 territory).
- DO NOT edit apps/server/ntrp/memory/items_store.py or buffers_store.py.
- DO NOT edit anything under apps/desktop/.
- DO NOT try to be helpful and fix the broken legacy methods on knowledge/store.py — DELETE the search_* methods (search_text, search_vector, search_entities, search_temporal). If the whole file ends up uncalled, delete it.
- DO NOT keep the old activation code commented out, behind a flag, or as a "fallback". Burn it. Delete it.
- DO NOT add a usage-event DB write. Log via _logger only (slice 3 §9.4).
- DO NOT skip any of the 18 enumerated tests in §7 of the brief.

DELIVERABLES
1. New files:
   - apps/server/ntrp/memory/retrieval.py
   - apps/server/ntrp/memory/activation.py (types only — no service logic)
   - apps/server/tests/memory/test_retrieval.py (18+ tests, per §7)
2. Modified files (caller migration):
   - apps/server/ntrp/server/runtime/knowledge.py (construct MemoryRetrieval, expose .memory_retrieval)
   - The services-dict location that wires `memory_retrieval` into ToolExecution context (grep for `services["memory"]` to find it)
   - apps/server/ntrp/tools/memory.py (recall, forget)
   - apps/server/ntrp/tools/research.py
   - apps/server/ntrp/tools/background.py
   - apps/server/ntrp/services/chat.py — chat prompt-injection
   - apps/server/ntrp/operator/runner.py — operator injection
   - apps/server/ntrp/server/routers/knowledge.py — HTTP route returns new bundle
   - apps/server/ntrp/memory/search_source.py — repoint to memory_items
   - apps/server/ntrp/benchmarks/longmemeval.py — bench harness type swap
   - apps/server/ntrp/knowledge/evals.py — protocol stub type swap
   - apps/server/ntrp/skills/activation.py — import swap only; logic unchanged (auto-skill stays dormant until slice 7 per brief §3.5)
3. Deleted files:
   - apps/server/ntrp/knowledge/activation.py
   - apps/server/ntrp/knowledge/activation_scoring.py
   - apps/server/tests/test_knowledge_activation.py
   - Re-exports of the above in apps/server/ntrp/knowledge/__init__.py
   - apps/server/ntrp/knowledge/store.py (if uncalled) OR just its search_* methods
4. The exact pytest output below.

REQUIRED PYTEST OUTPUT
Run: `cd /Users/escept1co/src/ntrp && apps/server/.venv/bin/python -m pytest apps/server/tests/memory/test_retrieval.py -v`
Must report `18 passed` (or more, if you add bonus tests) with zero failures.

Additionally run:
  cd /Users/escept1co/src/ntrp && apps/server/.venv/bin/python -m pytest apps/server/tests/memory/ -v
  cd /Users/escept1co/src/ntrp && apps/server/.venv/bin/python -m pytest apps/server/tests/test_memory_tools.py apps/server/tests/test_research_tools.py apps/server/tests/test_background_agent_runs.py apps/server/tests/test_operator_activation_context.py -v
The first must still show slice-1 + slice-2 tests passing. The second is allowed to have failures from contract changes (recall/forget/research/background now return MemoryActivationBundle instead of ActivationBundle) — REPORT each failure with one-line analysis in your final summary; do NOT mutate the assertion expectations to make them pass.

Also run `ruff check apps/server/ntrp/memory/retrieval.py apps/server/ntrp/memory/activation.py apps/server/tests/memory/test_retrieval.py` — must be clean.

WHEN DONE — POST AS A SINGLE FINAL MESSAGE
1. Files Changed (created/modified/deleted with one-line description each)
2. Exact pytest output from the required test run
3. Any deviations from the brief (e.g. couldn't delete store.py because X) — with file/line refs
4. Any contract failures in the secondary test run with one-line analysis each
5. The vec0 distance → similarity formula you implemented + the test that pins it (test 15 from §7)

Begin now. No further questions — the brief is comprehensive.
```

---

## 12. PM review checklist (run after Codex returns, before saying "done")

- [ ] All 18 tests from §7 present in `test_retrieval.py` and passing.
- [ ] `pytest apps/server/tests/memory/ -v` still green on slice-1 + slice-2 tests.
- [ ] `apps/server/ntrp/knowledge/activation.py` deleted.
- [ ] `apps/server/ntrp/knowledge/activation_scoring.py` deleted.
- [ ] `apps/server/tests/test_knowledge_activation.py` deleted.
- [ ] No remaining `KnowledgeActivationService` references: `grep -rn KnowledgeActivationService apps/server/` returns zero.
- [ ] No remaining `ActivationBundle` / `ActivationRequest` / `ActivationCandidate` references outside `apps/desktop/`: `grep -rn 'ActivationBundle\|ActivationRequest\|ActivationCandidate' apps/server/` returns zero.
- [ ] `services/chat.py` no longer imports from `ntrp.knowledge.activation` or `ntrp.knowledge.models`.
- [ ] `operator/runner.py` no longer imports from `ntrp.knowledge.activation` or `ntrp.knowledge.models`.
- [ ] `skills/activation.py` imports from `ntrp.memory.activation`, not `ntrp.knowledge.models`.
- [ ] `bundle.skills_to_use` is `== []` everywhere `MemoryRetrieval.search()` returns (verify by reading retrieval.py).
- [ ] Auto-skill activation is documented as deferred to slice 7 in a comment in `skills/activation.py` near `activated_skill_entries`.
- [ ] `apps/server/ntrp/memory/service.py` and `facts.py` unmodified (or modified only to remove broken imports — diff inspection).
- [ ] `apps/server/ntrp/memory/connectors/*`, `items_store.py`, `buffers_store.py` unmodified.
- [ ] `apps/desktop/` unmodified.
- [ ] ruff clean on new files.
- [ ] vec0 distance math: pinned in a test with hand-computed expected similarity.
- [ ] No `_logger.error` or `_logger.warning` calls in `retrieval.py` that hide real errors (errors should propagate; only log on truly recoverable degraded paths).

If any box is unchecked → write a correction brief, do not commit.

---

## 13. Done criteria

- All boxes in §12 checked.
- `pytest apps/server/tests/memory/test_retrieval.py -v` → 18+ passed.
- `pytest apps/server/tests/memory/` → all slice-1 + slice-2 + slice-3 tests passing.
- Live smoke test (separate runbook: `slice-03-smoke-test.md`): server restarts cleanly, `recall(query="...")` from a tool call returns a `MemoryActivationBundle` with at least the 3 existing episode rows when the query is broad enough.
- Codex diff reviewed against this brief by tim before commit.

---

## 14. Status

- DRAFT — awaiting tim approval (A: approve + fire / B: yolo / C: revise).
