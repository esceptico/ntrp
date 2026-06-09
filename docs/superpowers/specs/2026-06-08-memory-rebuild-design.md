# Memory Rebuild — Design Spec (Curated Docs)

> Status: APPROVED 2026-06-08. Branch: `feat/memory-rebuild`.
> Paradigm: curated markdown docs (Letta/Hermes/Claude-Code lineage), replacing the claims+lens pipeline.
> Decisions: hybrid capture (remember/forget tool + end-of-session curator w/ novelty gate); FTS5+semantic over the existing transcript archive; distill old claims into docs then drop tables; curator watermark lives in a `meta` table in memory.db; server-only this pass (desktop memory-UI repoint is a follow-up).

# NTRP Curated-Docs Memory Rebuild — CANONICAL IMPLEMENTATION BLUEPRINT

All paths absolute. Server root: `/Users/escept1co/src/ntrp/apps/server`. Module root: `ntrp/` under that. Every signature below is the CONTRACT — code to it exactly.

Scope key fact (verified): a project's scope `key` is `project_context.project_id` (a string id, NOT a slug). For docs on disk we slugify the id only for the FILENAME; the in-memory `Scope.key` stays the raw `project_id`.

---

## A. CANONICAL INTERFACES (exact code)

### A.1 `ntrp/memory/models.py` — slim rewrite (full code)

Keep `now_iso`, `ScopeKind`, `Scope`, `SourceRef`. Delete `Status`, `Provenance`, `Feedback`, `EdgeRole`, `MemoryItem`, `MemoryEdge`, and all `Lens*`/`Membership*` types. Add `MemoryDoc`.


---

## Implementer corrections (verified vs live code)

python
"""Curated-docs memory schema. A MemoryDoc is a scoped markdown file on disk —
the source of truth, git-friendly. No claim rows, no lenses, no pipeline."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ScopeKind(StrEnum):
    USER = "user"
    PROJECT = "project"
    SESSION = "session"


@dataclass
class Scope:
    """Mandatory scoping. `key` is None only for USER; required for PROJECT/SESSION."""

    kind: ScopeKind
    key: str | None = None

    def __post_init__(self):
        if isinstance(self.kind, str):
            self.kind = ScopeKind(self.kind)
        if self.kind is ScopeKind.USER:
            self.key = None
        elif not self.key:
            raise ValueError(f"scope {self.kind} requires a key")


@dataclass(frozen=True)
class SourceRef:
    """A typed pointer into the raw layer (chat_turn, tool_run, ...). Retained
    for the remember tool's append provenance footnotes."""

    kind: str
    ref: str
    captured_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "ref": self.ref, "captured_at": self.captured_at}

    @staticmethod
    def from_dict(d: dict) -> "SourceRef":
        return SourceRef(kind=d["kind"], ref=d["ref"], captured_at=d["captured_at"])


@dataclass
class MemoryDoc:
    """A curated markdown file. `path` is the absolute on-disk location;
    `content` is the markdown body (budget-bounded ~8k chars)."""

    scope: Scope
    path: Path
    content: str
    updated_at: str = field(default_factory=now_iso)

    @property
    def exists(self) -> bool:
        return bool(self.content.strip())
```

> ASSUMPTION: `SESSION` scope is retained in the enum but unused by docs (docs are only USER/PROJECT). It is kept because `ToolContext`/automation still reference `ScopeKind` generically; removing it is out of scope.

### A.2 `ntrp/memory/docs.py` — `MemoryDocStore` (NEW; full public signatures)

```python
from pathlib import Path
from ntrp.memory.models import MemoryDoc, Scope, ScopeKind

_DOC_CHAR_BUDGET = 8000  # ~2k tokens; the render budget per doc

