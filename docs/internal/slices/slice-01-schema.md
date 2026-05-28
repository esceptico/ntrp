# Slice 01 — schema burn + rebuild

Status: draft, awaiting tim's approval.
Parent spec: `docs/internal/ntrp-memory-redesign-spec.md` (spec wins).
Workflow split: PM (ntrp agent) writes this brief and reviews the diff. Implementer (codex exec headless) writes the code. Destructive DB ops are handed back to tim.

---

## 1. Goal

Land migration **v31** that:

1. Drops every existing memory table.
2. Creates the three new primitive tables (`memory_items`, `memory_item_parents`, `episode_buffers`) + their FTS5 and vec0 satellites.
3. Has tests proving the schema works (round-trip insert/read, FK integrity, edge roles).

No retrieval logic, no connector logic, no UX. No backfill from old data.

After this slice ships, the server still starts but the entire memory pipeline (writes from chat, retrieval, UI) will be broken until later slices replace them. Acceptable because the goal explicitly states: "burn, not backfill".

---

## 2. Source-of-truth references

Codex must read these before writing code:

- `docs/internal/ntrp-memory-redesign-spec.md` §2 (data model) — the authoritative shape.
- `docs/internal/ntrp-memory-redesign-spec.md` §3.7 (confidence) — informs the `confidence` column constraints.
- This file (slice brief).
- Existing patterns to mirror:
  - `apps/server/ntrp/memory/store/migrations.py` — migration framework (numbered fn → `_MIGRATIONS` list → bump `CURRENT_VERSION`).
  - `apps/server/ntrp/memory/store/base.py` lines ~380–435 — how vec0 virtual tables are created with the "extension may be missing" guard.
  - `apps/server/tests/memory/test_migrations.py` — test style (use `TEST_EMBEDDING_DIM` from `tests/conftest.py`).

If anything in this brief contradicts the spec, **spec wins** — and Codex should stop and flag the contradiction in chat rather than picking a side silently.

---

## 3. Tables to drop

Goal definition of done says "all current memory tables". Concretely, drop every table in this list (verified against the current `~/.ntrp/memory.db`):

```
entities
entity_aliases
entity_identity_edges
entity_mentions
entity_refs
entity_resolution_candidates
entity_resolution_commits
facts
facts_fts  facts_fts_config  facts_fts_data  facts_fts_docsize  facts_fts_idx
facts_vec  facts_vec_chunks  facts_vec_info  facts_vec_rowids   facts_vec_vector_chunks00
knowledge_entity_refs
knowledge_objects
knowledge_objects_fts        knowledge_objects_fts_config  knowledge_objects_fts_data
knowledge_objects_fts_docsize  knowledge_objects_fts_idx
knowledge_objects_vec        knowledge_objects_vec_chunks  knowledge_objects_vec_info
knowledge_objects_vec_rowids knowledge_objects_vec_vector_chunks00
memory_access_events
memory_events
obs_entity_refs
observation_facts
observations
observations_fts             observations_fts_config  observations_fts_data
observations_fts_docsize     observations_fts_idx
observations_vec             observations_vec_chunks  observations_vec_info
observations_vec_rowids      observations_vec_vector_chunks00
temporal_checkpoints
```

Tables to **keep**:
- `meta` — schema version pointer lives here.
- `sqlite_sequence`, `sqlite_stat1` — SQLite internals, untouched.

Drop order:
1. Drop FTS5 contentless tables (their `_data`/`_idx`/etc. shadows are managed by SQLite — see §10 clarification 4).
2. Drop vec0 virtual tables (same — let SQLite manage shadows).
3. Drop base tables (`facts`, `observations`, `knowledge_objects`).
4. Drop entity tables (`entities`, `entity_aliases`, `entity_identity_edges`, `entity_mentions`, `entity_refs`, `entity_resolution_candidates`, `entity_resolution_commits`, `obs_entity_refs`, `observation_facts`, `knowledge_entity_refs`).
5. Drop `memory_access_events`, `memory_events`, `temporal_checkpoints`.

For each `DROP TABLE`, use `DROP TABLE IF EXISTS <name>` so the migration is idempotent on partially-migrated DBs.

