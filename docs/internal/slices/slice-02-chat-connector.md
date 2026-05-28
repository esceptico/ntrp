# Slice 02 — chat connector + episode close

Status: DESIGN PASS DONE (2026-05-28). Awaiting tim approval before Codex invocation.
Parent spec: `docs/internal/ntrp-memory-redesign-spec.md` (spec wins).
Depends on: slice 01 (schema) — LANDED 2026-05-27, schema_version=31 in live DB.
Workflow split: PM writes brief → tim approves → codex exec headless → PM reviews diff.

---

## 1. Goal

Land the **chat connector**: the first writer to the new memory schema. It watches the `RunCompleted` event stream, maintains one `episode_buffers` row per active `(scope, source_kind='chat_msg')` pair, and on a boundary trigger fires a close that:

1. Generates an episode summary via LLM.
2. Inserts a `memory_items` row with `kind='episode'`, `provenance='inferred'`, populated `source_refs` JSON, computed confidence.
3. Carries the trailing window (last 5 turns + their source_refs) into the next buffer.

After this slice, real episodes start accumulating from live chat. Nothing reads them yet — that's slice 3.

---

## 2. Boundary triggers — locked

| Trigger | Default | Source |
|---|---|---|
| turn budget | 50 turns | spec §2.5, §3.2 |
| token budget | 8 000 tokens (cumulative across the buffer) | spec §2.5 |
| idle gap | 10 min since `last_activity_at` | spec §2.5 |
| topic shift | cosine drop > 0.3 (current-turn vec vs running centroid) | spec §2.5 |
| explicit close | session end / `/wrap` / `/goal ` markers (reuse `EpisodeBoundaryClassifier._EXPLICIT_SWITCH_MARKERS`) | existing module |
| overlap carry | last 5 turns (or first turn if buffer ≤5) into next buffer | spec §3.2 |

First-of: whichever trigger fires first closes the buffer.

**Granularity clarification**: one "turn" = one `RunCompleted` event = one user message + the assistant's resulting reply (which may include tool calls). `tokens` = `event.usage.total_tokens` accumulated.

**Centroid**: running mean of L2-normalized turn embeddings, re-normalized after each update. Cosine drop is `1 - dot(turn_vec, centroid_vec)` because vectors are L2-normalized (verified in `apps/server/ntrp/embedder.py:_normalize`).

**Centroid storage**: `episode_buffers.running_centroid_vec` is `BLOB`. Serialize with `vec.astype('float32').tobytes()`, deserialize with `np.frombuffer(blob, dtype='float32')`. Same float32 wire format as the existing `memory_items_vec` rows.

**Buffer schema** (confirmed against live DB):
- columns: `id, scope, source_kind, started_at, last_activity_at, turn_count, tokens, content_so_far, source_refs_so_far (TEXT JSON), running_centroid_vec (BLOB), closed_at`
- unique partial index: `(scope, source_kind) WHERE closed_at IS NULL` → IntegrityError on concurrent open attempt.
- index: `idx_episode_buffers_last_activity ON last_activity_at` — use this for the idle sweeper query.

---

## 3. Hook point — locked

The connector subscribes to **the outbox `OUTBOX_RUN_COMPLETED` queue**, same path that `_on_run_completed` in `apps/server/ntrp/server/runtime/outbox.py` already consumes. This gives us:

- Durable at-least-once delivery (DB-backed outbox already in place).
- Replayable on failure (existing infrastructure).
- Isolation: if the chat connector errors out, it doesn't kill the existing knowledge-objects pipeline (each handler runs independently).

**Concrete integration:** `apps/server/ntrp/outbox/worker.py:58` stores handlers as `self._handlers[event_type] = handler` — **one handler per event type, full stop**. So we chain inside the existing `_on_run_completed` body: fire `ChatConnector.on_run_completed` first, then the existing knowledge assimilation. Each call in its own `try/except` so neither breaks the other. The chain order matters: chat connector first means a slow LLM summary call adds latency to the outbox handler. Acceptable — outbox runs in the background, not in the request path.

---

## 4. New module layout