class MemoryDocStore:
    """Disk-backed store for curated markdown memory docs. Zero LLM, zero DB.
    Read path for the MEMORY CONTEXT block + write path for remember/forget +
    curator. Files live under `docs_dir`:
        <docs_dir>/user.md
        <docs_dir>/projects/<slug>.md
    """

    def __init__(self, docs_dir: Path, char_budget: int = _DOC_CHAR_BUDGET) -> None:
        """`docs_dir` = config.memory_docs_dir. Creates the dir tree lazily on write."""

    def _path_for(self, scope: Scope) -> Path:
        """Resolve the absolute file path for a scope. USER -> user.md;
        PROJECT -> projects/<slug(scope.key)>.md. Slug derives from the
        project_id (lowercased, non-alnum -> '-'); collisions are not expected
        because project_id is already unique."""

    async def load(self, scope: Scope) -> MemoryDoc:
        """Read one scope's doc from disk. Missing file -> MemoryDoc with empty
        content (never raises). Used by the curator (needs current doc state)."""

    async def render(self, scopes: list[Scope]) -> str | None:
        """Concatenate the docs for `scopes` (in order) into the MEMORY CONTEXT
        body. Each present doc is prefixed with a small '## <scope label>'
        header. Returns None if all scopes are empty. This is the per-turn read
        path — pure file I/O, no truncation beyond what was already budgeted on
        write."""

    async def append(self, scope: Scope, text: str, *, source: SourceRef | None = None) -> bool:
        """Append a fact paragraph to the scope's doc (creating it if absent).
        De-dupes on an exact normalized-line match (cheap, no LLM). If appending
        would exceed char_budget, drops the oldest bullet(s) FIFO to stay under
        budget. Returns True if the doc changed. This is the remember() write."""

    async def forget(self, scope: Scope, target: str) -> bool:
        """Remove the matching bullet/paragraph from the scope's doc. Match is a
        case-insensitive substring against existing lines; removes the first
        match. Returns True if something was removed. This is the forget() write."""

    async def write(self, scope: Scope, content: str) -> None:
        """Replace the entire doc body for a scope (curator's full-doc rewrite).
        Enforces char_budget by refusing > budget*1.1 and logging; writes
        atomically (tmp + rename). Updates updated_at."""

    async def list_scopes(self) -> list[Scope]:
        """Enumerate scopes that have a doc on disk: always USER if user.md
        exists, plus one PROJECT scope per projects/*.md. For the REST surface.
        NOTE: the project Scope.key returned is the slug read from the filename;
        callers that need the original project_id must map via the projects table
        (REST read-only display only — no write keys off this)."""
```

Budget enforcement rule (single source): `append` and `write` both clamp to `char_budget`. `append` trims oldest bullets FIFO; `write` (curator) is responsible for its own compression and the store only guards the hard ceiling.

### A.3 `ntrp/memory/curator.py` — `Curator` (NEW; full public signatures)

```python
from ntrp.memory.docs import MemoryDocStore
from ntrp.memory.models import Scope

class Curator:
    """End-of-session memory writer. ONE LLM call per session per scope: reads
    new transcript turns since a per-session watermark + the current scoped doc,
    returns an updated doc (or a NO-CHANGE sentinel). Replaces the whole
    capture->admit->extract->reconcile->consolidate pipeline."""

    def __init__(
        self,
        doc_store: MemoryDocStore,
        llm,                      # completion client for config.memory_model
        sessions,                 # SessionService — to read transcript turns (search_messages/load)
        *,
        model: str,               # config.memory_model id (for the call)
        reasoning_effort: str | None = None,
    ) -> None: ...

    def schedule_curation(self, session_id: str, scope: Scope) -> None:
        """Fire-and-forget: spawn a tracked asyncio task running curate_session.
        Called from chat.py end-of-run. Swallows + logs errors; never blocks the
        response path. De-dupes: if a curation for this session is already
        in-flight, no-op."""

    async def curate_session(self, session_id: str, scope: Scope) -> bool:
        """1. Read watermark (max seq already curated for this session).
        2. Load new transcript turns (seq > watermark) via sessions store.
        3. If no new substantive turns -> advance watermark, return False.
        4. Load current MemoryDoc(scope).
        5. ONE LLM call (see §C). Novelty gate: model returns NO_CHANGE sentinel
           if nothing durable+new -> advance watermark, return False.
        6. Else doc_store.write(scope, updated_doc); advance watermark; return True.
        Watermark advances ONLY after a successful write (or confirmed no-change)."""

    async def stop(self) -> None:
        """Await/cancel in-flight curation tasks. Called from knowledge.stop()."""
```

Watermark storage (verified mechanism): reuse the `meta` table in the existing memory.db (`MemoryStore.conn`) exactly as `consolidate.py` did. Key form: `curate_watermark:{session_id}`. Value: max curated `seq` (TEXT). Read/advance helpers live on `Curator`, mirroring `consolidate.py:471–486`. (memory.db survives the rebuild for this watermark + distillation; only the claims/lens *tables* get dropped post-distillation.)

### A.4 Semantic transcript indexer — hook + calls

Hook point (verified): `ntrp/context/store.py` → `_mirror_session_messages` (line 1217), at the INSERT branch (~line 1255) where a NEW row is written. Index only newly-inserted rows (skip the UPDATE branch to avoid re-embedding churn).

The mechanism is the existing `SearchIndex` wrapper (`ntrp/search/index.py`), which embeds internally — do NOT call `SearchStore.upsert` directly and do NOT serialize embeddings yourself. Contract:

```python
# SearchIndex.upsert (already exists, ntrp/search/index.py:47)
async def upsert(self, source: str, source_id: str, title: str,
                 content: str, metadata: dict | None = None) -> bool
