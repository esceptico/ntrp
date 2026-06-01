# Memory UI API Contract — FROZEN (Stage 5)

The single source of truth shared by the backend router (`ntrp/server/routers/memory.py`)
and the desktop client (`apps/desktop/src/api/memoryItems.ts`). Every shape below is
**grounded against the real store/pipeline/lens code** — nothing here is aspirational.

- Store reads: `MemoryStore.{get,query,list_edges,search}` (`ntrp/memory/store.py`) — async, verbatim, no new methods.
- Lens reads/lifecycle: `LensService` (`pipeline/lens.py`), `LensProjector.project` (`pipeline/project.py`).
- Write-back: `LensWriteBack.apply` (`pipeline/writeback.py`).
- Search/retrieve: `MemoryStore.search` (FTS) and `MemoryPipeline.retrieve` (`pipeline/runtime.py`).
- Wiring: `require_knowledge_runtime` (`deps.py:49`) → `KnowledgeRuntime`. Reads use `knowledge.memory`
  (the `MemoryStore`); lens/page/writeback/retrieve use `knowledge.memory_retrieval` (the `MemoryPipeline`,
  exposing `.lens_service`, `.lens_projector`, `.lens_writeback`, `.retrieve(...)`).

## Mount / guard

- Router prefix `/admin/memory`, tag `["memory"]`, mounted in `app.py` via `app.include_router(memory_router)`.
- Every route depends on `require_knowledge_runtime` AND guards readiness:
  `if not knowledge.memory_ready: raise HTTPException(503, "memory pipeline not ready")`.
- The OLD `/admin/memory/*` routers (items PUT/DELETE, stats, today, skills, proposals, directories,
  global-graph, contradiction-undo, slug lenses) are **DELETED**. The desktop client below **replaces**
  `memoryItems.ts` wholesale; it is not a patch. Endpoints not listed here do not exist.

## Scope encoding (shared by every endpoint)

Wire form: `scope_kind ∈ "user" | "project" | "session"` (default `"user"`) + optional `scope_key`.
Server builds `Scope(kind=ScopeKind(scope_kind), key=scope_key)`. `Scope.__post_init__` forces
`key=None` for `user` and **raises** (→ 422) if `project`/`session` is missing a key.

```ts
export type ScopeKind = "user" | "project" | "session";
export interface ScopeParams { scope_kind?: ScopeKind; scope_key?: string }
export interface MemoryScope { kind: ScopeKind; key: string | null }
```

---

## Shared response value objects (serializers)

These mirror `MemoryItem` / `MemoryEdge` / `CoverageAdvisory` exactly. Enums are the real string values.

### `MemoryItem` (claim or lens)

```ts
export type MemoryKind = "claim" | "lens";
export type MemoryStatus = "active" | "superseded" | "archived";
export type MemoryProvenance =
  | "user_authored" | "recorded" | "inferred" | "external" | "induced";
export type MemoryFeedback = "none" | "confirmed" | "corrected";
export type LensDetailLevel = "gist" | "structured" | "dossier";

export interface MemorySourceRef { kind: string; ref: string; captured_at: string }

export interface MemoryItem {
  id: string;
  kind: MemoryKind;
  content: string;                    // claim text; for a lens, the short label
  scope: MemoryScope;
  provenance: MemoryProvenance;
  status: MemoryStatus;
  valid_from: string | null;          // ISO
  invalid_at: string | null;          // ISO; set = closed interval, NOT deleted
  source_refs: MemorySourceRef[];
  corroboration: number;              // independent-evidence count
  last_relevant_at: string | null;    // ISO
  feedback: MemoryFeedback;
  // lens-only (null on claims):
  lens_name: string | null;
  lens_criterion: string | null;
  lens_kind: string | null;           // free-form, e.g. "topic" | "entity" | "user"
  lens_detail_level: LensDetailLevel | null;
  lens_exclusive: boolean;
  created_at: string;                 // ISO
  updated_at: string;                 // ISO
}
```