```
apps/server/ntrp/memory/
├── connectors/
│   ├── __init__.py
│   ├── chat.py              # ChatConnector orchestration (this slice)
│   ├── episode_close.py     # close trigger evaluation + summary call (this slice)
│   └── idle_sweeper.py      # periodic close of idle buffers (this slice)
├── items_store.py            # minimal memory_items writer used by all connectors (this slice)
├── buffers_store.py          # episode_buffers CRUD (this slice)
└── store/                    # (existing — base.py, migrations.py, …)
```

- `items_store.MemoryItemsRepository`:
  - `insert_item(item: MemoryItemInsert) -> str` — returns generated `id`.
  - `id` generation: `uuid.uuid4().hex` (matches slice 1 + codebase convention).
  - Writes to `memory_items`. Triggers handle FTS sync automatically.
  - Also writes the vec row via `memory_items_vec` when `embedding` provided.
  - NOT yet exposed as a query API — slice 3.

- `buffers_store.EpisodeBufferRepository`:
  - `find_open(scope, source_kind) -> EpisodeBuffer | None`
  - `create(scope, source_kind, *, carry: BufferCarry | None = None) -> EpisodeBuffer` — `carry` is the overlap-window payload from the previous buffer (last 5 turns' content + source_refs + centroid). When `None`, this is a fresh buffer.
  - `apply_turn(buffer_id, turn: TurnUpdate) -> EpisodeBuffer` — appends one turn: increments turn_count, adds tokens, appends content, appends source_ref, updates centroid, sets last_activity_at=now.
  - `close(buffer_id) -> None` — sets `closed_at = now`.
  - `find_idle(threshold_minutes) -> list[EpisodeBuffer]` — for the sweeper.

  Dataclass shapes:
  ```python
  @dataclass
  class BufferCarry:
      content: str                 # concatenation of last N turns' content
      source_refs: list[dict]      # last N turns' source_refs
      centroid: np.ndarray | None  # running centroid from the closed buffer
      turn_count: int              # = N (used as starting count for the new buffer)
      tokens: int                  # tokens in the carry window

  @dataclass
  class TurnUpdate:
      content: str
      tokens: int
      source_ref: dict             # {"kind":"chat_msg","ref":run_id,"captured_at":iso}
      embedding: np.ndarray
  ```

- `connectors/chat.ChatConnector`:
  - Constructor: `MemoryItemsRepository`, `EpisodeBufferRepository`, `Embedder`, LLM client, `EpisodeBoundaryClassifier` instance.
  - `async def on_run_completed(event: RunCompleted) -> None`:
    1. Resolve `scope` from `event.session_id` (use existing scope-resolution helper if present, else default to `'user'` — flagged §9.1).
    2. Extract turn text: concat of last user message + assistant final reply from `event.messages`.
    3. Embed the turn (L2-normalized) via `Embedder.embed_one`.
    4. Find or create buffer.
    5. Evaluate boundary triggers (see §5).
    6. If close fires: call `episode_close.finalize_buffer(buffer, …)`; else just update buffer.
  - Errors caught + logged, never re-raised (the user's chat is more important than memory accumulation).

- `connectors/episode_close.finalize_buffer`:
  - LLM summary call: prompt template stored as module constant `_SUMMARY_PROMPT`. Model: same model the existing `ModelBackedEpisodeBoundaryClassifier` uses (Codex inspects to find the exact model parameter — flagged §9.3).
  - Compute confidence via the §3.7 formula from spec. Fresh episode: provenance=inferred (0.75), no parents (0.5×), decay=1.0, no usage (0.85×) ⇒ 0.319. Stored as float, bucket=low.
  - Build `source_refs[]` from the buffer's accumulated `source_refs_so_far`.
  - Insert via `MemoryItemsRepository.insert_item`. Embed the summary too (vec row).
  - Close the buffer.
  - Open the next buffer with the overlap carry (last 5 turns concat into `content_so_far`, source_refs trailing slice).

---

## 5. Boundary trigger evaluation — concrete

```python
def evaluate_triggers(buffer, turn_vec, turn_tokens, now) -> tuple[bool, str | None]:
    """Returns (should_close, reason_label). Evaluated BEFORE applying the new turn."""
    if buffer.turn_count + 1 >= TURN_BUDGET:                # default 50
        return True, "turn_budget"
    if buffer.tokens + turn_tokens >= TOKEN_BUDGET:         # default 8000
        return True, "token_budget"
    if buffer.last_activity_at + IDLE_GAP < now:            # 10 min
        return True, "idle_gap"
    if buffer.running_centroid_vec is not None:
        drop = 1.0 - float(np.dot(turn_vec, buffer.running_centroid_vec))
        if drop > TOPIC_SHIFT_THRESHOLD:                    # 0.3
            return True, "topic_shift"
    return False, None
```

Explicit close (`EpisodeBoundaryClassifier` markers / `/wrap`) is evaluated separately before this function — reuses existing classifier output.

**Idle-gap sweep**: a separate periodic asyncio task wakes every 60s, calls `EpisodeBufferRepository.find_idle(10)`, forces close on each result. Started in `OutboxRuntime.start`, stopped in `OutboxRuntime.stop`. Same `asyncio.create_task` + `CancelledError` pattern as the existing reembed task in `memory/facts.py`.

---

## 6. Files (final paths)

**New:**
- `apps/server/ntrp/memory/items_store.py` (~80 LOC, repo + dataclass)
- `apps/server/ntrp/memory/buffers_store.py` (~120 LOC, repo + dataclass)
- `apps/server/ntrp/memory/connectors/__init__.py` (empty)
- `apps/server/ntrp/memory/connectors/chat.py` (~180 LOC)
- `apps/server/ntrp/memory/connectors/episode_close.py` (~120 LOC)
- `apps/server/ntrp/memory/connectors/idle_sweeper.py` (~60 LOC)
- `apps/server/tests/memory/connectors/__init__.py`
- `apps/server/tests/memory/connectors/test_chat_connector.py` (~300 LOC, tests in §7)

**Modified:**
- `apps/server/ntrp/server/runtime/outbox.py` — chain chat handler in `_on_run_completed`. Add idle sweeper start/stop to `start()` / `stop()`. ~20 LOC delta.
- `apps/server/ntrp/server/runtime/knowledge.py` — instantiate `MemoryItemsRepository`, `EpisodeBufferRepository`, `ChatConnector` inside `_create_memory` (alongside `MemorySearchSource`). Reuse the existing `self.memory.db` connection. Reuse the existing `self.embedding` Embedder. Expose `self.chat_connector` so `OutboxRuntime` can reach it via the same `_get_memory_service` plumbing. Tear down in `_close_memory`. ~25 LOC delta.

**Wiring detail (to save Codex inspection time):** `KnowledgeRuntime._create_memory` already builds `FactMemory` (which holds `self.memory.db`) and `MemoryService(self.memory)`. The chat connector's repositories should share `self.memory.db` so they write to the same SQLite file. `OutboxRuntime` already has `_get_memory_service` — add an analogous `_get_chat_connector` (or `_get_knowledge_runtime`) so the chain in `_on_run_completed` can fetch the connector without circular imports.

**Live schema reference (`sqlite3 ~/.ntrp/memory.db ".schema"`):**
- `memory_items` columns: `id, kind, content, provenance, source_refs (TEXT JSON), confidence (REAL CHECK 0..1), status, valid_from, invalid_at, scope (default 'user'), tags (TEXT JSON), artifact_ref, usage (TEXT JSON with activated/helped/hurt/ignored), feedback (TEXT JSON), created_at, updated_at`
- `memory_items.kind` CHECK: `('episode', 'observation', 'claim', 'skill', 'proposal', 'artifact_ref')` — use `'episode'`.
- `memory_items.provenance` CHECK: `('recorded', 'inferred', 'user_authored', 'external')` — use `'inferred'`.
- `memory_items.status` CHECK: `('active', 'superseded', 'archived')` — use `'active'` for fresh episodes.
- `memory_items_vec`: `id TEXT PRIMARY KEY` (matches `memory_items.id`). Insert one vec row per memory_item row that has an embedding.
- `memory_item_parents`: edge table for slice 4 use. Slice 2 inserts 0 rows here (no observation children yet).

**Explicitly NOT modified in this slice:**
- `memory/facts.py`, `memory/service.py` — still broken; slice 3 replaces them.
- `memory/search_source.py` — still queries dropped `knowledge_objects` table; broken by design until slice 3.
- The legacy `KnowledgeObjectRepository.assimilate_run_completed` — still try/except'd by tim's hot patch. Slice 3 retires it.
- Spec / scratchpad / other slice briefs.

**Codex: do NOT try to be helpful and fix the broken legacy paths.** They are intentionally broken between slices 1 and 3. The try/except wrappers exist to keep the server running. If you touch them, you will break the slice plan.

---

## 7. Tests (final list)

In `tests/memory/connectors/test_chat_connector.py`:

1. **`test_first_msg_creates_buffer`** — no open buffer + msg → buffer created, fields populated (turn_count=1, tokens=N, content_so_far=text, source_refs_so_far=[{kind:'chat_msg',ref:run_id,…}]).
2. **`test_subsequent_msg_updates_buffer`** — open buffer + msg → fields updated (turn_count++, content appended, refs grow, centroid moves).
3. **`test_turn_budget_close`** — 50th turn → close fires, `memory_items` row written with kind='episode', buffer.closed_at set.
4. **`test_token_budget_close`** — accumulated tokens cross 8000 → close fires.
5. **`test_idle_gap_close`** — buffer.last_activity_at = now-11min, new msg → close fires (and a fresh buffer is created for the new msg via overlap path).
6. **`test_topic_shift_close`** — mock embedder returns orthogonal vector → cosine drop = 1.0 → close fires.
7. **`test_explicit_close_marker`** — message contains "switching topic" → close fires.
8. **`test_overlap_carry`** — after close, next msg lands in a buffer pre-populated with last-5 turns' content + source_refs.
9. **`test_unique_open_buffer_per_scope`** — two concurrent msgs to same (scope, source_kind) don't both create buffers (relies on slice 1's partial unique index — `PRAGMA foreign_keys=ON` test fixture).
10. **`test_episode_item_has_valid_confidence_in_range`** — closed episode's `confidence ∈ [0,1]`, fresh episode bucket = 'low' (~0.319 per §3.7 formula).
11. **`test_episode_item_source_refs_shape`** — JSON shape matches spec §2.3 (`kind`, `ref`, `captured_at`).
12. **`test_connector_swallows_errors`** — make LLM call raise → connector logs but returns None; outbox event still acks (does NOT poison the queue).
13. **`test_idle_sweeper_closes_stale_buffers`** — fixture inserts an idle buffer directly, runs sweeper, asserts close.

Mock the LLM (`AsyncMock` returning a fixed summary string) and the `Embedder` (return controlled vectors so cosine math is deterministic). DB is real sqlite via `tmp_path` (same pattern as slice 1 tests).

---

## 8. Out of scope

- Pattern finder (episode → observation): slice 4.
- Retrieval / reading episodes back: slice 3.
- Multi-source connectors (gmail/slack/calendar/etc): slice 10.
- UX / Memory tab updates: slice 8.
- Replacing the legacy `MemoryService` methods: slice 3.
- Backfilling episodes from pre-burn chat history: explicit non-goal.

---

## 9. Open clarifications (resolve in Codex inspection or callout before merge)

1. **Scope resolution from session_id**: is there an existing helper? If not, default to `'user'` and add a TODO. The cross-scope contradiction rule (spec §3.4) needs both scopes to function — bookmark for slice 3.
2. **Outbox worker handler model**: RESOLVED. `outbox/worker.py:58` is `self._handlers[event_type] = handler` — one handler per event. Chain inside `_on_run_completed` (chat connector first, then knowledge assimilation, each `try/except`-isolated).
3. **LLM model + prompt template** — mirror `ModelBackedEpisodeBoundaryClassifier`'s model selection. Prompt template lives in `connectors/episode_close.py` as a constant. Keep it short (≤200 token target output).
4. **Confidence formula** — locked from spec §3.7. Four multiplicative components: provenance (base × tanh contradiction), evidence (0.5 + 0.5·(1-exp(-0.4·N·w)), floors at 0.5), decay (0.7·(1+last_used)^-0.5 + 0.3·exp(-age/100)), usage (clamp 0.85 + 0.15·tanh(ratio), 0.5..1.0). Lives in `connectors/_confidence.py`. Fresh inferred episode worked example: 0.75 × 0.5 × 1.0 × 0.85 = 0.31875 → "low". ✓
5. **Embedding dim mismatch** — if `Embedder.config.dim != memory_items_vec` dim (read from `meta.embedding_dim`; live DB currently has **1536**, NOT 768 as previously noted), abort the close path with a logged error rather than corrupting vec table. Should never happen post slice 1 but worth a guard.
6. **Buffer concurrency** — two `RunCompleted` events for the same `(scope, source_kind)` could race. The partial unique index from slice 1 turns the second INSERT into `IntegrityError`. Connector catches that specific error and retries `find_open` once. Test #9 covers it.

---

## 10. Migration / DB impact

Zero. This slice only writes to tables created in slice 1. No new tables, no migration v32. The live DB has already passed v31 (confirmed 2026-05-27).

---

## 11. Codex prompt (verbatim — this block gets pasted into `codex exec`)

```
You are implementing slice 2 of the ntrp memory redesign as PM/architect-supervised work.
The slice brief is at docs/internal/slices/slice-02-chat-connector.md and is the
authoritative instruction for this task. The spec at
docs/internal/ntrp-memory-redesign-spec.md is the source-of-truth for data-model and
confidence-formula details; if brief and spec conflict, STOP and report the contradiction
instead of guessing.

Slice 1 (schema v31) is already landed. You will be writing the first code that uses the
new memory_items / memory_item_parents / episode_buffers tables. The legacy
memory/facts.py, memory/service.py, memory/search_source.py, and
knowledge/store.py modules are intentionally broken (they reference dropped tables like
knowledge_objects, facts, observations) and will be replaced in slice 3 — DO NOT touch
them. DO NOT touch any file outside the §6 file list in the brief. The try/except
wrappers around the legacy paths exist to keep the server running between slices; do
NOT remove them and do NOT replace the broken queries.

Read both documents before writing code. Then implement everything in §4, §5, §6 of the
brief. Add the 13 tests described in §7. Do NOT do anything listed in §8.

Pattern conformance:
- Repository style (items_store, buffers_store): mirror existing repositories like
  apps/server/ntrp/outbox/store.py — async aiosqlite, _SQL_* module constants, Row factory.
- Outbox handler chaining: extend apps/server/ntrp/server/runtime/outbox.py's
  _on_run_completed. CHAIN inside the existing handler (one handler per event type per
  outbox/worker.py:58 — confirmed). Fire ChatConnector.on_run_completed first, then
  the existing assimilate_run_completed. Each call in its own try/except so failures
  are isolated.
- Embedder usage: see apps/server/ntrp/embedder.py — vectors come back L2-normalized,
  so cosine similarity is dot product. Centroid math must keep that invariant.
- Boundary classifier reuse: apps/server/ntrp/knowledge/episodes.py already has
  EpisodeBoundaryClassifier with explicit-switch markers. Reuse it for the explicit-close
  trigger; do NOT reimplement the marker list.
- Async task lifecycle (idle sweeper): mirror the reembed task pattern in
  apps/server/ntrp/memory/facts.py — asyncio.create_task, CancelledError handling,
  start in OutboxRuntime.start, cancel + await in OutboxRuntime.stop.
- Test style: mirror apps/server/tests/memory/test_slice01_schema.py.
  - Use tmp_path for the DB.
  - PRAGMA foreign_keys=ON on the test connection.
  - Mock the LLM client with AsyncMock returning a fixed summary string.
  - Mock the Embedder so cosine math is deterministic (provide explicit vectors).
  - Use TEST_EMBEDDING_DIM = 8 in tests for fast deterministic vectors. The production
    dim (1536, stored in `meta.embedding_dim`) is irrelevant to test fixtures because
    each test creates its own DB with whatever dim the mock embedder is configured for.
    The connector code MUST read the dim from `meta.embedding_dim` rather than
    hardcoding any value.

Specific defaults to encode as module constants (single source of truth):
- TURN_BUDGET = 50
- TOKEN_BUDGET = 8000
- IDLE_GAP = timedelta(minutes=10)
- TOPIC_SHIFT_THRESHOLD = 0.3
- OVERLAP_TURNS = 5
- IDLE_SWEEP_INTERVAL = timedelta(seconds=60)
Place these in apps/server/ntrp/memory/connectors/_constants.py.

Confidence formula (from spec §3.7) goes in
apps/server/ntrp/memory/connectors/_confidence.py. READ spec §3.7 FIRST — the canonical
formula is `confidence = provenance × evidence × decay × usage` with:
- BASE_BY_PROVENANCE = {"recorded": 0.9, "user_authored": 0.95, "inferred": 0.75, "external": 0.6}
- provenance = base × (1 - 0.15 × tanh(contradiction_count))
- evidence   = 0.5 + 0.5 × (1 - exp(-0.4 × N × w_evidence))     # floor 0.5 at N=0
- decay      = 0.7 × (1 + last_used_days)^(-0.5)  +  0.3 × exp(-age_days / 100)
- usage      = clamp(0.85 + 0.15 × tanh(ratio), lo=0.5, hi=1.0)
               where net_usage = helped - hurt - 0.3 × ignored
               and   ratio     = net_usage / max(1, helped + hurt + ignored)
- Bucket thresholds: low / med / high per spec §3.7.
- Confidence stored as REAL in memory_items.confidence; bucket is computed at READ time,
  never stored.

Worked example for a fresh inferred episode (provenance=inferred, N=0, age=0,
last_used=0, helped=hurt=ignored=0):
- provenance = 0.75
- evidence   = 0.5
- decay      = 0.7 × 1.0 + 0.3 × 1.0 = 1.0
- usage      = 0.85 + 0.15 × tanh(0) = 0.85
- confidence = 0.75 × 0.5 × 1.0 × 0.85 = 0.31875 → bucket "low"
Include a unit test that pins this 0.31875 value within 1e-9 tolerance.

Error semantics:
- ChatConnector.on_run_completed MUST NOT re-raise. Every exception caught + logged at
  warning level. The outbox event is acked regardless.
- IntegrityError on the partial unique index (slice 1's
  uniq_episode_buffers_open_per_scope) means a concurrent insert won. Catch it
  specifically, re-fetch with find_open, retry the update once. Don't loop forever.
- Embedding-dim mismatch (Embedder.dim vs the dim used at slice-1 migration time):
  log error, skip the close path, return. Never write a malformed vec row.

When done, in your final message:
- Print a short summary of files changed (path + one-line description).
- Print the contents of the test file (full body) so the reviewer can read it without diffing.
- Run `pytest apps/server/tests/memory/connectors/test_chat_connector.py -v` and print
  the output.
- List every file you touched outside the §6 file list (should be empty).
- Confirm: no edits to apps/server/ntrp/memory/facts.py or
  apps/server/ntrp/memory/service.py.
- Do NOT run git commit, do NOT modify ~/.ntrp/memory.db.
```

---

## 12. PM review checklist (run after Codex returns, before saying "done")

Mechanical pass on Codex's diff. Each line gets ✓ or callout. If anything fails: do not merge, write a correction prompt for Codex or fix it yourself.

**Files touched (expected set only):**
- [ ] `apps/server/ntrp/memory/items_store.py` — new, ≤120 LOC, repository pattern matches outbox/store.py.
- [ ] `apps/server/ntrp/memory/buffers_store.py` — new, ≤150 LOC.
- [ ] `apps/server/ntrp/memory/connectors/__init__.py` — empty or trivial exports.
- [ ] `apps/server/ntrp/memory/connectors/chat.py` — new, `ChatConnector` class.
- [ ] `apps/server/ntrp/memory/connectors/episode_close.py` — new, `finalize_buffer`.
- [ ] `apps/server/ntrp/memory/connectors/idle_sweeper.py` — new, asyncio task.
- [ ] `apps/server/ntrp/memory/connectors/_constants.py` — new, default constants block.
- [ ] `apps/server/ntrp/memory/connectors/_confidence.py` — new, formula + bucketing.
- [ ] `apps/server/tests/memory/connectors/__init__.py` — new.
- [ ] `apps/server/tests/memory/connectors/test_chat_connector.py` — new, 13 tests.
- [ ] `apps/server/ntrp/server/runtime/outbox.py` — chained handler + sweeper start/stop.
- [ ] `apps/server/ntrp/server/runtime/knowledge.py` — constructs connector + repos.
- [ ] **NO** other files modified. If Codex touched `facts.py` / `service.py` / `models.py` / desktop frontend / spec / scratchpad: REVERT and re-prompt.

**Boundary triggers (verify against §2 and §5):**
- [ ] Constants in `_constants.py` match: TURN_BUDGET=50, TOKEN_BUDGET=8000, IDLE_GAP=10min, TOPIC_SHIFT=0.3, OVERLAP_TURNS=5.
- [ ] `evaluate_triggers` evaluates in the §5 order (turn → token → idle → topic_shift).
- [ ] Triggers evaluated BEFORE applying the new turn to the buffer (so the close emits the buffer's pre-turn state and the new turn lands in the next buffer).
- [ ] Centroid math: dot product on L2-normalized vectors. No re-normalization to length 0 (guard zero-norm case).
- [ ] Explicit close reuses `EpisodeBoundaryClassifier._EXPLICIT_SWITCH_MARKERS` (does not re-list them).

**Confidence formula (verify against spec §3.7):**
- [ ] `_confidence.py` BASE_BY_PROVENANCE: recorded=0.9, user_authored=0.95, inferred=0.75, external=0.6.
- [ ] All four components implemented per spec §3.7: provenance (tanh contradiction term), evidence (0.5 floor at N=0, k=0.4), decay (0.7·(1+lu)^-0.5 + 0.3·exp(-age/100)), usage (clamp ±tanh around 0.85, floor 0.5).
- [ ] Fresh-episode worked example test asserts `0.31875` within 1e-9 tolerance.
- [ ] Bucket thresholds match spec (low / med / high).
- [ ] Stored as `REAL` in `memory_items.confidence`; bucket computed at read time, never stored.

**Source refs (verify against spec §2.3):**
- [ ] Each entry has `kind`, `ref`, `captured_at` (ISO-8601 UTC).
- [ ] Stored as JSON in `memory_items.source_refs` and `episode_buffers.source_refs_so_far`.
- [ ] Chat-msg kind is `chat_msg`; ref is `run_id` (verify, since spec calls this out).

**Outbox integration:**
- [ ] Chat connector handler invoked from `_on_run_completed` BEFORE or alongside `assimilate_run_completed` (latter may still throw — connector must not depend on it).
- [ ] Connector errors logged but not re-raised — outbox event still acks.
- [ ] Idle sweeper task started in `OutboxRuntime.start`, cancelled + awaited in `OutboxRuntime.stop`.

**Tests (verify against §7):**
- [ ] All 13 tests present and named per §7.
- [ ] LLM mocked (no real model calls in CI).
- [ ] Embedder mocked with deterministic vectors.
- [ ] DB on `tmp_path` with `PRAGMA foreign_keys=ON`.
- [ ] `test_unique_open_buffer_per_scope` exercises the IntegrityError → retry path.
- [ ] `test_connector_swallows_errors` verifies no re-raise.

**No silent regressions:**
- [ ] `pytest apps/server/tests/memory/connectors/test_chat_connector.py -v` → all 13 green.
- [ ] `pytest apps/server/tests/memory/test_slice01_schema.py -v` still 8/8 green (no schema regression).
- [ ] `git status` shows only the expected files modified or added.
- [ ] No new dependencies added to pyproject.toml / requirements.

If all boxes checked: proceed to live smoke test (manual: chat one turn, sqlite3 `SELECT * FROM episode_buffers`, expect 1 row).

---

## 13. Done criteria

- [ ] `pytest apps/server/tests/memory/connectors/test_chat_connector.py -v` → all 13 tests green.
- [ ] PM (ntrp) reviewed diff against this brief + spec.
- [ ] No edits to `service.py` / `facts.py` / unrelated modules (file scope locked in §6).
- [ ] After merge: live server fires `RunCompleted` from one real chat turn, an `episode_buffers` row appears in `~/.ntrp/memory.db` (manual smoke test by tim).
- [ ] tim confirms.

---

## 14. Status

- §1 goal: locked.
- §2 boundary triggers: locked.
- §3 hook point: locked at outbox.
- §4 module layout: designed, file paths chosen.
- §5 trigger evaluation: pseudocode locked.
- §6 files: enumerated.
- §7 tests: 13 cases listed.
- §8 out-of-scope: locked.
- §9 clarifications: 6 items, mostly answerable inside Codex's own inspection pass.
- §10: zero DB migration.
- §11 Codex prompt: deliberately empty pending tim approval of §1–§10.
- §12 PM review checklist: pending.
- §13 DoD: locked.

**Next step:** tim reviews §1–§10. If green, PM writes §11 (Codex prompt) and §12 (review checklist), then fires `./docs/internal/slices/slice-02-invoke.sh` (to be created).
