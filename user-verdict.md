# NTRP Code Review — All `TO CLAUDE` Findings

## Executive Summary

Full audit of every `# TO CLAUDE:` comment across the NTRP codebase. **~40 comments analyzed**: ~15 need fixes (P0/P1), ~25 are confirmed correct (remove comment only). Additionally includes a roadmap for expanding the existing `EventBus` into the primary inter-module communication backbone.

---

## P0: Quick Wins (trivial effort)

### Remove Wrong/Outdated Comments

| File:Line | Comment gist | Why it's wrong | Fix |
|-----------|-------------|----------------|-----|
| `ntrp/memory/models.py:13` | "FactType not used" | Used in `facts.py`, `tools/memory.py`, `store/facts.py`, and frontend | Remove comment |
| `ntrp/memory/events.py:5` | Question about `ConfigDict(frozen=True)` | Makes Pydantic model immutable — correct and intentional | Remove comment |
| `ntrp/memory/consolidation.py:164` | "Is JSON format right?" | JSON is sent to LLM prompt — format is correct | Remove comment |
| `ntrp/memory/consolidation.py:192` | Same JSON format question | Same reason — correct | Remove comment |
| `ntrp/tools/core/base.py:10-31` | "`_inline_refs` needed?" | OpenAI API requires inlined `$ref` schemas — function is necessary | Remove comment, add one-line docstring explaining why |
| `ntrp/context/models.py:15` | "What is SessionData for?" | Clean DTO returned by `SessionStore.load_session()` | Remove comment |

### Remove Dead Code

| File:Line | What | Why it's dead | Fix |
|-----------|------|---------------|-----|
| `ntrp/server/dashboard.py:1` | `from __future__ import annotations` | Python 3.13 — not needed | Remove import |
| `ntrp/server/runtime.py:131-137` | `__aenter__` / `__aexit__` | Runtime is never used as async context manager | Remove both methods |
| `ntrp/core/tool_runner.py:36` | `tool_id` parameter on `_maybe_offload` | Parameter is accepted but never read | Remove parameter and update call sites |

### Naming Fixes

| File:Line | Current | Proposed | Reason |
|-----------|---------|----------|--------|
| `ntrp/memory/consolidation.py:171` | `f` | `fact` | Single-letter name is vague in a loop body with logic |
| `ntrp/core/parsing.py:16` | `sanitize_assistant_message` | `normalize_assistant_message` | Function normalizes structure, not sanitizing untrusted input |

---

## P1: Constants & Magic Numbers

### New constants for `ntrp/constants.py`

| Constant | Value | Used in | Explanation |
|----------|-------|---------|-------------|
| `RRF_K` | `60` | `search/retrieval.py:33`, `search/index.py:22` | RRF smoothing constant (Cormack et al. 2009) |
| `RRF_OVERFETCH_FACTOR` | `2` | `search/retrieval.py:49,58`, `memory/store/retrieval.py:22-26` | Over-fetch ratio for RRF merge |
| `COMPRESSION_THRESHOLD_ACTUAL` | `0.80` | `context/compression.py:54` | Trigger compression when actual token count known (higher confidence than heuristic 0.75) |
| `SUMMARY_MIN_TOKENS` | `400` | `context/compression.py:110` | Minimum summary output tokens |
| `SUMMARY_MAX_TOKENS` | `2000` | `context/compression.py:110` | Maximum summary output tokens |
| `SUMMARY_COMPRESSION_RATIO` | `4` | `context/compression.py:110` | 1 summary token per N input tokens |
| `WORDS_PER_TOKEN` | `0.75` | `context/compression.py:112` | Words-per-token conversion factor |
| `CONSOLIDATION_MAX_BACKOFF_MULTIPLIER` | `16` | `memory/facts.py:82` | 2^4 = cap after 4 consecutive failures |
| `USER_ENTITY_NAME` | `"User"` | `memory/facts.py:372` | Primary user entity in memory graph |
| `FRIDAY_WEEKDAY` | `4` | `schedule/models.py:75` | Mon=0..Fri=4, >4 means weekend |
| `INDEXABLE_SOURCES` | `{"notes", "memory"}` | `server/runtime.py:245` | Sources that trigger re-indexing on change |