```

Call to add (inside the INSERT branch, after the SQL insert, fire-and-forget so a slow embed never blocks message persistence):

```python
# search_index is the SearchIndex passed into ContextStore (NEW constructor arg, optional)
if self._search_index is not None and search_text.strip():
    source_id = f"{session_id}:{next_seq}"
    asyncio.create_task(self._search_index.upsert(
        source="transcript",
        source_id=source_id,
        title=f"{role} @ {session_id}",
        content=search_text,
        metadata={"session_id": session_id, "seq": next_seq, "role": role},
    ))
```

> ASSUMPTION (state explicitly): `ContextStore` does not currently hold a `SearchIndex`. The clean wiring is to pass the runtime's `search_index` into the store. Because `search_index` is built lazily in `KnowledgeRuntime` AFTER stores connect, expose a setter `ContextStore.attach_search_index(idx)` and call it from `KnowledgeRuntime.connect` once the indexer is up. The vector index lives in **search.db**, fully separate from sessions.db — no schema collision.

### A.5 Hybrid transcript search — `search_messages` becomes FTS+vector

`ntrp/context/store.py:2626` `search_messages` keeps its signature and return shape. Internally:

1. Run the existing FTS query → ordered `[(rowid/seq-key, bm25)]`.
2. If a `SearchIndex` is attached: `await search_index.store.vector_search(embed(query), sources=["transcript"], limit=...)` → `[(item_id, score)]`, then map `item_id` → `{session_id, seq}` via `SearchStore` item metadata.
3. Merge the two ranked lists with the existing `rrf_merge` (`ntrp/search/retrieval.py:13`), then re-hydrate the top-N hits from `session_messages` for the snippet/role/created_at fields.
4. If no `SearchIndex` attached → behave exactly as today (FTS-only). Keep it thin: vector is additive, never required.

### A.6 `remember` / `forget` tools — `ntrp/tools/memory.py` (full rewrite contract)

```python
MEMORY_DOCS_SERVICE = "memory_docs"   # replaces MEMORY_WRITE_SERVICE / MEMORY_READ_SERVICE

class RememberInput(BaseModel):
    fact: str = Field(min_length=1, max_length=20_000, description="A single durable, self-contained fact...")

class ForgetInput(BaseModel):
    fact: str = Field(min_length=1, max_length=20_000, description="The fact/text to remove from memory (substring match).")

def _resolve_scope(execution: ToolExecution) -> Scope:
    """PROJECT(key=project_id) if execution.ctx.project.project_id else USER.
    Structural, never LLM-inferred. (ctx.project is ProjectContext | None.)"""

async def remember(execution: ToolExecution, args: RememberInput) -> ToolResult:
    """doc_store = execution.ctx.services.get(MEMORY_DOCS_SERVICE); guard None.
    changed = await doc_store.append(scope, args.fact,
        source=SourceRef(kind='chat_turn', ref=f'{ctx.session_id}:{tool_id}'))
    -> ToolResult(preview='Remembered'|'Already known')."""

async def forget(execution: ToolExecution, args: ForgetInput) -> ToolResult:
    """removed = await doc_store.forget(scope, args.fact)
    -> ToolResult(preview='Forgotten'|'Not found')."""

