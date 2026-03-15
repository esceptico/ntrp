# Backend Refactoring — Complete

## Investigated (not issues)

- ~~Event handler accumulation~~ — `wire_events()` only called once in `connect()`, never on reload.
- ~~inject_queue race condition~~ — single asyncio event loop, no awaits between extend+clear.
- ~~MemoryService consistency~~ — intentional separation: FactMemory for core ops, MemoryService for web API.
- ~~ToolContext as god-object~~ — already well-composed (RunContext, IOBridge, BackgroundTaskRegistry). `get_source[T]()` generic avoids coupling.
- ~~Full Runtime decomposition~~ — Runtime is the composition root. Cross-cutting concerns (reload_config, close, build_operator_deps) inherently need access to all subsystems. The meaningful improvement was decoupling the services that held it — done below.

## Round 1 — Decoupling & cleanup

- **BusRegistry leak fix** (`app.py`) — remove bus from registry when last subscriber disconnects AND no active run is emitting. Prevents both leaks and race where reconnecting client gets a new empty bus.
- **Centralized DI** (`server/deps.py`) — new module with all `require_*` functions; removed 7 scattered duplicates from routers. Eliminated duplicate `_require_config_service` (was in both mcp.py and session.py).
- **ConfigService decoupled** (`services/config.py`) — takes `on_config_change` callback instead of full `runtime`.
- **ToolExecutor decoupled** (`tools/executor.py`) — takes `mcp_tools` list + `get_services` callable instead of `runtime`. Exposes `tool_services` property for factory.py.
- **NotifierService decoupled** (`notifiers/`) — `NotifierContext(get_source, get_config_value)` replaces `runtime` in service + all 3 notifier implementations (email, telegram, bash).
- **`_sync_mcp` → `sync_mcp`** (`runtime.py`) — made public since it's called from MCP router. No more private method access from outside.
- **`AgentConfig.from_config()`** (`core/factory.py`) — eliminated 4× duplicated 7-line construction blocks in chat.py, runtime.py, cli.py.
- **`dataclasses.replace()` for model override** (`operator/runner.py`) — replaced manual 7-field copy.
- **`sync_google_sources()`** (`runtime.py`) — consolidated duplicated gmail+calendar reinit + restart_monitor pattern in gmail router.

## Round 2 — Deduplication & simplification

- **Memory init dedup** (`runtime.py`) — extracted `_memory_ready` property, `_create_memory()`, `_close_memory()`. Eliminated 3 repetitions of the FactMemory.create + MemoryService setup and 2 repetitions of the close+nullify pattern.
- **TriggerPatch simplification** (`automation/service.py`) — `has_changes` and `overrides` now use `dataclasses.asdict()` instead of manually enumerating all 8 fields twice.
- **Models JSON I/O dedup** (`llm/models.py`) — extracted `_read_models_json() -> dict | None`. Replaced 3 separate try/except + exists-check blocks in load, add, remove.
- **Router init loop dedup** (`llm/router.py`) — merged two identical loops over `get_models()` and `get_embedding_models()` into one using `itertools.chain`.
- **SessionStore `_update` helper** (`context/store.py`) — extracted `_update(sql, params) -> bool` for the repeated execute→commit→return rowcount pattern. Used in 4 methods.

## Round 3 — Memory pipeline dedup

- **Shared `find_top_pair`** (`memory/retrieval.py`) — extracted identical `_find_top_pair` from both `observation_merge.py` and `fact_merge.py`. Both merge modules now import the shared version. Generic over any items with `.id` and `.embedding`.
- **`_replace_source_fact_id` helper** (`memory/fact_merge.py`) — extracted duplicated obs/dream source_fact_ids replacement logic into a single function. Uses `Literal["observations", "dreams"]` type for table name safety.

## Round 4 — Clarity & explicitness

