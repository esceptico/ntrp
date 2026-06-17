# Memory (internal)

The single living description of how ntrp memory works today. Earlier specs
(claims, lenses, derivation graphs, dreams) are gone — this is the only design.

## Substrate: scoped records

Memory is one flat pool of atomic, self-contained **records** in a SQLite table
(`apps/server/ntrp/memory/records.py`, `RecordStore`). A record is typed by
function, not subject:

- `directive` — a procedure/rule that should steer the agent's behaviour
- `fact` — a durable statement about the user or their world (preferences and
  project facts are facts with the right scope)
- `source` — a captured receipt/reference from an integration or tool
- `summary` — **being retired.** Still a valid `Kind` for legacy rows and the
  curator's `note`→`summary` fold, but not a target for new first-class writes.

The record shape lives in `apps/server/ntrp/memory/models.py`:

```py
@dataclass
class Record:
    id: str
    text: str
    kind: str = Kind.FACT
    scope_kind: str | None = None
    scope_key: str | None = None
    created_at: str
    last_confirmed_at: str
    superseded_by: str | None = None
    pinned: bool = False
    source_ref: SourceRef | None = None
```

There is **no graph, no derivation DAG, no claims, no lenses.** Lineage is a
single axis: `superseded_by` closes a record into its successor; supersession is
the only active/inactive lifecycle. Freshness is `last_confirmed_at`. `pinned`
records survive every decay pass.

Open-vocabulary **labels** (referents and categories) attach to records at write
time (`record_labels`), decided once by the curator. They are used for the
"everything about X" page and label-hygiene folding — they are not a hierarchy.

### Scopes

`scope_kind`/`scope_key` (`apps/server/ntrp/memory/scopes.py`) are default
**visibility metadata**, not partitions. Write resolution:

- directives → `global`
- an active project → `project/<knowledge_scope or project_id>`
- an integration source ref → `integration/<kind>:<ref>`
- otherwise summaries fall to `session/<session_id>` (or `user` with no session)
- everything else → `user`

Read defaults (`scopes_for_read`): `global` + `user`, plus the active
`project` or `session` scope when present. This keeps session/integration writes
from polluting the always-visible profile.

## Write path: the Curator

The **Curator** (`apps/server/ntrp/memory/curator.py`) is the background writer.
One LLM call per session: it reads new transcript turns since a per-session
watermark (`curate_watermark:{session_id}` in a `meta` table it owns inside the
memory DB), reconciles them against the **existing similar records**, and emits
`ADD`/`UPDATE`/`SUPERSEDE`/`NOOP` ops plus labels. Because it chooses ops against
existing records, dedup happens inside the LLM op choice — it does not blindly
mint duplicates.

Triggers: after a chat run completes, and a periodic backstop sweep
(`SWEEP_INTERVAL_SECONDS`, capped at `SWEEP_SESSION_LIMIT` sessions). A session
with no new turns costs one DB read and no LLM call.

The agent-facing **`remember` tool** (`apps/server/ntrp/tools/memory.py`) also
writes, via a direct `store.add` with a `chat_turn` source ref and the same
scope resolution. This is the one path that bypasses curator dedup (the known
double-mint surface); consolidate cleans up the overlap afterwards.

## Hygiene: Consolidate + prune (the LINT)

**Consolidate** (`apps/server/ntrp/memory/consolidate.py`) is the periodic
health-check that turns the raw pile into a small, current body. It is
demote/merge-only and `O(delta)`: candidates are records confirmed since the last
watermark plus each one's recall neighborhood. It never authors a new fact and
never raises trust. Per sweep it can:

- MERGE near-duplicates onto one survivor
- SUPERSEDE stale/contradicted records into a newer one
- RETYPE a record to its correct function-kind (e.g. `note`→`fact`)
- DROP genuine orphans
- run one bounded label-hygiene call that folds near-duplicate label spellings
  via `rename_label`

Pinned records are inviolable. With no LLM configured the pass is a no-op.

At the end of each sweep (and on demand) it calls `RecordStore.prune()` — the
deterministic **LINT**: hard-delete superseded tombstones, drop the labels they
orphan, and reconcile the vector index so recall can never surface dead content.
Idempotent. Pinned records are never superseded, so prune never touches them.

Consolidate runs out-of-process by default (`scripts.run_consolidation`); set
`NTRP_INLINE_CONSOLIDATE=1` to run it inline after curation.

## Read path

### Resident profile (always-on)

`apps/server/ntrp/memory/profile.py::resident_profile()` renders a small,
char-bounded `## Profile` block into the system prompt for **both** interactive
chat and operator/automation runs. Pure DB I/O, no LLM. It pulls directives,
durable user facts, and anything pinned within the read scopes, with separate
char budgets per slice (directives first, so behaviour rules can't be evicted by
a flood of recent facts):

- `DIRECTIVE_CHAR_BUDGET = 3000`
- `FACT_CHAR_BUDGET = 2000`

### Recall (pull-only)

Deeper retrieval is on demand via the **`recall` tool**: hybrid lexical
(`records_fts`) ⊕ semantic (shared `SearchIndex`, `source="record"`) fused with
`rrf_merge`, then post-filtered by kinds, scopes, and supersession
(`RecordStore.search`). `recall` defaults to `directive`+`fact`; `summary`/
`source` are opt-in for catch-up or receipts. `forget` searches the same way and
deletes the best hit, listing other near-matches instead of dead-ending.

### Artifacts browse UI

`apps/server/ntrp/memory/artifacts.py` projects records into a read-only
markdown filesystem (`ArtifactMemoryStore`) for the desktop Memory view and the
agent's `memory_tree`/`memory_read`/`memory_search` tools. It is a generated
projection of the records — `memory_patch` edits the projection files only and
never mutates canonical DB records; `memory_rebuild` regenerates them.

## Admin REST surface

`apps/server/ntrp/server/routers/memory.py`, mounted at `/admin/memory/*`:

- `GET  /scopes` — currently returns `[]` (scopes are enforced internally, not a
  user-facing browser)
- `GET  /artifacts`, `GET /artifacts/{path}`, `POST /artifacts/rebuild` — the
  generated markdown browser
- `POST /record` — quick-capture a single record (the desktop pin-to-memory
  affordance)
- `POST /record/{id}/pin` — pin/unpin (survives consolidation decay)
- `GET  /items`, `GET /items/{id}` — list/get records as the desktop
  `MemoryItem` shape; item detail returns empty `parents`/`children` (no edges)
- `GET  /search` — hybrid record search
- `POST /prune` — manually trigger the LINT pass

The `MemoryItem` JSON carries compatibility defaults (`provenance`, `standing`,
`depth`, `corroboration`) for the existing desktop client; they are derived from
record fields, not a separate model.

## Key files

| Concern | File |
| --- | --- |
| Record store / search / prune | `apps/server/ntrp/memory/records.py` |
| Record + Kind + SourceRef models | `apps/server/ntrp/memory/models.py` |
| Scope resolution | `apps/server/ntrp/memory/scopes.py` |
| Background writer | `apps/server/ntrp/memory/curator.py` |
| Consolidate / LINT | `apps/server/ntrp/memory/consolidate.py` |
| Resident profile injection | `apps/server/ntrp/memory/profile.py` |
| Markdown projection | `apps/server/ntrp/memory/artifacts.py` |
| Agent tools (remember/recall/forget + fs) | `apps/server/ntrp/tools/memory.py` |
| Admin REST router | `apps/server/ntrp/server/routers/memory.py` |
</content>
</invoke>