remember_tool = tool(
    display_name="Remember",
    description="Durably remember a single fact ... ",   # keep existing wording
    input_model=RememberInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL,
                      permissions=frozenset({MEMORY_DOCS_SERVICE})),
    execute=remember,
)
forget_tool = tool(
    display_name="Forget",
    description="Remove a previously-remembered fact from long-term memory.",
    input_model=ForgetInput,
    policy=ToolPolicy(action=ToolAction.WRITE, scope=ToolScope.INTERNAL,
                      permissions=frozenset({MEMORY_DOCS_SERVICE})),
    execute=forget,
)
```

`recall_tool` is DELETED (deep recall = `search_transcripts` tool, which already exists and now becomes hybrid via A.5). Remove all imports of `Retriever`, `Retrieval`, `WriteSeam`, `WriteRequest`, `Provenance`.

---

## B. FILE-BY-FILE CHANGE PLAN

| Path | Action | Precise change |
|---|---|---|
| `ntrp/memory/docs.py` | NEW | `MemoryDocStore` per §A.2. |
| `ntrp/memory/curator.py` | NEW | `Curator` per §A.3 (incl. meta-table watermark helpers). |
| `ntrp/memory/models.py` | REWRITE | Replace with §A.1 (keep `now_iso`/`ScopeKind`/`Scope`/`SourceRef`; add `MemoryDoc`; delete claim/lens/edge/membership types). |
| `ntrp/memory/__init__.py` | REWRITE | Export only `MemoryDoc`, `Scope`, `ScopeKind`, `SourceRef`, `MemoryDocStore`, `Curator`. Drop all pipeline/lens/store re-exports. |
| `ntrp/memory/store.py` | DELETE | No claim rows remain. (Watermark uses a tiny meta table — see note below; do NOT keep the 723-LOC store for it.) |
| `ntrp/memory/migrations.py` | DELETE | Migrations were for memory_items/lens schema; gone with store. |
| `ntrp/memory/SCHEMA.md` | DELETE | Stale. |
| `ntrp/memory/pipeline/**` (all ~30 files) | DELETE | Entire dir: `__init__`, `admit`, `capture`, `consolidate`, `extract`, `membership`, `project`, `reconcile`, `retrieve`, `runtime`, `write`, `writeback`, `lens_generation`, `types`, all `prompts*`. |
| `ntrp/memory/lens/**` (all files) | DELETE | `__init__`, `file_store`, `registry`, `tool`, `expand`. Lens concept removed entirely (design item 6). |
| `ntrp/tools/memory.py` | REWRITE | Per §A.6. `MEMORY_DOCS_SERVICE`, `remember`+`forget`, delete `recall`. |
| `ntrp/integrations/core.py` | EDIT | Line 9 drop `from ntrp.memory.lens import lens_tool`. Line 41 `from ntrp.tools.memory import forget_tool, remember_tool`. MEMORY integration tools `{"remember": remember_tool, "forget": forget_tool}` (drop `recall`, `lens`). |
| `ntrp/server/runtime/knowledge.py` | REWRITE `_init_memory` + EDIT | See B.1 below. |
| `ntrp/server/runtime/core.py` | EDIT | Remove props `memory`, `memory_service`, `pattern_finder`, `lens_pass`, `lens_author`; keep `memory_retrieval` (now the `MemoryDocStore`). In `build_chat_deps`: drop `memory=`, `memory_service=`; keep `memory_retrieval=self.memory_retrieval`; add `memory_curator=self.knowledge.memory_curator`. In `build_operator_deps`: drop `memory=`, `memory_service=`; keep `memory_retrieval=`. |
| `ntrp/services/chat.py` | EDIT | See B.2 below. |
| `ntrp/operator/runner.py` | EDIT | See B.3 below. |
| `ntrp/context/store.py` | EDIT | Add `attach_search_index`/`_search_index`; index-on-insert in `_mirror_session_messages` (§A.4); make `search_messages` hybrid (§A.5). |
| `ntrp/server/routers/memory.py` | REWRITE | Replace 629-line claims/lens API with minimal docs API (§B.4). |
| `ntrp/automation/suggestions.py` | EDIT | `_memory_subjects`, `_recent_claims`, `_active_lenses` all call deleted store/lens APIs — replace the three with one `_memory_docs()` that calls `doc_store.render([USER])` (or returns `""`). Update `__init__` to take the doc_store instead of `memory`. |
| `ntrp/server/runtime/automation.py` | EDIT | Delete `_build_pattern_finder_daily_handler` + its scheduled registration (the episode→observation path is dead; recon flagged "keep" but it imports `get_pattern_finder` which no longer exists once pipeline is gone — it MUST be removed). |

> Watermark-store note: rather than keep the whole `MemoryStore`, the curator creates/opens a tiny sqlite at `config.memory_db_path` with a single `meta(key,value)` table (the curator owns `init`). This isolates the only surviving DB need from the deleted store. ASSUMPTION: acceptable to reuse `memory.db` for this one table; if the team prefers, point the watermark at sessions.db's existing `meta`-style storage — confirm before coding.

### B.1 `knowledge.py` exact rewire

`_init_memory(self, stores)` becomes:
```python
if not self.config.memory:           # unchanged guard
    return
from ntrp.memory.docs import MemoryDocStore
from ntrp.memory.curator import Curator
self._doc_store = MemoryDocStore(self.config.memory_docs_dir)
self.memory_retrieval = self._doc_store          # read path
self.memory_curator = Curator(
    doc_store=self._doc_store,
    llm=get_completion_client(self.config.memory_model),
    sessions=stores.sessions,
    model=self.config.memory_model,
    reasoning_effort=self._memory_reasoning_effort(self.config.memory_model),
) if self.config.memory_model else None
```
- Delete instance fields: `memory`, `memory_search`, `memory_service`, `memory_reader`, `memory_search_source`, `memory_items`, `pattern_finder`, `lens_service`, `lens_pass`, `lens_author`, `_memory_conn`, `_memory_read_conn`, `_memory_pipeline`. Add `self.memory_curator` and `self._doc_store`.
- `memory_ready` → `return self.memory_retrieval is not None`.
- `stop()` → `if self.memory_curator: await self.memory_curator.stop()`.
- `tool_services()` → register `services[MEMORY_DOCS_SERVICE] = self._doc_store` when present; keep `search_index`; drop the three memory/lens service registrations + their imports.
- In `connect()`/after indexer is up: `if self.search_index: stores.sessions.store.attach_search_index(self.search_index)`.
- Drop imports of `MemoryPipeline`, `MemoryStore`, `Embedder` (if now unused), `_CaptureSessions`.

### B.2 `chat.py` exact rewire

- `ChatDeps`: drop `memory`, `memory_service`; keep `memory_retrieval`; add `memory_curator: object | None = None`.
- `ChatContext`: replace `memory_ingest` with `memory_curator: object | None = None`.
- `_retrieve_memory_context(memory_retrieval, user_message, project_context)`: keep the `< _MEMORY_RECALL_FLOOR` guard, then:
  ```python
  scopes = [Scope(kind=ScopeKind.USER)]
  if project_context and project_context.project_id:
      scopes = [Scope(ScopeKind.PROJECT, str(project_context.project_id)),
                Scope(ScopeKind.USER)]
  try:
      return await memory_retrieval.render(scopes)
  except Exception:
      _logger.warning("memory docs load failed", exc_info=True); return None
  ```
  (`render` is zero-LLM; the `_MEMORY_TOKEN_BUDGET` const can be deleted or left unused.)
- Construction site (~line 690): `memory_ingest=deps.memory_retrieval` → `memory_curator=deps.memory_curator`.
- `_record_completed_run` write trigger (~961): replace the `schedule_ingest_session` block with:
  ```python
  curator = ctx.memory_curator
  if curator is not None:
      scope = (Scope(ScopeKind.PROJECT, str(ctx.session_state.project_id))
               if ctx.session_state.project_id else Scope(ScopeKind.USER))
      curator.schedule_curation(ctx.session_state.session_id, scope)
  ```
  Add `from ntrp.memory.models import Scope, ScopeKind` at top.

### B.3 `runner.py` exact rewire

- `OperatorDeps`: drop `memory`, `memory_service`; keep `memory_retrieval`.
- `_retrieve_memory_context(memory_retrieval, prompt)`: keep floor guard, then `return await memory_retrieval.render([Scope(kind=ScopeKind.USER)])` in a try/except returning None. Import `Scope, ScopeKind` from `ntrp.memory.models`; drop `Retrieval` import.

### B.4 `server/routers/memory.py` minimal docs API (replaces all 629 lines)

```python
router = APIRouter(prefix="/memory", tags=["memory"])

def _store(knowledge=Depends(require_knowledge_runtime)):
    if not knowledge.memory_retrieval:
        raise HTTPException(503, "memory not ready")
    return knowledge.memory_retrieval

@router.get("/scopes")            # -> {"scopes": [{"kind","key"}]}
@router.get("/doc")               # query: kind, key -> {"content"}  (load(scope).content)
@router.put("/doc")               # body: {kind,key,content} -> write(scope, content)
```
Delete every `/items`, `/lenses*`, `/graph`, `/search`, `/remember`, writeback route. Update the desktop API client + any UI calling them (out of server scope — flag to the frontend task; `apps/desktop/src/api.ts` is already dirty in git status, coordinate).

---

## C. CURATOR DESIGN

Model: `config.memory_model` (the cheap model), with `reasoning_effort` from `_memory_reasoning_effort` (verified helper in knowledge.py). NOT chat_model.

Single LLM call. Prompt shape (system + user):

- SYSTEM: "You maintain a durable MEMORY DOC about the user (or a project). You are given the CURRENT DOC and NEW CONVERSATION TURNS. Return the COMPLETE updated doc. Rules: (1) NOVELTY GATE — if the new turns contain nothing durable AND new (stable preferences, decisions, facts, identity, long-lived project context), output exactly the sentinel `<<NO_CHANGE>>` and nothing else. Transient task state, one-off questions, and anything already captured do NOT count. (2) Merge, don't append blindly: fold new facts into existing sections, correct/replace superseded facts, dedupe. (3) BUDGET: keep the doc under ~8000 characters; if over, compress the least-important/oldest details, never the core durable facts. (4) Plain markdown, terse bullets, no preamble."
- USER: 
  ```
  CURRENT DOC (scope=<kind>:<key>):
  <doc.content or "(empty)">

  NEW TURNS (since seq <watermark>):
  <flattened user/assistant turns>
  ```

Output handling:
- Strip; if equals `<<NO_CHANGE>>` (case-insensitive, allowing surrounding whitespace) → no write, advance watermark, return False.
- Else treat the whole response as the new doc body → `doc_store.write(scope, body)`.

Budget-compression rule: the store hard-caps at `char_budget*1.1`; the prompt instructs soft compression at 8k. If the model returns over the hard cap, log + still write the truncated-to-cap body (truncate on a bullet boundary).

Watermark: read `meta['curate_watermark:{session_id}']` (default -1). After a successful `write` OR a confirmed `<<NO_CHANGE>>`/empty-turns path, set it to the max `seq` seen. Advance-after-success only, so a crashed call re-processes the same turns next time (idempotent because the LLM dedupes against the current doc).

New-turns read: `sessions.search_messages` is FTS-only; instead load the full ordered transcript for the session and filter `seq > watermark`. Use the existing `session_messages` load path (the store already exposes ordered message rows by session — `SQL_LOAD_SESSION_MESSAGES_JSON`); pass through `_flatten_message_text` for compact text. ASSUMPTION: add a thin `SessionService.messages_since(session_id, seq)` if no ordered+seq accessor is exposed; recon shows rows carry `seq`, so this is a small read method, not new schema.

---

## D. HYBRID TRANSCRIPT SEARCH

Verified facts: transcript FTS = `session_messages_fts` in **sessions.db** (`context/store.py`); the vector index = `items_vec` in **search.db** (`search/store.py`), driven by the `SearchIndex` wrapper. They are different DBs/connections — bridge them in code, not SQL.

1. Index on persist — `ntrp/context/store.py::_mirror_session_messages`, INSERT branch only, per §A.4. `source="transcript"`, `source_id="{session_id}:{seq}"`, `content=search_text`, metadata `{session_id, seq, role}`. Fire-and-forget task; embedding is done inside `SearchIndex.upsert`.
2. Attach: `ContextStore.attach_search_index(idx)` + `self._search_index` field, set from `KnowledgeRuntime` after the indexer connects. When unset, all behavior is FTS-only (no regression).
3. Hybrid query — `search_messages` (§A.5): FTS list + `search_index.store.vector_search` list → `rrf_merge([fts, vec])` (existing `ntrp/search/retrieval.py:13`, k=`RRF_K`) → take top-N keys → hydrate snippet/role/created_at from `session_messages`. Map vector `item_id`→`{session_id,seq}` via the SearchStore item's stored metadata.
4. Backfill: a one-time pass embedding existing `session_messages` rows (source="transcript") is OPTIONAL; the `SearchIndex.sync` path or a small loop over existing rows. Flag as a follow-up, not blocking.

Keep it thin: no new ranking module, reuse `rrf_merge`; vector is strictly additive.

---

## E. DISTILLATION MIGRATION (one-time script)

Lives at `ntrp/scripts/distill_memory_to_docs.py` (NEW), run via `uv run python -m ntrp.scripts.distill_memory_to_docs`. It must run BEFORE deleting `store.py`/`models.py` claim types — so it reads the OLD schema directly via raw SQL (no import of the soon-deleted store), making it self-contained and deletion-order-safe.

Steps:
1. Open `config.memory_db_path` read-only.
2. `SELECT scope_kind, scope_key, canonical_subject, content, valid_from, provenance FROM memory_items WHERE status='active' ORDER BY scope_kind, scope_key, canonical_subject, created_at`.
3. Group rows by `(scope_kind, scope_key)`, then by `canonical_subject`.
4. Per `(scope)` group: ONE LLM call (memory_model) — "Synthesize these grouped claims into a clean durable MEMORY DOC (markdown bullets, ~8k char budget, group by subject)." Input = the subject→claims listing.
5. Write each result via `MemoryDocStore.write(scope, body)` to `config.memory_docs_dir` (user.md / projects/<slug>.md).
6. Print a summary + the written file paths; STOP. Do not drop anything.
7. After the user eyeballs the docs (`git diff` of the docs dir), a second invocation `--drop` (or a manual SQL step) drops `memory_items`, `memory_item_parents`, `lens_*` tables and deletes the lens files dir. This `--drop` step is gated behind an explicit flag and prints what it will remove first.

Project slug: reuse `MemoryDocStore._path_for`'s slug of `scope_key` so distilled filenames match the runtime's.

---

## F. BUILD ORDER & PARALLELIZATION

### Group 1 — PARALLEL-SAFE new isolated files (distinct paths, no shared-registry edits)
Each can be a separate agent; they only create new files + are imported later.
- `ntrp/memory/models.py` (REWRITE — but it's leaf; everything else imports the new symbols, so land it FIRST and let Group 2 depend on it). → SERIALIZE as the very first step, then Groups 1b/2 proceed.
- `ntrp/memory/docs.py` (NEW)
- `ntrp/memory/curator.py` (NEW — imports docs.py + models.py)
- `ntrp/scripts/distill_memory_to_docs.py` (NEW — raw SQL, imports only docs.py)

> Practical sequencing: models.py first (tiny), then docs.py + distill in parallel, then curator.py (needs docs.py).

### Group 2 — SEQUENTIAL integration (ONE agent; all shared-file edits + deletions)
Do in this order to keep imports valid at every step:
1. `ntrp/tools/memory.py` REWRITE (remember/forget; new `MEMORY_DOCS_SERVICE`).
2. `ntrp/integrations/core.py` EDIT (drop lens import + recall; wire forget).
3. `ntrp/context/store.py` EDIT (attach_search_index + index-on-insert + hybrid search_messages).
4. `ntrp/server/runtime/knowledge.py` REWRITE `_init_memory` + fields + tool_services + stop + attach.
5. `ntrp/server/runtime/core.py` EDIT (props + build_chat_deps + build_operator_deps).
6. `ntrp/services/chat.py` EDIT (deps/context fields, read fn, write trigger).
7. `ntrp/operator/runner.py` EDIT (deps fields + read fn).
8. `ntrp/automation/suggestions.py` EDIT (replace 3 claim/lens gatherers with doc render).
9. `ntrp/server/runtime/automation.py` EDIT (remove pattern_finder daily handler).
10. `ntrp/server/routers/memory.py` REWRITE (minimal docs API).
11. DELETIONS (import-safe order — nothing imports these after steps 1–10):
    `ntrp/memory/pipeline/prompts*.py` → `pipeline/types.py` → `pipeline/{admit,capture,extract}.py` → `pipeline/{reconcile,consolidate,membership}.py` → `pipeline/{project,writeback,lens_generation}.py` → `pipeline/{retrieve,write,runtime}.py` → `pipeline/__init__.py` → `memory/lens/**` → `memory/store.py` → `memory/migrations.py` → `memory/SCHEMA.md` → `memory/__init__.py` REWRITE last.

### Group 3 — migration + tests (after Group 2 compiles)
- Run distillation (E) against a copy of the user's memory.db.
- Tests (G).

SHARED-FILE CONFLICT FLAGS (must be serialized, all in Group 2): `knowledge.py`, `core.py`, `chat.py`, `context/store.py`, `integrations/core.py`, `memory/__init__.py`. No two Group-1 files touch the same path. `apps/desktop/src/api.ts` (frontend) consumes the old REST routes — flag to the desktop owner; it's outside server scope but WILL break if shipped uncoordinated.

---

## G. TEST PLAN

DELETE (pipeline/lens-specific): `tests/test_memory_pipeline_e2e.py`, `tests/test_pipeline_admit.py`, `tests/test_pipeline_capture.py`, `tests/test_pipeline_retrieve.py`, `tests/test_pipeline_write.py`, `tests/memory/test_consolidate.py`, `tests/memory/pipeline/**`, `tests/memory/lens/**`, `tests/test_memory_reconcile.py`, `tests/test_tool_recall.py`. (Verify exact paths first with `ls`; recon listed these but some may differ.)

REWRITE:
- `tests/test_memory_remember.py` → assert `remember` appends a bullet into `user.md` / `projects/<slug>.md` via a temp `MemoryDocStore`, and `forget` removes it.
- `tests/test_memory_store.py` → becomes `tests/test_memory_docs.py`: `MemoryDocStore` load/render/append/forget/write/list_scopes + budget FIFO trim + path resolution.

NEW:
- `tests/test_memory_curator.py`: curate_session with a stub LLM — (a) returns `<<NO_CHANGE>>` → no write, watermark advances; (b) returns new body → doc written; (c) watermark filters already-seen seqs; (d) over-budget body truncated.
- `tests/test_transcript_hybrid_search.py`: with a fake SearchIndex returning vector hits, `search_messages` merges FTS+vector via rrf and returns hydrated hits; without an attached index, identical to FTS-only.
- `tests/test_distill_memory.py`: seed a temp memory.db with a few active claims, run the distill function with a stub LLM, assert docs written to a temp docs dir.

VERIFICATION COMMANDS:
```bash
cd /Users/escept1co/src/ntrp/apps/server
uv run python -c "import ntrp.server.runtime.core, ntrp.services.chat, ntrp.operator.runner, ntrp.integrations.core, ntrp.server.routers.memory, ntrp.memory, ntrp.memory.docs, ntrp.memory.curator, ntrp.tools.memory, ntrp.context.store"   # import smoke (no dangling deleted-module imports)
uv run python -c "import ntrp.memory.pipeline" 2>&1 | grep -q ModuleNotFoundError && echo "pipeline gone OK"
uv run pytest tests/test_memory_docs.py tests/test_memory_curator.py tests/test_memory_remember.py tests/test_transcript_hybrid_search.py tests/test_distill_memory.py -q
uv run pytest tests/ -q     # full suite green
```
Add a grep gate to prove no live code still imports deleted modules:
```bash
cd /Users/escept1co/src/ntrp/apps/server && grep -rn "memory.pipeline\|memory.lens\|MemoryStore\|WriteSeam\|Retriever\|lens_tool\|recall_tool\|schedule_ingest_session\|MEMORY_WRITE_SERVICE\|MEMORY_READ_SERVICE\|MEMORY_LENS_SERVICE" ntrp/ | grep -v "\.pyc"   # must be empty
```
```

Blueprint complete. Key corrections I made to the recon (verified against live code) — call these out to implementers:

1. **`search_index` is a `SearchIndex` wrapper, not a raw `SearchStore`.** `SearchIndex.upsert(source, source_id, title, content, metadata)` embeds internally — do NOT serialize embeddings or call `SearchStore.upsert` directly. The recon's "call SearchStore.upsert + serialize" instruction is wrong.
2. **Transcript FTS (sessions.db) and the vector index (search.db) are separate databases.** Hybrid search must bridge them in Python via `rrf_merge`, not in SQL. `search_messages` lives at `context/store.py:2626` and uses `self.read_conn`.
3. **Project scope `key` is the raw `project_id` string, not a slug.** Slugify only for the on-disk filename inside `MemoryDocStore._path_for`.
4. **`ToolContext` fields are `.project` (ProjectContext|None), `.services`, `.session_id`; `ToolExecution.tool_id`** — confirmed for the remember/forget executors.
5. **The pattern_finder daily handler MUST be removed, not kept** (recon said "keep") — it calls `get_pattern_finder()` which vanishes with the pipeline; leaving it breaks `automation.py` at import/registration.
6. **`memory/store.py` should be DELETED, not rewritten** — nothing survives except a one-table `meta` watermark, which the `Curator` owns directly. (Flagged one open assumption: reuse memory.db for that meta table vs. sessions.db — confirm before coding.)
7. **`ContextStore` has no `SearchIndex` today** — added `attach_search_index()` because the indexer is built lazily after stores connect; this is new wiring the recon missed.
8. Construction sites verified: `ChatDeps`/`OperatorDeps` are built in `server/runtime/core.py:296` and `:326`, and the chat write trigger passes `memory_ingest=deps.memory_retrieval` at `chat.py:690` (must become `memory_curator=deps.memory_curator`).

Relevant absolute paths: `/Users/escept1co/src/ntrp/apps/server/ntrp/memory/{models,docs,curator}.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/memory/pipeline/`, `/Users/escept1co/src/ntrp/apps/server/ntrp/memory/lens/`, `/Users/escept1co/src/ntrp/apps/server/ntrp/services/chat.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/operator/runner.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/server/runtime/{knowledge,core,automation}.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/tools/memory.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/integrations/core.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/context/store.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/search/{index,store,retrieval}.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/server/routers/memory.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/automation/suggestions.py`, `/Users/escept1co/src/ntrp/apps/server/ntrp/config.py`.