---

## 4. Tables to create

### 4.1 `memory_items` (primary table)

```sql
CREATE TABLE memory_items (
    id              TEXT PRIMARY KEY,                       -- ulid string (see §10 clarification 2)
    kind            TEXT NOT NULL CHECK (kind IN (
                        'episode', 'observation', 'claim',
                        'skill', 'proposal', 'artifact_ref'
                    )),
    content         TEXT NOT NULL,
    provenance      TEXT NOT NULL CHECK (provenance IN (
                        'recorded', 'inferred', 'user_authored', 'external'
                    )),
    source_refs     TEXT NOT NULL DEFAULT '[]',              -- JSON array of SourceRef
    confidence      REAL NOT NULL DEFAULT 0.5 CHECK (
                        confidence >= 0.0 AND confidence <= 1.0
                    ),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
                        'active', 'superseded', 'archived'
                    )),
    valid_from      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invalid_at      TIMESTAMP,
    scope           TEXT NOT NULL DEFAULT 'user',            -- 'user' | 'project:<id>' | 'session:<id>'
    tags            TEXT NOT NULL DEFAULT '[]',              -- JSON array of string
    artifact_ref    TEXT,                                    -- path/uri for kind in (skill, artifact_ref)
    usage           TEXT NOT NULL DEFAULT '{"activated":0,"helped":0,"hurt":0,"ignored":0}', -- JSON UsageRollup
    feedback        TEXT NOT NULL DEFAULT '{"thumbs_up":0,"thumbs_down":0,"corrections":0}', -- JSON FeedbackRollup
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- hot-path index (status filter + scope filter + kind filter is the dominant retrieval shape)
CREATE INDEX idx_memory_items_status_scope_kind ON memory_items(status, scope, kind);
-- temporal queries
CREATE INDEX idx_memory_items_valid_from ON memory_items(valid_from);
CREATE INDEX idx_memory_items_invalid_at ON memory_items(invalid_at);
-- update tracking
CREATE INDEX idx_memory_items_updated_at ON memory_items(updated_at);
```

Notes:
- `source_refs`, `tags`, `usage`, `feedback` are JSON strings (TEXT). Typed-column access is not needed at this slice. Shape definitions live in spec §2.1 and §2.3 — Codex must not invent additional fields.
- `id` is TEXT (ulid), not INTEGER. We want stable distributed-style IDs since this table is the canonical reference target for `memory_item_parents`, `source_refs`, and future external references.

### 4.2 `memory_item_parents` (edge DAG)

```sql
CREATE TABLE memory_item_parents (
    child_id    TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    parent_id   TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN (
                    'step', 'evidence', 'contradicts',
                    'supersedes', 'similar_to'
                )),
    "order"     INTEGER,                                     -- only meaningful for role='step'
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (child_id, parent_id, role)
);

CREATE INDEX idx_mip_child ON memory_item_parents(child_id);
CREATE INDEX idx_mip_parent ON memory_item_parents(parent_id);
CREATE INDEX idx_mip_role ON memory_item_parents(role);
```

Notes:
- Composite PK on `(child_id, parent_id, role)` allows the same pair to coexist with different roles (rare but legal — e.g. evidence + similar_to).
- `"order"` is quoted because `ORDER` is a reserved word.

### 4.3 `episode_buffers` (transient, per spec §2.5 episode)

```sql
CREATE TABLE episode_buffers (
    id                      TEXT PRIMARY KEY,
    scope                   TEXT NOT NULL,
    source_kind             TEXT NOT NULL,                   -- 'chat_msg' | 'tool_call' | ...
    started_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    turn_count              INTEGER NOT NULL DEFAULT 0,
    tokens                  INTEGER NOT NULL DEFAULT 0,
    content_so_far          TEXT NOT NULL DEFAULT '',
    source_refs_so_far      TEXT NOT NULL DEFAULT '[]',      -- JSON array of SourceRef
    running_centroid_vec    BLOB,                            -- packed float32, or NULL until first embed
    closed_at               TIMESTAMP                         -- non-null once finalized
);

-- At most one open buffer per (scope, source_kind)
CREATE UNIQUE INDEX uniq_episode_buffers_open_per_scope
    ON episode_buffers(scope, source_kind)
    WHERE closed_at IS NULL;

CREATE INDEX idx_episode_buffers_last_activity ON episode_buffers(last_activity_at);
```