`lens_page` (the rendered markdown) is **omitted** from this serializer — large; served only by
the page endpoint (#4). There is **no** `confidence`, `title`, `tags`, `usage`, `has_embedding`, or
`artifact_ref` field — those belonged to the deleted model.

Python serializer:
```python
def item_json(m: MemoryItem) -> dict:
    return {
        "id": m.id, "kind": m.kind.value, "content": m.content,
        "scope": {"kind": m.scope.kind.value, "key": m.scope.key},
        "provenance": m.provenance.value, "status": m.status.value,
        "valid_from": m.valid_from, "invalid_at": m.invalid_at,
        "source_refs": [r.to_dict() for r in m.source_refs],
        "corroboration": m.corroboration, "last_relevant_at": m.last_relevant_at,
        "feedback": m.feedback.value,
        "lens_name": m.lens_name, "lens_criterion": m.lens_criterion,
        "lens_kind": m.lens_kind,
        "lens_detail_level": m.lens_detail_level.value if m.lens_detail_level else None,
        "lens_exclusive": m.lens_exclusive,
        "created_at": m.created_at, "updated_at": m.updated_at,
    }
```

### `MemoryEdge`

```ts
export type MemoryEdgeRole = "evidence" | "supersedes" | "contradicts" | "member_of";
export interface MemoryEdge {
  child_id: string;
  parent_id: string;
  role: MemoryEdgeRole;
  position: number;                   // ordering of multi-parent edges (was the old `order`)
  created_at: string;                 // ISO
}
```
Edge semantics: `child --role--> parent`. `supersedes`: successor(child) → predecessor(parent).
`member_of`: claim(child) → lens(parent). `evidence`/`contradicts`: claim → claim.

```python
def edge_json(e: MemoryEdge) -> dict:
    return {"child_id": e.child_id, "parent_id": e.parent_id,
            "role": e.role.value, "position": e.position, "created_at": e.created_at}
```

### `CoverageAdvisory`

```ts
export interface CoverageAdvisory {
  lens_id: string;
  scope_pool: number;                 // active claims in scope
  member_count: number;               // active member_of members
  ratio: number;                      // member_count / scope_pool (0.0 if pool == 0)
  generic: boolean;                   // ratio >= GENERIC_RATIO — ADVISORY ONLY, never a gate
  suggestion: string;                 // "split" | "narrow" prose for the user
}
```

### Rendered page block (write-back spine)

```ts
export interface RenderedClaim {
  claim_id: string;                   // stable anchor — the entire write-back contract
  content: string;
  provenance: MemoryProvenance;
  corroboration: number;
  feedback: MemoryFeedback;
  source_refs: MemorySourceRef[];
}
```

---

## Endpoints

All paths are under `/admin/memory`. Bodies are `application/json`.
Pydantic request bodies live in `ntrp/server/schemas.py`.

### 1 — List claims/lenses
`GET /admin/memory/items`

Query: `scope_kind="user"`, `scope_key?`, `kind="claim"` (`claim|lens`), `status="active"`
(`active|superseded|archived`; **empty `status=` → all statuses**, maps to `store.query(status=None)`),
`valid_at?` (ISO instant), `limit=100`.

Backed by `store.query(kind=, scope=, status=, valid_at=, limit=)` verbatim. `store.query` has **no
offset/total** — pagination is out of scope, the response is `{items, limit}` (the old
`{total, offset}` page is gone).

```ts
export interface MemoryItemsResponse { items: MemoryItem[]; limit: number }
export interface ListMemoryItemsParams extends ScopeParams {
  kind?: MemoryKind;
  status?: MemoryStatus | "";          // "" => all statuses
  valid_at?: string;
  limit?: number;
}
export function listMemoryItems(c: AppConfig, p?: ListMemoryItemsParams): Promise<MemoryItemsResponse>;
```

### 2 — Get one item + provenance edges
`GET /admin/memory/items/{item_id}`

`store.get(item_id)` (404 if None) + `store.list_edges(item_id, direction="from")` (its parents) and
`direction="to"` (its dependents/members). `direction="from"` = edges where the item is the **child**;
`direction="to"` = edges where the item is the **parent**.

```ts
export interface MemoryItemDetail {
  item: MemoryItem;
  parents: MemoryEdge[];               // direction=from: item -> parent
  children: MemoryEdge[];              // direction=to:   child -> item (e.g. lens members)
}
export function getMemoryItem(c: AppConfig, itemId: string): Promise<MemoryItemDetail>;
```

### 3 — List lenses (with coverage advisory)
`GET /admin/memory/lenses`

Query: `scope_kind="user"`, `scope_key?`. Backed by `lens_service.list_lenses(scope)` →
`list[(MemoryItem, CoverageAdvisory)]`. No page synthesis (cheap; page is per-lens via #4).

```ts
export interface LensWithCoverage { lens: MemoryItem; coverage: CoverageAdvisory }
export interface LensesResponse { lenses: LensWithCoverage[] }
export function listMemoryLenses(c: AppConfig, p?: ScopeParams): Promise<LensesResponse>;
```

### 4 — Get a lens page (rendered markdown + block spine + coverage)
`GET /admin/memory/lenses/{lens_id}/page`

Query: `detail?` (`gist|structured|dossier`, default = lens's own / `structured`), `refresh=false`.
Backed by `lens_projector.project(lens_id, detail=, refresh=)` → `ProjectedPage`.

**Cost caveat:** a cache hit (default GET on a `structured`, non-dirty lens with a cached page) is
**0-LLM**. `refresh=true`, a dirty lens, or `gist`/`dossier` invokes the strong LLM (synthesis) and may
`supersede` the lens row to cache the `structured` page. The UI controls cost via `refresh`.

404 mapping: `project()` returns an empty page (`markdown:""`, `blocks:[]`, `synthesized:false`,
`coverage:null`) when the lens is missing/inactive. The router maps **(empty page AND
`store.get(lens_id) is None`) → 404**; otherwise it returns the page as-is (an active lens with no
members legitimately returns a non-empty header markdown with `blocks:[]`).

```ts
export interface ProjectedPage {
  lens_id: string;
  detail: LensDetailLevel;
  markdown: string;                    // contains hidden `<!--claim:ID-->` anchors
  blocks: RenderedClaim[];             // the write-back spine, document order
  synthesized: boolean;                // false = degraded raw-list fallback (still anchored)
  coverage: CoverageAdvisory | null;
}
export interface LensPageParams { detail?: LensDetailLevel; refresh?: boolean }
export function getLensPage(c: AppConfig, lensId: string, p?: LensPageParams): Promise<ProjectedPage>;
```

### 5 — Provenance graph (router-side BFS over edges)
`GET /admin/memory/items/{item_id}/graph`

Query: `direction="both"` (`parents|children|both`), `depth=3` (server clamps ≤ 5),
`roles?` (CSV of `evidence,supersedes,contradicts,member_of`; empty/absent = all roles).

Pure composition of existing reads: seed `{item_id}`, repeatedly `store.list_edges(id,
direction=…, role=…)` filtered to `roles`, `store.get` each touched node, dedup by id, stop at `depth`.
`parents`→`direction="from"`, `children`→`direction="to"`, `both`→union. 404 if `store.get(item_id)` is None.

```ts
export interface MemoryGraph {
  root_id: string;
  nodes: MemoryItem[];
  edges: MemoryEdge[];
  depth: number;
  direction: "parents" | "children" | "both";
}
export interface MemoryGraphParams {
  direction?: "parents" | "children" | "both";
  depth?: number;
  roles?: MemoryEdgeRole[];            // serialized CSV on the wire
}
export function getMemoryGraph(c: AppConfig, itemId: string, p?: MemoryGraphParams): Promise<MemoryGraph>;
```
There is **no** global-graph endpoint (the old `getMemoryGlobalGraph` is gone); build the global view
client-side by seeding BFS from each lens, or omit it.

### 6 — Search
`GET /admin/memory/search`

Query: `q` (required), `scope_kind="user"`, `scope_key?`, `limit=20`, `include_inactive=false`,
`mode="fts"` (`fts|retrieve`).

- `mode=fts` → `store.search(q, limit=, include_inactive=)` (cheap, no LLM, no scope filter inside the
  store — scope params accepted for symmetry but `store.search` is corpus-wide; document this).
  `degraded = not store.has_fts`.
- `mode=retrieve` → `memory_retrieval.retrieve(Retrieval(goal=q, scope=scope, token_budget=…,
  kinds=(Kind.CLAIM,)))` → `RetrievedContext`. LLM/embedding-backed ranked egress (costs an embed +
  goal pass).

```ts
export interface MemorySearchFts {
  mode: "fts";
  items: MemoryItem[];
  degraded: boolean;                   // FTS5 unavailable
}
export interface RankedItem {
  item: MemoryItem;
  order_score: number;                 // transparent scalar; ORDERS, never gates
  rrf: number;
  freshness: number;
  provenance_ord: number;
  corroboration: number;
}
export interface MemorySearchRetrieve {
  mode: "retrieve";
  rendered: string;
  items: RankedItem[];
  degraded: boolean;
  diagnostics: Record<string, unknown>; // variable keys: lens_id, fts_hits, vector_hits, ranked, …
}
export type MemorySearchResponse = MemorySearchFts | MemorySearchRetrieve;
export interface MemorySearchParams extends ScopeParams {
  q: string;
  limit?: number;
  include_inactive?: boolean;
  mode?: "fts" | "retrieve";
}
export function searchMemory(c: AppConfig, p: MemorySearchParams): Promise<MemorySearchResponse>;
```
The `mode` field is echoed in both response variants so the client can discriminate the union.

### 7 — Lens page write-back
`POST /admin/memory/lenses/{lens_id}/writeback`

Body `{ ops: PageEditOp[] }`. Validation: `edit|reject|accept` require `claim_id`;
`add|edit_criterion` require `new_text`. Router maps each to
`PageEditOp(kind=PageEditKind(...), claim_id=, new_text=)` and calls `lens_writeback.apply(lens_id, ops)`
→ `WriteBackResult`. Fixed apply order ACCEPT→EDIT→REJECT→ADD→EDIT_CRITERION; one failed op lands in
`rejected` with a reason, the rest still apply. **Never-delete preserved** (reject appends a negative
example + marks dirty; it never drops an edge or a claim).

404 if `store.get(lens_id)` is None or not an active lens (the router pre-checks for a clean 404;
otherwise `apply` itself would return all-ops-rejected).

```ts
export type PageEditKind = "edit" | "reject" | "accept" | "add" | "edit_criterion";
export interface PageEditOp {
  kind: PageEditKind;
  claim_id?: string;                   // required for edit|reject|accept
  new_text?: string;                   // required for edit (successor) | add (new claim) | edit_criterion
}
export interface WriteBackApplied { kind: PageEditKind; id: string }       // id = new/affected claim or lens id
export interface WriteBackRejected { op: PageEditOp; reason: string }
export interface WriteBackResult {
  applied: WriteBackApplied[];
  rejected: WriteBackRejected[];
  rederive_triggered: boolean;         // true if the page should be re-fetched (with refresh)
}
export function writebackLens(c: AppConfig, lensId: string, ops: PageEditOp[]): Promise<WriteBackResult>;
```
Serializer note: `WriteBackResult.applied` is `list[tuple[PageEditKind, str]]` →
`{kind, id}`; `rejected` is `list[tuple[PageEditOp, str]]` → `{op, reason}`.

### 8 — Lens lifecycle (admin)
Thin wrappers over `LensService`. Each that mints/edits a lens runs a backfill or marks dirty — see cost notes.

```ts
// POST /admin/memory/lenses  → lens_service.create_lens(name, criterion, scope, lens_kind)
//   (runs ONE backfill_lens → LLM/embeds; cost.)
export interface CreateLensBody extends ScopeParams {
  name: string; criterion: string; lens_kind?: string; // default "topic"
}
export function createLens(c: AppConfig, body: CreateLensBody): Promise<{ lens: MemoryItem }>;

// PUT /admin/memory/lenses/{lens_id}/criterion → lens_service.edit_criterion (supersede + mark dirty; no LLM at edit)
export function editLensCriterion(c: AppConfig, lensId: string, criterion: string): Promise<{ lens: MemoryItem }>;

// POST /admin/memory/lenses/{lens_id}/split → lens_service.split_lens (each child backfills; cost.)
export interface SplitChild { name: string; criterion: string }
export interface SplitLensBody { into: SplitChild[]; archive_parent?: boolean } // default true
export function splitLens(c: AppConfig, lensId: string, body: SplitLensBody): Promise<{ children: MemoryItem[] }>;

// POST /admin/memory/lenses/merge → lens_service.merge_lenses (union backfills; cost.)
export interface MergeLensBody extends ScopeParams { lens_ids: string[]; name: string; criterion: string }
export function mergeLenses(c: AppConfig, body: MergeLensBody): Promise<{ lens: MemoryItem }>;

// DELETE /admin/memory/lenses/{lens_id} → lens_service.delete_lens (archives the VIEW only; claims untouched)
//   The sole HTTP "delete"; maps to invalidate(ARCHIVED), honoring never-delete.
export function deleteLens(c: AppConfig, lensId: string): Promise<{ archived: boolean }>;
```
Router maps `split`'s `into: [{name, criterion}]` → `list[tuple[str,str]]` for `split_lens`.

---

## Resolved mismatches (old client → new model)

The old `memoryItems.ts` is built for the **deleted** model. Each removed surface and its disposition:

| Old client surface | Disposition |
|---|---|
| kinds `episode\|observation\|skill\|proposal\|artifact_ref\|entity\|directory` | Gone. Only `claim\|lens`. `entity`/`directory` are now `lens` rows (an entity is a `lens_exclusive` lens). |
| scalar `confidence` | Gone (SCHEMA "never a magic float"). Use `provenance` + `corroboration` + `feedback` + freshness (`valid_from`/`invalid_at`/`last_relevant_at`). |
| `title`, `tags`, `usage`, `artifact_ref`, `has_embedding` | Gone. Not columns on `memory_items`. |
| `MemoryItemsPage{total, offset}` | → `{items, limit}` (store has no offset/total). |
| `MemoryStats`, `MemoryToday` | Gone. No stats/today endpoint. (Counts can be derived from #1 if needed.) |
| `listMemorySkills`, `setMemorySkillEnabled` | Gone. No skills in the new model. |
| `approveMemoryProposal`, `rejectMemoryProposal`, `LensProposal`, `listLensProposals`, `approve/rejectLensProposal`, `generateLens` | Gone. Proposal flow is not in this contract. Lens creation is the explicit `createLens` (#8); induced lenses surface as ordinary lenses with `provenance="induced"` in #3. |
| `MemoryDirectory`, `listMemoryDirectories` | Gone. Directories are lenses (#3). |
| slug-based `MemoryLens{slug, directory, entity_type, path}`, `updateLens(slug, markdown)`, `runLensPass`, `deleteLens(slug)` returning file/dir-removed | Gone. Lenses are addressed by **id**, not slug. Page edits go through structured #7 write-back (claim-id ops), not raw markdown PUT. `deleteLens(id)` → `{archived}`. There is no "run pass"; backfill happens inside create/split/merge and re-validation happens at page read. |
| `getMemoryGlobalGraph`, `MemoryGlobalGraph` | Gone. Only the per-item BFS graph (#5). |
| `undoMemoryContradiction` | Gone. Never-delete means there's no undo verb; contradictions are visible as `contradicts` edges (#2/#5). |
| `updateMemoryItem` (PUT), `deleteMemoryItem` (DELETE) | Gone. Claims are immutable; edits = `edit` write-back (supersede) on a lens page; "delete" = `invalidate`, surfaced only through lens delete (#8) / reject (#7), never raw HTTP DELETE on a claim. |
| `MemoryParentRole` had `step`, `similar_to` | Not in the new `EdgeRole` enum. Roles are exactly `evidence\|supersedes\|contradicts\|member_of`. |
| edge field `order` | renamed `position`. |

## Implementation notes

- No new store/pipeline methods for #1–#7; #5 and the global view are pure composition of existing reads;
  #8 calls existing `LensService` verbs verbatim.
- New Pydantic request bodies (`WriteBackOpsBody`, `CreateLensBody`, `EditCriterionBody`, `SplitLensBody`,
  `MergeLensBody`) go in `ntrp/server/schemas.py` alongside `CompactRequest`.
- Router imports only `fastapi`, `require_knowledge_runtime`, the memory enums/dataclasses, and the
  serializers above — all importable today; the server stays importable.
- TS client uses `apiWithConfig<T>(config, path, init?)` from `apps/desktop/src/api.ts` (signature
  confirmed at `api.ts:308`) and a `queryString(params)` helper for query encoding (roles/CSV joined client-side).
```
