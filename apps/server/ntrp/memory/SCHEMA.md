# Memory Schema (Stage 2 — storage layer)

Persistence only. No pipeline, no admit/extract/reconcile, no retrieval ranking,
no agent-loop wiring. This documents what the schema can *hold*.

Files: `models.py` (dataclasses + enums), `store.py` (`MemoryStore` + DDL),
`migrations.py` (version ladder).

## The locked model

- **Memory is claims only**, plus claim↔claim edges (`evidence`, `supersedes`,
  `contradicts`). Nothing else is a memory participant.
- **Lenses are views, not memory.** A lens is a named, criterion-defined
  projection over claims. It lives in a **separate `lenses` registry table**,
  never in `memory_items`, never as a graph node, never edge-linked. Creating or
  deleting a lens touches zero claims.
- **Subject / coreference is a claim attribute** (`canonical_subject`), not an
  entity row. Reconcile resolves it and merges/supersedes claims sharing a
  subject. Aliases are themselves ordinary claims.
- **Lens membership is a computed projection**, not a stored edge. It is cached
  in `lens_membership_cache` for latency — a cache, not graph truth. Drop the
  whole cache and nothing breaks except projection speed.

## Tables

### `memory_items` — claims only

Every row is a claim: an atomic, self-contained proposition.

| column | meaning |
|---|---|
| `id` TEXT PK | caller-supplied id (uuid by convention) |
| `content` | the claim proposition text |
| `canonical_subject` | the coreference merge key — who/what the claim is about; resolved by reconcile, indexed for subject recall |
| `scope_kind` / `scope_key` | mandatory scope: `user` (key NULL) \| `project` \| `session` (key required). No global implicit scope. |
| `provenance` | ordinal source: `user_authored` > `recorded` > `inferred` > `external` |
| `status` | `active` \| `superseded` \| `archived` — drives never-delete |
| `valid_from` / `invalid_at` | single validity axis (event/validity time). `invalid_at` set = closed interval, NOT a delete |
| `source_refs` | JSON array of typed pointers into the immutable raw layer |
| `corroboration` | count of independent evidence (queryable trust signal) |
| `last_relevant_at` | feeds freshness ("re-check", not a decay curve) |
| `feedback` | `none` \| `confirmed` \| `corrected` |
| `created_at` / `updated_at` | transaction (row-written) time, distinct from `valid_from` |

There is no `kind` column and no `lens_*` columns — `memory_items` is
claims-only. `memory_items_fts` (FTS5, external-content + triggers) indexes
`content` and `canonical_subject` (the subject-alias recall channel). Degrades
gracefully if FTS5 is unavailable (`_has_fts`).

### `lenses` — the view registry (NOT memory)

A lens is a small editable object: a criterion + metadata + a cached rendered
page. It owns no claims.

| column | meaning |
|---|---|
| `id` TEXT PK | uuid |
| `name` | short label ("People", "Regina Volkov", "Bugs") |
| `criterion` | one-sentence natural-language membership test |
| `scope_kind` / `scope_key` | inherits the scoping rule |
| `detail_level` | default render zoom: `gist` \| `structured` \| `dossier` |
| `render_mode` | page layout: `flat` \| `grouped_by_subject` (bucket by `canonical_subject`) |
| `provenance` | `user_authored` \| `induced` (system-proposed) |
| `status` | `active` \| `archived` |
| `page` | cached synthesized markdown projection; `NULL` = dirty / not yet computed |
| `created_at` / `updated_at` | timestamps |

Edits are **in-place `UPDATE`s** (registry, not memory): a lens has no
provenance DAG, no supersede chain. `lenses_fts` (FTS5) indexes
`name`/`criterion`/`page` for lens-name recall. `delete_lens` is a hard `DELETE`
(plus cache invalidation) — disposable, owns no data.

### `lens_membership_cache` — a cache, not graph truth

`(lens_id, claim_id, decision, rationale, scored_at)`, PK on `(lens_id,
claim_id)`. `decision` is `in` \| `out` \| `defer`. Membership is recomputed by
running the criterion over candidate claims via the LLM judge; this table only
caches verdicts. Invalidated by `lens_id` on criterion edit/delete. Carries no
semantic weight — dropping it loses no knowledge.

### `memory_item_parents` — claim↔claim edge DAG

`(child_id, parent_id, role, position, created_at)`, PK on `(child, parent,
role)`, FK to `memory_items` with `ON DELETE CASCADE`, indexed both directions.
Edge roles are **claim→claim only**:

- `evidence` — claim → claim provenance (raw evidence lives inline in
  `source_refs`).
- `supersedes` — successor claim → prior claim (prior interval closed).
- `contradicts` — claim → claim.

There is no `member_of` role. Lenses are never edge participants.

## Trust: transparent signals, never a magic float

Trust is a few separately-stored, queryable signals — `provenance`,
`corroboration`, `feedback`, and freshness derivable from
`valid_from`/`invalid_at` + `last_relevant_at`. No multiplicative confidence
scalar is stored. A retrieval-ordering scalar may exist later but is never a
stored gate; ranking is out of storage scope (Stage 3).

## Never delete

There is no hard-delete path for claims. `invalidate()` moves `status` off
`active` and stamps `invalid_at`; `supersede()` creates the successor, closes the
predecessor (`status=superseded`, `invalid_at` set), and links a `supersedes`
edge. History stays walkable; no successor-chain rewrite, no row removal. (Lens
rows and cache rows are disposable views and *do* hard-delete — they own no
knowledge.)

## Wiring note

`MemoryStore` is the storage substrate. The lens *view layer* (registry CRUD
orchestration, computed-projection engine) lives in the pipeline/lens stages and
builds on the registry + cache methods here; the store stays storage-only and
makes no membership judgments.
