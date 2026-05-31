# Memory Schema (Stage 2 — storage layer)

Persistence only. No pipeline, no admit/extract/reconcile, no retrieval ranking,
no agent-loop wiring. This documents what the schema can *hold* and the forks
resolved while laying the foundation.

Files: `models.py` (dataclasses + enums), `store.py` (`MemoryStore` + DDL),
`migrations.py` (version ladder).

## Tables

### `memory_items` — the single object table

Every durable knowledge unit is a row, discriminated by `kind`:

- `claim` — atomic, self-contained proposition (coreference resolved inline).
  One claim = one fact.
- `lens` — editable object holding a `criterion` + metadata + a rendered `page`.
  Membership is *derived* from the criterion, never stored as authoritative rows.

Columns:

| column | meaning |
|---|---|
| `id` TEXT PK | caller-supplied id (uuid by convention) |
| `kind` | `claim` \| `lens` |
| `content` | claim proposition text; for a lens, a short label |
| `scope_kind` / `scope_key` | mandatory scope: `user` (key NULL) \| `project` \| `session` (key required). No global implicit scope. |
| `provenance` | ordinal source: `user_authored` > `recorded` > `inferred` > `external`; `induced` for system-proposed lenses |
| `status` | `active` \| `superseded` \| `archived` — drives never-delete |
| `valid_from` / `invalid_at` | single validity axis (event/validity time). `invalid_at` set = closed interval, NOT a delete |
| `source_refs` | JSON array of typed pointers into the immutable raw layer |
| `corroboration` | count of independent evidence (queryable trust signal) |
| `last_relevant_at` | feeds freshness ("re-check", not a decay curve) |
| `feedback` | `none` \| `confirmed` \| `corrected` |
| `lens_*` | lens-only fields (NULL for claims): `lens_name`, `lens_criterion`, `lens_kind`, `lens_page`, `lens_detail_level`, `lens_exclusive` |
| `created_at` / `updated_at` | transaction (row-written) time, distinct from `valid_from` |

`memory_items_fts` (FTS5, external-content + triggers) indexes `content`,
`lens_name`, `lens_criterion`, `lens_page`. Degrades gracefully if FTS5 is
unavailable (`_has_fts`).

### `memory_item_parents` — role-typed edge DAG

`(child_id, parent_id, role, position, created_at)`, PK on `(child, parent,
role)`, FK to `memory_items` with `ON DELETE CASCADE`, indexed both directions.
Walkable for provenance. Named edge roles (open set, these are the minimum):

- `evidence` — claim → claim provenance (in-schema parent only; raw evidence
  lives inline in `source_refs`, see F5).
- `supersedes` — successor claim → prior claim (prior interval closed).
- `contradicts` — claim → claim.
- `member_of` — item → lens (derived membership; cache, not source of truth).

## Trust: transparent signals, never a magic float

v1's `compute_confidence` multiplicative float (provenance × evidence × decay ×
usage, ~8 tuned constants, collapsed to 3 UI buckets) is **dropped**. Trust is a
few separately-stored, queryable signals — `provenance`, `corroboration`,
`feedback`, and freshness derivable from `valid_from`/`invalid_at` +
`last_relevant_at`. A retrieval-ordering scalar may exist later but is never a
stored gate; ranking is out of storage scope (Stage 3).

## Never delete

There is no hard-delete path in the store. `invalidate()` moves `status` off
`active` and stamps `invalid_at`; `supersede()` creates the successor, closes
the predecessor (`status=superseded`, `invalid_at` set), and links a
`supersedes` edge. History stays walkable; no successor-chain rewrite, no row
removal. (The FK CASCADE only fires if a parent row were ever deleted, which the
store never does — it exists for integrity, not as a delete path.)

## Forks resolved (confirm if you disagree)

- **F1 — lens row vs separate table → polymorphic single table.** Faithful to
  the vision's "one object table"; lens-only columns are nullable. The schema
  does not branch on `lens_kind` (informational only). Avoids a join on every
  query. *Confirm: acceptable to carry nullable lens columns on claim rows.*

- **F2 — entity-lens identity → `lens_exclusive` flag + `member_of` edges.**
  Exclusivity (one claim-subject → one entity) is a flag on the lens row;
  enforcement and transitive merge (A≡B,B≡C⇒A≡C) are pipeline (Stage 3), not a
  storage constraint. No separate alias/equivalence table yet; the **alias
  index** is served by the existing FTS5 over `lens_name` + `lens_criterion` +
  `lens_page` (recall over names and page summaries). *Confirm: deferring the
  merge/equivalence edge + dedicated alias table to Stage 3 is acceptable.*

- **F3 — membership → pure-derived via `member_of` edges, no materialized
  cache.** `member_of` rows are the (optional) cache the pipeline writes;
  `criterion` stays canonical. No separate cache table with a refresh contract
  in Stage 2 — refresh/invalidation is pipeline logic. *Confirm: a first-class
  membership-cache table is not needed at the storage layer yet.*

- **F4 — validity axis → single-axis, confirmed.** `status` + `valid_from` /
  `invalid_at` for validity time, plus a distinct `created_at` transaction
  timestamp. NOT full bi-temporal (no walkable transaction-time history). Costly
  to retrofit — raise now if walkable transaction history is wanted.

- **F5 — `source_refs` → inline typed JSON pointers on the claim.** Raw is not a
  memory node, so the evidence endpoint is an external pointer
  (`{kind, ref, captured_at}`), not a stub row. The `evidence` edge role is
  reserved for claim→claim provenance where the parent is itself in-schema.
  *Confirm: inline JSON source_refs (not evidence-edge rows to a raw-pointer
  table) is the intended shape.*

## Wiring note

`MemoryStore` is not yet added to `server/stores.py`. It follows the standard
shape (injected `conn`, `async init_schema()`); add it to `Stores.connect` over
`config.memory_db_path` when Stage 3 wires the pipeline.