### Use existing constant

- `ntrp/server/chat.py:41` — Hardcoded `5` should use `RECALL_SEARCH_LIMIT` (already defined in `constants.py:122`).

### Better expressions (no constant needed)

| File:Line | Current | Proposed | Why |
|-----------|---------|----------|-----|
| `ntrp/server/state.py:75` | `/ 3600` | `/ timedelta(hours=1)` | Self-documenting, avoids magic number |
| `ntrp/schedule/models.py:63-64` | `int(time_of_day[:2])` | `time_of_day.split(":")` | Handles all time formats, not just zero-padded |

---

## P1: Type Safety Improvements

### ToolResult error tracking

**File:** `ntrp/tools/core/base.py:34-38`
**Problem:** Error detection relies on `result.content.startswith("Error:")` in `tool_runner.py:77` — fragile string matching.
**Fix:** Add `is_error: bool = False` field to `ToolResult`. Update tool implementations that return errors to set `is_error=True`. Update `tool_runner.py` to check `result.is_error` instead of string prefix.

### ConsolidationAction type field

**File:** `ntrp/memory/consolidation.py:36-37`
**Problem:** `type: str` accepts any string but only `"update"`, `"create"`, `"skip"` are valid (matches `ConsolidationSchema`).
**Fix:** Change to `type: Literal["update", "create", "skip"]`. String comparisons at lines 63, 119, 122, 142 get free validation.

### UsageStats container

**File:** `ntrp/server/state.py:30-34`
**Problem:** `get_usage()` returns a raw `dict` — callers must know the key names.
**Fix:** Create `UsageStats` dataclass with `prompt: int`, `completion: int`, `total: int` fields.

### SyncResult container

**File:** `ntrp/search/index.py:74`
**Problem:** Returns `tuple[int, int]` — positional meaning is ambiguous.
**Fix:** `class SyncResult(NamedTuple): updated: int; deleted: int`

### ProgressCallback type alias

**File:** `ntrp/search/index.py:72`
**Fix:** Define `type ProgressCallback = Callable[[int, int], None]` at module level instead of inline.

### Stream return type

**File:** `ntrp/core/agent.py:125`
**Problem:** `AsyncGenerator[SSEEvent | str]` — mixed types force callers to isinstance-check every yielded value.
**Fix:** Create `TextResult(SSEEvent)` wrapper for plain text results. Unify return type to `AsyncGenerator[SSEEvent]`.

### `_result` hack in stream

**File:** `ntrp/server/app.py:214`
**Problem:** `{"_result": result}` dict used as side-channel through the generator — untyped, invisible contract.
**Fix:** Create `AgentResult` dataclass, yield that instead of a raw dict.

---

## P1: Code Style & Patterns

### Guard conditions (flip if-statements)