### 4.4 FTS5 satellite

The existing `knowledge_objects_fts` uses external-content mode (`content='knowledge_objects', content_rowid='id'`) because `knowledge_objects.id` is INTEGER. We cannot reuse that pattern: `memory_items.id` is TEXT (uuid hex), and FTS5 external-content requires an INTEGER rowid.

Use **standalone FTS5** with a TEXT `item_id` column and manual-sync triggers:

```sql
CREATE VIRTUAL TABLE memory_items_fts USING fts5(
    item_id UNINDEXED,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER memory_items_ai AFTER INSERT ON memory_items BEGIN
    INSERT INTO memory_items_fts(item_id, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER memory_items_ad AFTER DELETE ON memory_items BEGIN
    DELETE FROM memory_items_fts WHERE item_id = old.id;
END;

CREATE TRIGGER memory_items_au AFTER UPDATE ON memory_items BEGIN
    DELETE FROM memory_items_fts WHERE item_id = old.id;
    INSERT INTO memory_items_fts(item_id, content) VALUES (new.id, new.content);
END;
```

Verified empirically (2026-05-27): insert/update/delete on `memory_items` keeps `memory_items_fts` consistent; `MATCH` returns the right `item_id`. Queries that need to fetch full rows should `JOIN memory_items ON memory_items.id = memory_items_fts.item_id` after MATCH.

**Do NOT use external-content mode.** If Codex sees the existing `knowledge_objects_fts` pattern and tries to copy it verbatim, it will fail because of the TEXT vs INTEGER id mismatch — STOP and flag instead.

### 4.5 vec0 satellite

Add a `memory_items_vec` virtual table in `apps/server/ntrp/memory/store/base.py`, alongside the existing block that creates `observations_vec` / `facts_vec` / `knowledge_objects_vec`. Use the same try/except guard (`if "no such module: vec0" in str(exc): warn and skip`).

```python
CREATE VIRTUAL TABLE memory_items_vec USING vec0(
    item_id TEXT PRIMARY KEY,
    embedding float[<DIM>]
)
```

`<DIM>` should reuse whatever embedding-dim constant the existing three vec tables use. Codex should inspect base.py and use the same source; do not re-pick a dimension.

**Different from existing vec tables**: the existing three use INTEGER primary keys (`observation_id`, `fact_id`, `knowledge_object_id`). `memory_items_vec` uses **`item_id TEXT PRIMARY KEY`** because `memory_items.id` is TEXT (uuid hex). Verified empirically 2026-05-27 that vec0 accepts TEXT primary keys and cosine-distance queries work correctly with them.

The vec table lives in base.py (created on every connection if missing), not inside migrations.py. That's the existing convention — vec extension may be absent in some environments.

---

## 5. Migration code shape (concrete)

In `apps/server/ntrp/memory/store/migrations.py`:

1. Bump `CURRENT_VERSION = 31`.
2. Add `async def _migrate_v31(conn: aiosqlite.Connection) -> None:` with:
   - Log: `_logger.info("Migration v31: memory redesign — burn old tables, create memory_items + memory_item_parents + episode_buffers")`
   - Drop sequence (see §3).
   - Create sequence (see §4.1–4.4; vec table is handled in base.py per §4.5).
3. Append `(31, _migrate_v31)` to `_MIGRATIONS`.

In `apps/server/ntrp/memory/store/base.py`:

- Add the `memory_items_vec` virtual table creation in the same block as the existing three vec tables, with the same try/except guard.

**Do not modify** anything else in `apps/server/ntrp/memory/` in this slice. We expect the rest of the package (`facts.py`, `observations.py`, `service.py`, etc.) to break at import-time after the migration runs. That's expected — slices 2/3 replace them. Codex should leave those broken modules untouched and not attempt to "fix" them.

---

## 6. Tests

Add `apps/server/tests/memory/test_slice01_schema.py` with:

1. **Round-trip insert/read on `memory_items`** for each of the 6 `kind` values.
2. **Round-trip on `memory_item_parents`** for each of the 5 `role` values.
3. **CHECK constraint enforcement**:
   - Inserting a `memory_items` row with `kind='nonsense'` raises.
   - Inserting with `confidence=1.5` raises.
   - Inserting `memory_item_parents` with `role='nonsense'` raises.
4. **FK integrity**: deleting a parent `memory_items` row cascades to `memory_item_parents` (both child and parent edges referencing it).
5. **`episode_buffers` unique open-per-scope**: inserting two buffers for the same `(scope, source_kind)` both with `closed_at IS NULL` raises. Closing the first (set `closed_at`) and inserting a second is allowed.
6. **FTS round-trip**: insert two `memory_items` rows, run an FTS5 MATCH query, get the right one back.
7. **Migration idempotency**: running migrations a second time on a v31 DB is a no-op (no errors).
8. **`run_migrations` from a fresh DB** reaches `CURRENT_VERSION == 31` and the three new tables exist (verify via `sqlite_master`).

Use the existing test patterns from `apps/server/tests/memory/test_migrations.py`. Use `TEST_EMBEDDING_DIM` for any vec interactions (though the schema tests probably won't need vec).

**FK cascade gotcha**: `PRAGMA foreign_keys` is OFF by default in SQLite per-connection. The prod connection helper in `apps/server/ntrp/database.py` sets `PRAGMA foreign_keys=ON` in `connect()`. Tests must use the same path (either the existing fixture from `tests/conftest.py`, or explicitly call `await conn.execute("PRAGMA foreign_keys=ON")` before exercising the cascade test). Otherwise the FK cascade test will pass incorrectly (rows not cascaded but no error raised).

If existing tests in `test_migrations.py` reference the now-dropped tables and fail, Codex must NOT silently delete or skip them. Allowed action: mark them with `@pytest.mark.xfail(reason="slice 1 burns pre-v31 schema; data-survival assertions no longer hold", strict=False)`. Codex must list every test it xfails in the final report — PM reviews and may revert if the xfail is masking a real bug.

There are 19 tests in `test_migrations.py` today. We expect most "seed old schema, run migrations, assert data survived" tests to need xfail. Tests that ONLY check `schema_version == CURRENT_VERSION` may still pass.

---

## 7. Out of scope (do NOT do)

- No Python models / pydantic shapes / store classes for `memory_items`. Slice 2 owns that.
- No retrieval API. Slice 3.
- No deletion of the existing `facts.py`, `observations.py`, `service.py`, `models.py`. Leave them broken.
- No backup of `~/.ntrp/memory.db`. **tim runs the backup manually before this migration is allowed to touch the live DB.** Tests run on temp DBs.
- No VACUUM. Spec says not to.
- No app.db or any other DB.
- No git commit, no git add. PM reviews diff manually.

---

## 8. Codex prompt (verbatim — this block is what gets pasted into `codex exec`)

```
You are implementing slice 1 of the ntrp memory redesign as PM/architect-supervised work.
The slice brief is at docs/internal/slices/slice-01-schema.md and is the authoritative
instruction for this task. The spec at docs/internal/ntrp-memory-redesign-spec.md is the
source-of-truth for data model details; if the brief and spec conflict, STOP and report
the contradiction instead of guessing.

Read both documents before writing code. Then implement migration v31 exactly as the
brief specifies in §3, §4, §5. Add the tests described in §6. Do NOT do anything in §7.

Pattern conformance:
- Migration framework: mirror existing _migrate_vN functions in
  apps/server/ntrp/memory/store/migrations.py.
- Vec0 table creation: mirror the existing block in apps/server/ntrp/memory/store/base.py
  that creates observations_vec / facts_vec / knowledge_objects_vec (with try/except
  guard for "no such module: vec0").
- FTS5 sync triggers: mirror existing patterns in migrations.py for knowledge_objects_fts.
- Test style: mirror apps/server/tests/memory/test_migrations.py.

When done, in your final message:
- Print a short summary of files changed (path + one-line description).
- Print the contents of the new test file (so the reviewer can read it without diffing).
- Run `pytest apps/server/tests/memory/test_slice01_schema.py -v` and print the output.
- List any existing tests in test_migrations.py that broke (do NOT delete or modify them — just list).
- Do NOT run git commit, do NOT modify ~/.ntrp/memory.db.
```

---

## 8.5. PM review checklist (run after Codex returns, before saying "done")

Mechanical pass on Codex's diff. Each line gets a ✓ or a callout. If anything fails: do not merge, write a correction prompt for Codex or fix it yourself.

**Files touched (expected set only):**
- [ ] `apps/server/ntrp/memory/store/migrations.py` — `CURRENT_VERSION` bumped to 31, new `_migrate_v31` added, appended to `_MIGRATIONS` list.
- [ ] `apps/server/ntrp/memory/store/base.py` — `memory_items_vec` block added in the existing vec0-creation block.
- [ ] `apps/server/tests/memory/test_slice01_schema.py` — new file with 8 tests per §6.
- [ ] **NO** other files modified. If Codex touched `facts.py` / `observations.py` / `service.py` / `models.py` / etc, REVERT and re-prompt — §7 explicitly forbids it.

**Migration drops (verify against §3):**
- [ ] All 35 base/satellite tables listed appear in the drop block via `DROP TABLE IF EXISTS`.
- [ ] FTS5 shadow shadows (`_data`, `_idx`, `_docsize`, `_config`, `_content`) NOT dropped explicitly — they cascade. If they are, mild lint issue (not a bug); flag but allow.
- [ ] vec0 shadow shadows (`_chunks`, `_info`, `_rowids`, `_vector_chunks00`) NOT dropped explicitly — same as above.
- [ ] `meta` table is NOT dropped.

**Migration creates (verify against §4):**
- [ ] `memory_items` CREATE matches §4.1 character-for-character on column names, constraints, defaults.
- [ ] `memory_item_parents` CREATE matches §4.2 — composite PK `(child_id, parent_id, role)`, `"order"` quoted, FK CASCADE on both.
- [ ] `episode_buffers` CREATE matches §4.3 — partial unique index on `(scope, source_kind) WHERE closed_at IS NULL`.
- [ ] FTS5 virtual table created with the unicode61 tokenizer + remove_diacritics 2.
- [ ] Indexes match §4.1–4.3 list (4 on memory_items, 3 on memory_item_parents, 2 on episode_buffers).

**vec table (base.py):**
- [ ] `memory_items_vec` created with `embedding float[{dim}] distance_metric=cosine`, same try/except guard as the other three.
- [ ] `item_id TEXT PRIMARY KEY`, not `rowid` or `INTEGER`.

**Tests (verify against §6):**
- [ ] All 8 test cases present.
- [ ] Each of the 6 `kind` values appears in the round-trip test.
- [ ] Each of the 5 `role` values appears in the edge round-trip test.
- [ ] FTS test uses MATCH syntax and asserts retrieval.
- [ ] Idempotency test: explicitly re-runs `run_migrations` on a v31 DB and asserts no error.

**Log warning:**
- [ ] `_logger.warning(...)` line in `_migrate_v31` describes what's being dropped and is unrecoverable from this DB.

**No silent regressions:**
- [ ] `pytest apps/server/tests/memory/test_slice01_schema.py -v` → all green.
- [ ] Codex reported which existing `test_migrations.py` tests fail (do not delete or modify them in this slice).
- [ ] `_MIGRATIONS` list still passes `run_migrations` from an empty DB to v31.

If all boxes checked: proceed to tim for the live DB step.

---

## 9. Done criteria (matches goal DoD)

- [ ] `pytest apps/server/tests/memory/test_slice01_schema.py -v` passes (all 8 tests in §6).
- [ ] PM (ntrp) has reviewed the diff against this brief + spec §2.
- [ ] Any regressions in existing `test_migrations.py` are documented (not silently swallowed).
- [ ] tim has executed the live DB backup + migration (or has explicitly chosen to defer until after slice 2).

Goal-level DoD items handled outside this brief (tim runs these manually):

**Step 1 — backup (mandatory before the migration runs):**

```bash
# Server must be stopped first to release the WAL.
# Then:
cp ~/.ntrp/memory.db    ~/.ntrp/memory.db.bak.2026-05-27
cp ~/.ntrp/memory.db-wal ~/.ntrp/memory.db.bak.2026-05-27-wal 2>/dev/null || true
cp ~/.ntrp/memory.db-shm ~/.ntrp/memory.db.bak.2026-05-27-shm 2>/dev/null || true

# Verify size and integrity:
ls -lh ~/.ntrp/memory.db.bak.2026-05-27
sqlite3 ~/.ntrp/memory.db.bak.2026-05-27 "PRAGMA integrity_check;"
sqlite3 ~/.ntrp/memory.db.bak.2026-05-27 "SELECT COUNT(*) FROM facts;"
```

**Step 2 — apply migration to live DB:**

The migration runs automatically on next server start (`run_migrations` is called from `GraphDatabase.init_schema`). To force it now without booting the full server:

```bash
cd /Users/escept1co/src/ntrp/apps/server
.venv/bin/python -c "
import asyncio
from pathlib import Path
import ntrp.database as database
from ntrp.memory.store.base import GraphDatabase

async def main():
    conn = await database.connect(Path.home() / '.ntrp/memory.db', vec=True)
    db = GraphDatabase(conn, 768)  # dim must match the embedding model
    await db.init_schema()
    print('Migration complete. New tables:')
    rows = await conn.execute_fetchall(
        \"SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'memory_item%' OR name LIKE 'episode_buf%') ORDER BY name\"
    )
    for r in rows: print(' ', r[0])
    await conn.close()

asyncio.run(main())
"
```

**Server behavior after slice 1 lands but before slice 2 ships:**
The server will still BOOT — `init_schema` → `run_migrations` runs v31 cleanly, drop+create completes, vec tables come up. Verified by code-reading the startup chain on 2026-05-27 (`runtime/knowledge.py` → `FactMemory.create` → `database.connect` → `GraphDatabase` → `init_schema`; no SELECT against the dropped tables at startup time).

BUT any operation that touches the old tables (chat memory writes via `MemoryService`, knowledge API endpoints, fact-consolidation automations, the UI Memory tab) will throw `OperationalError: no such table` at runtime. This is the explicit "burn, don't backfill" cost — by design. Slice 2 + slice 3 close the gap.

---

## 10. Clarifications (status)

1. **Embedding dimension for `memory_items_vec`** — **RESOLVED.** Use `dim = self.embedding_dim` exactly like the existing three vec tables in `base.py` (lines 405–428). Same `distance_metric=cosine`. Codex must NOT hardcode a number; reuse the constructor attribute.
2. **ID format** — **RESOLVED.** Use `uuid.uuid4().hex` for consistency with the rest of the codebase. Verified 2026-05-27: `apps/server/ntrp/outbox/`, `apps/server/ntrp/context/store.py`, `apps/server/ntrp/core/spawner.py`, and `apps/server/ntrp/server/routers/context.py` all use `uuid4().hex` (often with a domain-prefix like `proj_`, `task-`, `msg-`). No `ulid` anywhere in the codebase. Verdict: do not introduce a new dependency. Memory item IDs are unprefixed `uuid4().hex` strings (32 hex chars). Spec §2 originally said "uuid or ulid"; this resolves the choice to uuid for consistency.
3. **One-time log warning** — **RESOLVED.** Yes. The migration must log `_logger.warning("Migration v31: dropping all pre-v31 memory tables (knowledge_objects, facts, observations, entities, …). This is the memory redesign burn step. Pre-v31 data is unrecoverable from this DB; restore from backup if needed.")` so a user inspecting logs after a server restart sees what happened.
4. **FTS5 / vec0 shadow table drop behavior** — **RESOLVED, empirically.** Verified on 2026-05-27: `DROP TABLE <fts5_vtab>` removes all 5 shadows (`_config`, `_content`, `_data`, `_docsize`, `_idx`) automatically. `DROP TABLE <vec0_vtab>` removes all 4 shadows (`_chunks`, `_info`, `_rowids`, `_vector_chunks00`) automatically. Codex should drop only the virtual table names listed in §3, NOT the shadow names. The v31-idempotency test will catch any leftovers.