- **`extraction_model` → `model`** (`memory/facts.py`) — renamed property, update method, `__init__` param, and `create()` param. This model is used for ALL memory LLM operations (consolidation, merge, dreams, temporal, extraction), not just extraction. `FactMemory.model` reads naturally.
- **Compression sentinel removed** (`context/compression.py`) — `find_compressible_range()` returns `None` instead of `(0, 0)` sentinel. All 3 callers updated to explicit `if compressible is None` check.
- **`_consolidation_interval` initialized** (`memory/facts.py`) — added to `__init__` as `float | None = None`. Removed `getattr()` hack in runtime.py. Attribute is now visible and typed.
- **`ReembedProgress` TypedDict** (`memory/facts.py`) — `_reembed_progress` typed as `ReembedProgress | None` instead of `dict | None`. Shape is now explicit: `{total: int, done: int}`.
- **`RunState.approval_queue` typed** (`server/state.py`) — `asyncio.Queue[dict]` instead of bare `asyncio.Queue`.

## Round 5 — SQL constants, walrus operators, polish

### SQL queries moved to module-level constants
- **`notifiers/store.py`** — 5 inline queries → `SQL_LIST`, `SQL_GET`, `SQL_SAVE`, `SQL_RENAME`, `SQL_DELETE`
- **`notifiers/log_store.py`** — 3 inline queries → `SQL_SAVE`, `SQL_RECENT`, `SQL_RECENT_BY_TASK` (shared `_COLUMNS` for DRY)
- **`context/store.py`** — 6 inline queries → `SQL_LOAD_SESSION`, `SQL_DELETE_STALE_MESSAGES`, `SQL_UPDATE_NAME`, `SQL_ARCHIVE`, `SQL_RESTORE`, `SQL_DELETE_ARCHIVED`
- **`memory/store/facts.py`** — 5 inline queries → `_SQL_UPDATE_TEXT`, `_SQL_COUNT_ENTITY_REFS_FOR_FACT`, `_SQL_RESET_CONSOLIDATED`, `_SQL_LIST_ALL_WITH_EMBEDDINGS`, `_SQL_UPDATE_EMBEDDING`
- **`memory/store/observations.py`** — 6 inline queries → `_SQL_UPDATE_SUMMARY`, `_SQL_DELETE_OBSERVATION`, `_SQL_CLEAR_OBS_ENTITY_REFS`, `_SQL_CLEAR_OBS_VEC`, `_SQL_CLEAR_OBSERVATIONS`, `_SQL_UPDATE_OBS_EMBEDDING`

### Walrus operator (:=) for assign-then-check patterns
- **`llm/models.py`** — `_read_models_json()` None check
- **`automation/models.py`** — `BUILD_DISPATCH.get()` and `PARSE_DISPATCH.get()` dispatch lookups
- **`automation/service.py`** — `store.get()` not-found guard
- **`automation/scheduler.py`** — `store.get()` not-found guard
- **`notifiers/service.py`** — `NOTIFIER_FIELDS.get()` validation
- **`services/config.py`** — `settings.get()` in model cleanup loop
- **`services/session.py`** — `load()` + empty check
- **`context/store.py`** — `get_latest_id()` check
- **`memory/service.py`** — all 9 get-then-check patterns in FactService, ObservationService, DreamService

### Runtime decomposition
- **`Stores` class** (`runtime.py`) — extracted DB connection + 5 stores (`SessionService`, `AutomationStore`, `NotifierStore`, `NotificationLogStore`, `MonitorStateStore`) into self-contained `Stores` class with own `connect()` / `close()` lifecycle. Runtime.__init__ reduced from 20 to 15 attributes. `session_service` exposed as a property delegating to `stores.sessions`.

### Dataclasses for untyped dicts
- Not pursued — message dicts are intentionally in OpenAI format for JSON serialization. API response dicts are intentionally loose for FastAPI. No candidates where typing would catch real bugs without adding complexity.

## Not pursued (assessed, not worth the trade-off)

- DI helpers factory — 5 functions with `Depends(get_runtime)` signatures. A factory would lose type annotations and IDE support.
- Router client caching merge — completion and embedding clients have distinct provider sets and cache types.
- LLM structured call pattern — 6 callers share "call LLM → parse JSON → handle errors" but differ enough that a generic helper would need too many parameters.
- Merge pass orchestration — observation_merge_pass and fact_merge_pass share loop structure but differ in skip action names, keeper selection, merge execution.
- Tool list/search dispatch — similar pattern in 4 tools but `_list` and `_search` have very different signatures per tool.
- Session metadata TypedDict — single key `last_input_tokens`, typing a one-key dict adds more code than it clarifies.
- Message/tool call TypedDicts — dicts follow OpenAI message format, typing them constrains without benefit since format is dictated by the LLM API.