| File:Line | Current pattern | Proposed |
|-----------|----------------|----------|
| `ntrp/core/agent.py:83` | Deep nesting under `if response.usage` | `if not response.usage: return` early |
| `ntrp/schedule/scheduler.py:38` | Nested under `if self._task is None` | `if self._task is not None: return` early |
| `ntrp/memory/facts.py:313` | Complex nested block | Extract `_reinforce_observations()` helper (can't simple-guard due to control flow) |

### Boilerplate reduction

| File:Line | Issue | Fix |
|-----------|-------|-----|
| `ntrp/memory/facts.py:211` | Repeated `_add_entity_ref` calls with same partial args | Use `functools.partial` |
| `ntrp/schedule/scheduler.py:97` | `deps = self.deps` alias used once | Remove alias, use `self.deps` directly |
| `ntrp/memory/facts.py:354` | Vague ternary expression | Expand into explicit `if`/`else` for readability |
| `ntrp/core/agent.py:77-78` | `if self.tools` conditional | Remove — tools always exist |
| `ntrp/core/agent.py:191` | `isinstance` chain | Use `match`/`case` pattern matching |
| `ntrp/core/tool_runner.py:32` | `parent_id or ""` | Change to `parent_id or "root"` — semantically clearer |

### SQL queries to module-level constants

| File | Lines | Proposed constant names |
|------|-------|------------------------|
| `ntrp/context/store.py` | 40-46, 81-84, 91-96 | `SQL_SAVE_SESSION`, `SQL_GET_LATEST`, `SQL_LIST_SESSIONS` |
| `ntrp/schedule/store.py` | 34-38, 68-73, 94-99 | `SQL_SAVE_TASK`, `SQL_LIST_DUE`, `SQL_UPDATE_LAST_RUN` |

### Extract to proper locations

| File:Line | What to extract | Target location |
|-----------|----------------|-----------------|
| `ntrp/sources/google/gmail.py:235` | HTML email template string | Module-level constant `EMAIL_HTML_TEMPLATE` |
| `ntrp/schedule/scheduler.py:114` | Scheduler prompt suffix | `ntrp/core/prompts.py` |
| `ntrp/server/app.py:164` | `{"remember", "forget", "reflect", "merge"}` set | Named constant in tools module |
| `ntrp/server/state.py:87` | `get_run_registry()` function | Move to `runtime.py` — eliminates circular import risk |

---

## P2: Architecture

### Runtime as Composition Root

`ntrp/server/runtime.py:31` — Runtime is a large object but that's architecturally correct: it IS the composition root. It wires subsystems together, manages lifecycles, and holds the singleton. No structural refactor needed beyond the specific cleanups listed in P0/P1 above.

### Items Confirmed Correct (remove comment only)

These items were reviewed and found to be correct. The `# TO CLAUDE` comment should simply be deleted.

| File:Line | Comment topic | Why it's correct |
|-----------|--------------|-----------------|
| `memory/facts.py:64` | async `create()` classmethod | `__init__` can't be async |
| `memory/facts.py:110` | Rebuilding repo instances each call | Repos are cheap stateless wrappers around a connection |
| `memory/facts.py:45` | Repos created each time | Same — cheap stateless wrappers |
| `server/runtime.py:69` | `reinit_memory` method | Needed for runtime config toggle |
| `server/runtime.py:150` | Memory not a regular source | `FactMemory` doesn't implement `Source` interface |
| `server/runtime.py:202` | Consolidation triggered in Runtime | Lifecycle orchestration IS Runtime's job |
| `server/runtime.py:218` | Event wiring in Runtime | Composition root wires subsystems — correct location |
| `server/runtime.py:273` | Global singleton pattern | Pragmatic for FastAPI's dependency injection |
| `server/sources.py:32` | `reinit` function | Needed for dynamic source management |
| `server/app.py:140` | `/init` magic command | Simple, clean feature toggle — no refactor needed |
| `sources/registry.py:30` | Lambdas in `SOURCES` dict | Short, descriptive, clean |
| `sources/exa.py:43` | Defensive `getattr` | SDK doesn't guarantee field presence |
| `sources/memory.py:30` | Title from entity name | Sensible heuristic for display |
| `memory/formatting.py:19` | Section rendering logic | Works correctly, budget-aware truncation |
| `memory/store/base.py:124` | TZ conversion | Correct upgrade path for naive datetimes |
| `schedule/scheduler.py` (imports) | Imports inside methods | Genuine circular import avoidance — acceptable |
| `context/compression.py:13` | `_get_attr` helper | Necessary for dict/object message duality |
| `context/compression.py:20` | Approximate token count | Needed for pre-API-call estimation |
| `context/models.py:15` | `SessionData` dataclass | Clean DTO |
| `core/state.py:5` | `AgentState` enum | Sufficient states for current lifecycle |
| `core/async_queue.py:12` | `AsyncQueue` implementation | Solid, no issues |
| `core/agent.py:132` | `tool_runner` per stream call | Correctly scoped per invocation |
| `core/tool_runner.py:33` | `is_cancelled` flag | Used for cancellation in sequential execution |
| `server/stream.py:25` | Nested iteration cycles | Inherent complexity of event multiplexing |
| `server/stream.py:32` | `messages[:-1]` slice | Correct: separates history from current user message |
| `server/chat.py:28` | `prepare_messages` param count | 4 params is acceptable |
| `schedule/scheduler.py:47` | `stop()` guard structure | Can't early-return without breaking second cleanup block |

---

## P2: Event-Driven Architecture Expansion

### Current State

`ntrp/bus.py` has a working `EventBus` with type-based dispatch:

```python
class EventBus:
    def subscribe[T](self, event_type: type[T], handler: Handler[T]) -> None: ...
    async def publish[T](self, event: T) -> None: ...
```

Currently used only for memory events (`FactCreated`, `FactUpdated`, `FactDeleted`, `MemoryCleared`) and source events (`SourceChanged`).

### Vision

Expand the bus to be the primary inter-module communication backbone. Modules publish what happened; interested modules subscribe. No module needs to know who's listening. If there are no subscribers, publish is a no-op — no errors.

### Architecture Decision: Single bus, type-based dispatch

- **Event type IS the topic.** `FactCreated`, `ToolExecuted`, `RunStarted` — subscribers filter by type.
- **Named channels** add wiring complexity and need bridges for cross-domain events. Not worth it.
- **Topic tags** are redundant over type dispatch at this scale.
- **Per-session correlation** via `run_id` / `session_id` fields on events, not via separate channels.

### Communication Pattern Split

Not everything should go through the bus. The dividing line:

| Pattern | Use for | Mechanism |
|---------|---------|-----------|
| **Events** (fire-and-forget) | Tool completed, run started/finished, agent state changed, session saved, indexing progress, consolidation done | `EventBus.publish()` |
| **Direct calls** (request-reply) | Execute tool -> get `ToolResult`, embed text -> get embedding, compress messages -> get result | Method calls (unchanged) |

Rule of thumb: if the caller needs the return value, it's a direct call. If it's just notifying, it's an event.

### New Events to Define

```python
# Agent lifecycle
@dataclass
class RunStarted:
    run_id: str
    session_id: str

@dataclass
class RunCompleted:
    run_id: str
    prompt_tokens: int
    completion_tokens: int
    result: str

# Tool execution
@dataclass
class ToolExecuted:
    name: str
    duration_ms: int
    depth: int
    is_error: bool
    run_id: str

# Consolidation
@dataclass
class ConsolidationCompleted:
    facts_processed: int
    observations_created: int

# Indexing
@dataclass
class IndexingStarted:
    sources: list[str]

@dataclass
class IndexingCompleted:
    updated: int
    deleted: int
```

### Migration Path

1. **Define new event types** in domain-specific modules or a shared `ntrp/events.py`.
2. **Publish from current call sites** — `app.py` publishes `RunStarted`/`RunCompleted`, `tool_runner.py` publishes `ToolExecuted`.
3. **DashboardCollector subscribes** to `ToolExecuted`, `RunStarted`, `RunCompleted` instead of being called directly via `if self.dashboard:` checks.
4. **Remove `dashboard` from `ToolContext`** — it no longer needs to be threaded through.
5. **Expand incrementally** to other subsystems (indexing, consolidation) as needed.

This eliminates the `if self.dashboard:` pattern throughout the codebase and makes adding new observers (logging, metrics, debugging) zero-cost: just subscribe.
