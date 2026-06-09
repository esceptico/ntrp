# Memory v2 — Records + Lenses (minimal)

> Branch: `feat/memory-rebuild`. Builds on the curated-docs rebuild. Approved direction; deliberately minimal — every "smart" piece is deferred (see §Deferred). License: OK to break current memory behavior.

## Why
The curated-docs memory is readable but "castrated": no atomic, searchable, supersedable units; no way to ask "what did I decide / how often do I do X / everything matching <criterion>". Research + Dex's own journey converge on: **free-form records (typed by function, not subject) + hybrid retrieval + background consolidation + saved-query "lenses"** — and explicitly NOT graphs, lifecycle taxonomies, or a lens materialization engine.

## The model (3 layers + saved queries)
1. **Records** — the atomic memory unit. Free-form, self-contained text (survives retrieval alone). The new core.
2. **Docs** (kept) — curated readable scope pages (`user.md`, `projects/<slug>.md`), always injected. The narrative surface.
3. **Transcript** (kept) — raw `session_messages` + FTS + vector. The episodic archive.
- **Lenses** — saved natural-language queries over records, evaluated **on demand** (no materialization, no membership cache).

## Add — RecordStore (`memory/records.py`)
SQLite table `records` in `config.memory_db_path` (the curator's db):
- `id` TEXT PK, `text` TEXT (self-contained), `kind` TEXT (open small set; default `note`; seed `fact|action|preference|note`), `scope_kind`/`scope_key`, `created_at`, `last_confirmed_at`, `superseded_by` TEXT NULL, `pinned` INT, `source_ref` JSON.
- Lexical: `records_fts` (FTS5 over `text`, triggers). Vector: index `text` into the existing `SearchIndex` as `source="record"`, `source_id=id` (embeds internally — mirror the transcript hook in `context/store.py`).
- Methods: `add(...)`, `supersede(old_id, new_id)`, `confirm(id)` (bump `last_confirmed_at`), `update(id, text)`, `delete(id)`, `get(id)`, `search(query, *, scope=None, kinds=None, limit, include_superseded=False)` → hybrid FTS⊕vector via `rrf_merge` (active-only by default), `list(scope, *, pinned_only=False, limit)` for render.
- No bitemporal axis. Freshness = `last_confirmed_at` + recency in ranking; `superseded_by` closes the lineage (never hard-delete on supersede). `pinned` survives decay.

## Rework — the Dreamer (was Curator)
The background pass (per-run schedule + the 600s sweep) now, per session since the watermark:
1. **Extract** candidate records from new turns (one cheap LLM call): self-contained statements + a `kind`.
2. **Reconcile** each candidate: hybrid-retrieve similar existing records → LLM decides **ADD / UPDATE / SUPERSEDE / NOOP** (Mem0 op set). ADD inserts; UPDATE edits + `confirm`; SUPERSEDE sets old `superseded_by` + inserts new; NOOP `confirm`s (reconfirmation).
3. **Keep** the scope-doc update (the readable narrative) — same or adjacent step. Prefer ONE LLM call emitting both the doc update and the record-ops to control cost.
- Reuse the existing watermark (advance-after-success), in-flight de-dupe, sweep loop. The novelty gate still applies (no new durable info → no-op).

## Add — Lenses (saved queries, on demand)
- Table `lenses`: `id`, `name`, `criterion` (NL), `scope` NULL, `created_at`.
- `lens` tool: `create(name, criterion)` | `list` | `view(name)` | `delete(name)`. **view** = hybrid-search records by `criterion` → **optional** cheap-LLM filter on the top-K candidates ONLY when the criterion is non-topical (logic/status/negation/behavior) → render matching records. Topic-ish criteria skip the LLM (semantic query is enough).
- NO materialized pages, NO membership store, NO incremental routing, NO poll machine.

## Tools (repoint)
- `remember(text, kind?)` → `RecordStore.add` (scope structural). (Was: doc append.)
- `forget(query)` → find best-match record → delete/supersede.
- `recall(query)` → hybrid record search (the ad-hoc lens); optionally include transcript hits.
- `lens(...)` → saved queries above.
- Keep `search_transcripts` / `read_transcript`.

## Read path (hot, cheap)
Always inject: scope docs (kept) **+ pinned records** for the active scope (small). Zero-LLM, zero per-turn vector. Everything else is pull (recall/lens/search_transcripts).

## Breaking / migration
- `remember` semantics change (doc-append → record). The `MEMORY_DOCS_SERVICE` gains a record store (or a new `MEMORY_RECORDS_SERVICE`).
- Existing distilled docs stay (narrative). Records start empty + accumulate from new sessions + `remember`. Optional one-time seed of records from existing doc bullets — **deferred / YAGNI**.
- Drop nothing that works (docs, transcript search, sweep stay).

## Deferred (the "what to add later" list — explicitly NOT in v1)
lens membership caching / materialized pages · bitemporal `valid_at/invalid_at` · emergent clustering / reflection trees · success/usage stats on `action` records · retrieval-over-docs at scale · coreference merge-UI (`coref.md`) · cross-scope dedup. Add only when a concrete pain forces it.

## Verify
import smoke · new tests for RecordStore (add/search/supersede/confirm/list, hybrid FTS+vector) + dreamer record-ops (stub LLM) + lens view (cascade) + remember/recall/forget over records · full `uv run pytest tests/`.
