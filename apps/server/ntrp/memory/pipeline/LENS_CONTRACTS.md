# LENS_CONTRACTS — Stage 4 (FROZEN)

Status: frozen contract for Stage-4 lenses. Build to this; do not re-litigate it.
Synthesizes three Stage-4 designs (membership/scale, page projection + write-back,
lifecycle/CRUD) into one mechanism. Builds on the Stage-2 store (frozen) and the Stage-3
pipeline (reconcile, retrieve, consolidate). Verified against the live code on
2026-06-01; every load-bearing line cited below was read, not assumed.

A lens is a **materialized view over the knowledge graph**: a `kind=LENS` row carrying a
name + NL criterion + an editable markdown page + a detail/zoom level. An **entity is a
constrained lens** (`lens_exclusive=True`), not a different object. Stage 3 already mints
and maintains the *entity* axis inline in reconcile. Stage 4 **generalizes that exact
substrate** to topic/user lenses and adds page projection, write-back, lifecycle/CRUD,
scale orchestration, and retrieval-by-lens. **One mechanism, two constraint settings.**

---

## §0 The absolute ban (read first — it governs every section)

Membership is the single decision channel and it is **always an LLM judgment against the
lens criterion** (LLooM multiple-choice scoring). Nowhere — in any decision OR recall
channel — may a word/keyword/term/stopword/prefix set, a regex-for-meaning, or a
similarity/cosine threshold *gate* a keep/drop/membership outcome.

Legal vs. banned, frozen:

- **LEGAL (recall/ranking only):** embeddings (cosine), FTS, RRF fusion, and **length
  floors** that *order* candidates into the judge or *rank* recall output. Precedent in
  the live code: `reconcile._recall_subjects` (cosine "orders candidates into the judge —
  it NEVER gates", reconcile.py:163-164) and `_salient_tokens` ("a length floor that
  routes, never a word/keyword set that decides", reconcile.py:73-76, `len(t) > 2`). A
  cosine score may decide *which* candidates the LLM sees and *in what order*; it may
  never decide whether a claim is `in` or `out`.
- **LEGAL (advisory only):** the **coverage ratio** — a pure `COUNT(member_of) /
  COUNT(scoped active claims)`. Surfaced to the user as a split/narrow suggestion. It
  never auto-acts, never drops a member, never gates membership. A number, not a decision
  (§7).
- **BANNED everywhere a decision is made:** any keyword/stopword/prefix list, any
  regex-as-meaning, any cosine/length cutoff that flips a membership/keep/drop verdict.
  If you think you need a keyword list, you don't — use the LLM.

The mid-band ("close call") does not introduce a numeric gate on the outcome: it only
**routes who re-judges** (cheap → strong → surface-to-user). The band chooses the judge;
the LLM owns the verdict. This is the existing `_escalate` pattern (reconcile.py:456).

---

## §1 Shared shapes (reuse Stage-2 columns + member_of edges; NO store-invariant changes)

The store is **frozen**. No schema migration, no new column, no new edge role, no new
store method. Verified store surface (store.py):

- **Lens row** = `MemoryItem(kind=Kind.LENS)` (models.py:22-25, Kind.LENS exists). Lens
  columns already present (store.py:56-61, create_item maps them at store.py:227-232):
  `lens_name`, `lens_criterion`, `lens_kind` (`"entity" | "topic" | "user"` — schema never
  branches on it), `lens_page`, `lens_detail_level` (`gist | structured | dossier`,
  LensDetailLevel, models.py:67), `lens_exclusive` (INTEGER, entity-only uniqueness flag).
- **Membership** = `member_of` edge `child=claim → parent=lens` (`EdgeRole.MEMBER_OF`,
  models.py:64). Minted by `add_edge` (store.py:241, `INSERT OR IGNORE`). **Cache, not
  truth** — the `lens_criterion` is canonical; the edge set is a re-derivable projection.
- **Mutators (the entire write surface):** `create_item`, `add_edge`, `invalidate`
  (status off active, never deletes — store.py:250-261), `supersede` (successor + close +
  `SUPERSEDES` edge, history walkable — store.py:263-277), `set_feedback`,
  `bump_corroboration`. **There is exactly one edge mutator: `add_edge`.**
- **Reads:** `get`, `query(kind,scope,status,valid_at,limit)`, `list_edges(item_id,
  direction, role)`, `search(query, limit, include_inactive)` (FTS5).

### §1.1 FROZEN CONSTRAINT: there is NO `remove_edge` and NO row delete

Verified: the only edge mutator is `add_edge` (INSERT OR IGNORE, store.py:241); there is
**no `remove_edge`, no `DELETE FROM memory_item_parents`**, and `invalidate`/`supersede`
never remove rows. Every design assumption that membership can be **dropped** by deleting
an edge is **false against this store** and is rejected here.

Consequence, frozen for all of Stage 4: **membership is added, never deleted at the edge
level.** A claim that should leave a lens (criterion narrowed, user rejected it) is handled
by **re-validate-at-read** (§3.3, §6), not by edge removal. Stale `member_of` edges are
tolerated as a harmless dangling cache; reads filter them out by re-judging current
members against the current criterion. Hard pruning would require a deliberate Stage-2
`store.remove_edge` addition — **explicitly future work, out of scope, never smuggled into
this layer.**

### §1.2 New transient shapes — `pipeline/types.py` (no rows, no columns)

```
class MembershipDecision(StrEnum):   IN = "in"; OUT = "out"; DEFER = "defer"

@dataclass
class MembershipVerdict:
    claim_id: str
    lens_id: str
    decision: MembershipDecision
    rationale: str

@dataclass
class RenderedClaim:                  # the structured spine behind the page prose
    claim_id: str                     # stable anchor — the entire write-back contract
    content: str
    provenance: Provenance
    corroboration: int
    feedback: Feedback
    source_refs: list[SourceRef]

@dataclass
class ProjectedPage:
    lens_id: str
    detail: LensDetailLevel
    markdown: str                     # what the user reads/edits
    blocks: list[RenderedClaim]       # served spine; write-back diffs against this
    synthesized: bool                 # False = degraded raw-list fallback
    coverage: CoverageAdvisory | None

class PageEditKind(StrEnum):
    EDIT = "edit"; REJECT = "reject"; ACCEPT = "accept"
    ADD = "add"; EDIT_CRITERION = "edit_criterion"

@dataclass
class PageEditOp:
    kind: PageEditKind
    claim_id: str | None              # required for edit/reject/accept; None for add/criterion
    new_text: str | None              # edit: successor; add: new claim; criterion: new criterion

@dataclass
class WriteBackResult:
    applied: list[tuple[PageEditKind, str]]
    rejected: list[tuple[PageEditOp, str]]   # op + reason
    rederive_triggered: bool

@dataclass
class BackfillReport:
    lens_id: str
    scanned: int
    members_added: int
    capped: bool

@dataclass
class CoverageAdvisory:
    lens_id: str
    scope_pool: int                   # active claims in scope
    member_count: int                 # active member_of members
    ratio: float                      # member_count / scope_pool (0.0 if pool==0)
    generic: bool                     # ratio >= GENERIC_RATIO — ADVISORY ONLY
    suggestion: str                   # "split" | "narrow" prose for the user
```

`RenderedClaim.claim_id` is the load-bearing token: the page is human prose, but every
editable unit carries its stable id, so write-back is structured **by claim id**, never by
reparsing prose position (§3).

---

## §2 The one mechanism — entity = constrained lens, ONE substrate not two

Reconcile **already is** the lens-membership loop for `lens_kind="entity"`:

```
_recall_subjects   (RRF candidate-bounding over name-FTS + content-FTS + embedding cosine)
   → _resolve_subject_llm  (LLM judge against criterion — the decision)
   → _do_add / _do_update  (mint the member_of edge)        reconcile.py:148-151,547-572
```

The only entity-specific narrowings are (a) the criterion is hard-coded
`f"this item is about {subject}"` (reconcile.py:283) and (b) recall filters
`lens_kind == "entity"` (reconcile.py:169,172).

**Generalization (the single move):** lift recall + judge into `LensMembership`,
parameterized by an arbitrary `lens_criterion`. Entity stays the **constrained special
case** (`lens_exclusive=True`, criterion born from a claim, recalled inline during
reconcile, transitive-identity contract). Topic/user lenses are the **unconstrained case**
(`lens_exclusive=False`, criterion authored or induced, backfilled once, no transitivity).

- **Same** `member_of` edge, **same** RRF recall shape, **same** `_escalate` band-routing,
  **same** store calls. No fork, no duplicate loop.
- **Axis split to avoid double-scoring the same edge:** Reconcile keeps owning the entity
  axis inline (it already filters `lens_kind == "entity"`). `LensMembership` owns the
  topic/user axis and filters its candidate recall to `lens_kind in {"topic", "user"}`.
  The two never score the same (claim, lens) pair.

This is why entity and topic lenses are **one mechanism**: `LensMembership` is the
generalization of reconcile's recall+judge with the two narrowings relaxed, and entity
membership remains exactly the path that already ships.

---

## §3 Component interfaces

All components are constructed with the **exact injected dependencies the existing
components use** (store, embed, cheap_llm, strong_llm, cheap_model, strong_model — see
reconcile.py constructor). Frozen constructors below.

### §3.1 Membership scorer — `pipeline/membership.py`

```
class LensMembership:
    def __init__(self, store, cheap_llm, strong_llm, embed, *, cheap_model, strong_model)

    # MODE 1 — incremental (hot, per write). Called from runtime.ingest_unit right after
    # self.reconcile.reconcile(...). Per new claim: RRF-recall top-K candidate topic/user
    # lenses, batch the new claims per lens into one cheap judge call, add_edge on `in`.
    async def score_into_active_lenses(self, claim_ids, scope) -> list[MembershipVerdict]

    # MODE 3 — backfill (cold, once per new lens). Bounded scan of the scoped active claim
    # pool, embedding-rank to the cap (orders the scan, never gates), batched judge,
    # add_edge on `in`.
    async def backfill_lens(self, lens_id) -> BackfillReport

    # The decider. One cheap structured call, N claims vs ONE lens (LLooM column scoring).
    async def score(self, claims, lens) -> list[MembershipVerdict]

    # Generic guard — advisory only (§7). Pure COUNT arithmetic, no LLM.
    async def coverage(self, lens_id, scope) -> CoverageAdvisory
```

Recall (legal): generalize `_recall_subjects` by relaxing the `lens_kind == "entity"`
filter to `lens_kind in {"topic","user"}`. The three channels (alias/name FTS, content
FTS via `_salient_tokens`, embedding cosine over `lens_name`/`lens_page`/`lens_criterion`,
RRF-merged, scope-filtered, capped at `MEMBERSHIP_CANDIDATE_K`) **order candidates into the
judge; they never gate.**

Decision (the ban-compliant core): `score` issues one cheap structured completion =
LLooM multiple-choice. System prompt gives `lens_name` + `lens_criterion` + `lens_page`
gist + numbered items; the model votes `in`/`out`/`defer` per item, judging **only the
criterion as written**, biased to `out` under doubt. `in` → `add_edge(MEMBER_OF)`; `out` →
nothing (absence = OUT; no negative rows); `defer` → escalate that one item to the strong
model via the `_escalate` pattern, then if still `defer` leave it unwritten and surface it
to the user as "needs review." The band only chooses the judge; **no numeric cutoff ever
decides keep/drop.** This is the sole membership channel.

### §3.2 Page projector + write-back — `pipeline/project.py`, `pipeline/writeback.py`

```
class LensProjector:
    def __init__(self, store, embed, cheap_llm, strong_llm, *, cheap_model, strong_model)

    # READ (Mode 2 egress, read-only). Re-validate-at-read: members are re-judged against
    # the CURRENT criterion; only still-`in` claims render. Lazy + cached into lens_page
    # via supersede on the lens row; gist/dossier derived on demand.
    async def project(self, lens_id, *, detail=None, refresh=False) -> ProjectedPage

class LensWriteBack:
    def __init__(self, store, write_seam, membership, projector)
    async def apply(self, lens_id, ops: list[PageEditOp]) -> WriteBackResult
```

**Page format (the editable view).** Markdown synthesized by the LLM (Karpathy-wiki
style) where each rendered claim is a list item carrying a hidden stable anchor:

```markdown
# Regina Volkov
*Lens · entity · criterion: this item is about Regina Volkov; also known as Reggie*

## Profile
- Regina is CEO of ThirdLayer. <!--claim:9f3a… ev:2 conf:user-->
```

The `<!--claim:ID-->` comment is invisible when rendered, survives a markdown round-trip,
and pins each editable line to one claim. Edits diff **per anchored block**, never as a
free-text diff over the whole page.

**Detail levels** (the `lens_detail_level` column):

| level | render | editable |
|---|---|---|
| `gist` | one synthesized paragraph, no anchors | no (zoom-in to edit) |
| `structured` | anchored bullet list, all active members | **yes — the default** |
| `dossier` | structured + `## Evidence` expanding `source_refs` + provenance/corroboration | yes |

Only `structured` is cached into `lens_page` (what reconcile recall + retrieve already
read). Degraded path: if synthesis LLM fails, `project` returns `synthesized=False` with a
raw anchored bullet list — never empty, never a hallucinated page (mirrors retrieve's
render fallback).

### §3.3 Write-back — anchored ops → frozen store calls (the DA-flagged hard part)

The risk is reparsing arbitrary edited prose. Resolution: **never reparse prose for
meaning.** The tool/UI emits discrete `PageEditOp`s keyed by `claim_id`, derived from the
block-to-block anchor diff. Each maps to exactly one existing store primitive:

| page edit | op | store call (frozen API) |
|---|---|---|
| reword a line | `EDIT(claim_id, new_text)` | `supersede(old_id=claim_id, new_item=successor)`; successor unions evidence + re-adds MEMBER_OF (exactly `_do_update`, reconcile.py:556-573) |
| delete a line | `REJECT(claim_id)` | **cannot remove the edge (§1.1).** Record a lens-scoped negative-example correction (below); claim untouched, survives in every other lens |
| confirm a line | `ACCEPT(claim_id)` | `set_feedback(CONFIRMED)` + `bump_corroboration` |
| add a new bullet | `ADD(new_text)` | route through the existing `WriteSeam` as `USER_AUTHORED` (write.py); reconcile re-scores + attaches; no bespoke writer |
| rewrite criterion | `EDIT_CRITERION(new_text)` | `supersede` the lens row with new `lens_criterion`; membership re-derives at next read (§6) |

Free-prose reparse is confined to the `ADD` case and **delegated to WriteSeam** (the one
sanctioned prose→claim translator). Everywhere else the anchor makes the op exact.

**REJECT semantics (frozen, given §1.1).** The store cannot drop the `member_of` edge.
REJECT therefore records a **lens-scoped correction**: a negative-example note appended to
the lens (carried in a dedicated section of `lens_page`, persisted via `supersede` on the
lens row — the same append-only pattern as `_append_alias`, reconcile.py:288-309). Future
`LensMembership.score` reads that note as a negative example in the prompt and the
re-validate-at-read pass renders the claim `out`. **The correction is LLM-read text, never
a keyword filter** (§0). Net effect: the rejected claim stops appearing on the page even
though its edge dangles harmlessly.

**Apply order (fixed):** ACCEPT → EDIT → REJECT → ADD → EDIT_CRITERION last. Each op is
independent against the frozen API; a failed op lands in `rejected` with a reason and the
rest still apply. After apply, re-project with `refresh=True` so the user sees canonical
state.

### §3.4 Lifecycle / CRUD — `pipeline/lens.py :: LensService`

```
class LensService:
    def __init__(self, store, membership, projector, writeback)
    async def create_lens(self, name, criterion, scope, *, lens_kind="topic") -> MemoryItem
    async def list_lenses(self, scope) -> list[tuple[MemoryItem, CoverageAdvisory]]
    async def edit_criterion(self, lens_id, new_criterion) -> MemoryItem
    async def delete_lens(self, lens_id) -> bool
    async def split_lens(self, lens_id, into: list[tuple[str, str]]) -> list[MemoryItem]
    async def merge_lenses(self, lens_ids: list[str], name, criterion) -> MemoryItem
```

- **create** — `create_item(kind=LENS, lens_kind, lens_criterion, lens_exclusive=False,
  provenance=USER_AUTHORED)`, then `membership.backfill_lens` once. Page synthesized lazily
  on first `project`.
- **edit_criterion** — `supersede` the lens row (history walkable, like `_append_alias`).
  Membership **re-derives at read** (§6); no edge mutation at edit time (§1.1).
- **delete** — `invalidate(lens_id, status=ARCHIVED)`. View gone; claims and `member_of`
  edges untouched (the store has no claim-delete path — verified store.py:250). Orphaned
  edges to an archived lens are simply never read (reads filter to active lenses). This is
  the spec's "delete the view, never the claims" invariant, for free.
- **split** — create children (each backfills); optionally `invalidate` the parent. The
  parent's members re-derive per child criterion at read. Triggered only by the coverage
  advisory (§7), never automatically.
- **merge** — create the union lens, `backfill_lens` it (so the union re-derives its
  members against the merged criterion), then `invalidate` the inputs. **DO NOT** try to
  re-point edges with `_inherit_members` — see §3.5.

### §3.5 FROZEN CORRECTION: `_inherit_members` is claim→lens, not lens→members

Verified (consolidate.py:331-334): `_inherit_members(from_id, to_id)` lists
`list_edges(from_id, direction="from", role=MEMBER_OF)` — i.e. the edges where `from_id`
is the **child** — and re-adds them with the new **child** `to_id`. It migrates **one
claim's lens memberships to a successor claim**. It does **not** migrate a lens's member
set to a successor lens.

The Stage-4 designs that proposed reusing `_inherit_members` "verbatim" to re-point a
lens's members during entity-merge are **wrong** and that approach is rejected. Lens merge
re-derives membership via `backfill_lens` against the merged criterion (§3.4), which is
both correct and consistent with §1.1 (add-only, re-validate-at-read). `_inherit_members`
is reused **only** for its actual purpose — claim supersession in consolidate — unchanged.

### §3.6 Scale orchestration — three modes, never O(corpus)

| Mode | When | Where | Bound |
|---|---|---|---|
| 1 incremental | every write | `runtime.ingest_unit`, after reconcile | O(new_claims × K), K=`MEMBERSHIP_CANDIDATE_K` recalled lenses |
| 2 read/render | every lens view + retrieval | `LensProjector.project`, `retrieve` | cache hit = 0 LLM; miss/dirty = 1 synth |
| 3 backfill | once per new lens | `LensService.create_lens` | one bounded scan, `BACKFILL_SCAN_CAP`, batched `MEMBERSHIP_BATCH` |

The single expensive pass happens once per **new lens**, never per node, never per query.
Mode 1 maintains membership thereafter incrementally.

### §3.7 Retrieval-by-lens — Mode 2 egress (read-only)

`Retrieval.lens_hint` already exists (types.py:163) and `kinds` admits `Kind.LENS`. The
read path (`Retriever`, constructed `(store, embed, cheap_llm, model=...)` — no strong_llm,
verified runtime.py:119) gains lens expansion:

- When a goal names a lens (or chat scope *is* an entity/project lens), resolve it and
  inject its cached `lens_page` directly as the scoped bundle — the cheapest recall path,
  the page is pre-compressed and query-shaped.
- Fallback / blend: if the page is stale or the goal is narrower, fall back to the
  existing hybrid path but **pre-filter the candidate pool to the lens's active
  `member_of` members**, then rank with the existing `order_score` (ranking orders, never
  gates). Re-validation of stale members against the criterion is the projector's job;
  retrieve consumes the validated page.

Retrieve never scores membership, never writes, never calls the strong model — it
consumes what membership/projector produced. (Consistent with retrieve.py:4.)

### §3.8 The define-lens tool — `tools/memory.py` (extend, do not add a top-level surface)

`tools/memory.py` already hosts `recall`/`remember` via the `tool(...)` + `ToolAction`
pattern (tools/memory.py:144-176, function.py:58). Add **one** `lens` tool with
sub-actions, not seven top-level tools (per "agent specializations aren't tools / keep the
surface small"):

```
lens(action="define" | "show" | "edit" | "delete" | "split" | "merge" | "list", ...)
```

- `define` → `LensService.create_lens` (name + criterion).
- `show` → `LensProjector.project` (returns the markdown page).
- `edit` → `edit_criterion` (or a structured page edit → `LensWriteBack.apply`).
- `list` → `LensService.list_lenses` (each row carries its `CoverageAdvisory`).
- `split`/`merge` → `LensService` (only invoked by the user, typically off an advisory).

Everyday recall stays the existing `recall` tool, which transparently uses `lens_hint`.
The `lens` service is exposed in `KnowledgeRuntime.tool_services()` next to the memory
read/write services and registered only inside the `memory_ready` branch
(knowledge.py:87-98,140) — purely additive, server boots unchanged with memory off.

---

## §4 Prompt I/O (frozen shapes; structured-output models live in `prompts_reconcile.py`)

Membership and the entity-resolution prompt share a home (same loop, same file —
`prompts_reconcile.py`). Page synthesis/write-back prompts live in `prompts_project.py`.

### §4.1 Membership judge (LLooM multiple-choice) — cheap model, batched N-vs-1

System: judge each numbered item **only against the criterion as written**; bias `out`
under doubt; `defer` only when genuinely close. Negative-example corrections (§3.3) are
appended as context, read as examples, never as filters.

Input (one lens, N claims):
```
LENS: name=<lens_name> kind=<lens_kind>
CRITERION: <lens_criterion>
PAGE_GIST: <lens_page[:N]>
NEGATIVE_EXAMPLES: <prior user rejections, if any>
ITEMS:
  [0] <claim content>
  [1] <claim content>
  ...
```
Output (`MembershipBatch`): `{votes: [{item_index, decision: in|out|defer, rationale}]}`.
Out-of-range index → ignore the vote, default `out` (matches `_validate_rows`).
Parse failure / empty output → treat the batch as all-`out`; lint re-scores later.

### §4.2 Escalation — strong model, single item

Same `_escalate` shape as reconcile.py:456: re-judge one `defer` item; if still `defer`,
leave unwritten + surface to the user. No numeric cutoff decides; the band routes.

### §4.3 Page synthesis — strong model, lazy

Input: active (re-validated) members as numbered blocks `{claim_id, content,
provenance, corroboration, feedback, source_refs}` + lens name/criterion + target detail
level. Output: markdown where **every claim_id anchor is echoed verbatim** (same discipline
as retrieve compression — the model selects/re-renders, anchors are echoed, never
invented). Page is synthesized from **claims only, never from another page** (recursion
guard).

### §4.4 Page write-back ADD — via WriteSeam, no new parser

`ADD` text is routed unchanged through `WriteSeam` (the existing prose→claim path).
EDIT/REJECT/ACCEPT need **no LLM** (pure id-keyed store calls). EDIT_CRITERION supersedes
the lens row (no LLM). So the only model spend on write-back is per-`ADD` reconcile.

---

## §5 Per-operation LLM-call budget (frozen)

| Operation | Cheap | Strong | Store | Frequency |
|---|---|---|---|---|
| Incremental (per ingest) | ≤ K batched judge calls (one per recalled lens) | ≤ #defer items | 1 query(LENS) + ≤3 search + add_edge/`in` | every write |
| Project — cache hit | 0 | 0 | list_edges + N get | every view |
| Project — miss/dirty | 0 | 1 synth | + 1 supersede (cache) | on member/criterion change |
| Backfill (per new lens) | ⌈min(pool, cap)/batch⌉ (≤ ~25) | 0 | 1 query + add_edge/`in` | once per lens |
| Write-back EDIT/REJECT/ACCEPT | 0 | 0 | supersede / set_feedback / lens-supersede | per edit |
| Write-back ADD | 1 cheap reconcile per added claim | rare escalation | via WriteSeam | per added line |
| EDIT_CRITERION | 0 at edit; re-derive amortized at next read | — | 1 supersede(lens) | on criterion edit |
| Coverage (advisory) | 0 | 0 | 2 COUNT queries | per sweep / list |
| Retrieval via lens page | 0 (page cached) | 0 | list_edges + gets | per recall |

Constants beside `SUBJECT_RECALL_K`/`RRF_K` in `reconcile.py` (or a shared constants
home): `MEMBERSHIP_CANDIDATE_K = 8`, `BACKFILL_SCAN_CAP = 500`, `MEMBERSHIP_BATCH = 20`,
`GENERIC_RATIO = 0.5`. The expensive pass is once per new lens — never per node, never per
query.

---

## §6 Re-validate-at-read — the criterion-edit resolution (frozen, given §1.1)

A criterion edit can turn an existing `in` member `out`, but the store **cannot delete the
edge**. Resolution, frozen:

1. `edit_criterion` → `supersede` the lens row with the new criterion; mark it dirty (a
   `meta` watermark key, mirroring consolidate's existing watermark pattern — no schema
   change).
2. Next `project` (or retrieval) for that lens **re-scores its current `member_of`
   members against the new criterion** via `LensMembership.score` and renders/returns only
   those still `in`. Now-`out` edges are tolerated as harmless dangling cache: the page
   never shows them, retrieval filters by re-validated membership.
3. New `in` matches outside the old member set are picked up by the next backfill/sweep or
   incrementally as new claims arrive.

This is the **only** place "frozen store" and "criterion edits re-derive membership" are in
tension. It is surfaced and resolved here, not silently papered over. Hard pruning is
deferred to a future Stage-2 `store.remove_edge` (§1.1).

---

## §7 The generic guard — advisory coverage ratio (never a decision, never a word list)

`coverage(lens_id, scope)` = `member_count / scope_pool` where both are `COUNT`s from
`list_edges` / `query` (no LLM, no lexical anything). `generic = ratio >= GENERIC_RATIO`
(0.5, the LLooM line). When generic, surface `CoverageAdvisory{generic=True,
suggestion="split"|"narrow"}` to the user via the `lens` tool's `list`/`show` output and
the consolidate lint sweep. It:

- **never** a word/keyword/stopword/prefix list,
- **never** an auto-split, auto-narrow, or silent member drop,
- **never** a gate on any membership outcome (membership is always the §3.1 LLM judgment).

`scope_pool == 0` → `ratio = 0.0`, `generic = False`, no banner (no divide-by-zero). A
near-duplicate variant (two lenses with heavily overlapping member sets) may additionally
ask the LLM whether the two criteria are synonymous and suggest `merge` — overlap is the
recall signal, the LLM makes the call, the user decides. A count and an LLM check, never a
keyword heuristic.

---

## §8 File layout under `ntrp/memory/pipeline/` (and the two extension points)

New files:
- `pipeline/membership.py` — `LensMembership` (recall+judge generalization, modes 1+3, coverage).
- `pipeline/project.py` — `LensProjector` (page synthesis, re-validate-at-read, detail levels).
- `pipeline/writeback.py` — `LensWriteBack` (anchored ops → frozen store calls).
- `pipeline/lens.py` — `LensService` (create/list/edit/delete/split/merge).
- `pipeline/prompts_project.py` — page synthesis + (no-op) anchor-echo prompts.

Edited files:
- `pipeline/types.py` — the §1.2 transient shapes.
- `pipeline/prompts_reconcile.py` — `MembershipBatch`/membership rubric (shares the loop's home).
- `pipeline/reconcile.py` — relax `_recall_subjects` lens-kind filter so the generalized
  recall is reusable (or factor the recall helper out; keep entity behavior identical).
- `pipeline/runtime.py` — construct `LensMembership`/`LensProjector`/`LensWriteBack`/
  `LensService` beside the existing components (runtime.py:85-126); one
  `score_into_active_lenses(...)` call line in `ingest_unit` after `reconcile.reconcile`
  (runtime.py:151).
- `pipeline/retrieve.py` — implement lens expansion (Mode-2 egress, read-only; §3.7).
- `pipeline/consolidate.py` — coverage/near-dup advisory + dirty re-validate ride the
  existing per-scope sweep. **Keep `ConsolidateLint` claim-only** (its docstring promises
  it never touches lenses, consolidate.py:5) — put lens maintenance in a sibling that the
  same loop drives. `_inherit_members` stays untouched and is **not** reused for lens
  merge (§3.5).
- `tools/memory.py` — add the single `lens` tool (§3.8).
- `server/runtime/knowledge.py` — expose the lens service in `tool_services()` and
  register the tool inside the `memory_ready` branch.
- `services/chat.py` — `_retrieve_memory_context` already builds `Retrieval`; populate
  `lens_hint` when chat is scoped to a lens (chat.py:382-437).

Reused unchanged (frozen): `store.py` (no `remove_edge`, verified), `models.py` (lens
columns + MEMBER_OF), `reconcile.py` entity path (the constrained special case + RRF
recall prototype), `write.py` WriteSeam (the ADD path), `tests/conftest.py` fakes.

### §8.1 As-built (integration phase, 2026-06-01) — two deviations from §8, both additive

The retrieval-by-lens egress (§3.7) and the `lens` tool (§3.8) were built as a small
standalone package `ntrp/memory/lens/` instead of in-place edits to `pipeline/retrieve.py`
and `tools/memory.py`. The behavior is identical to §8; only the file home differs, and the
seam is wired without forking the pipeline:

- `ntrp/memory/lens/expand.py` — `LensExpander(store, embed)` (read-only, no LLM, no strong
  model — §11.3). `runtime.MemoryPipeline` constructs it and passes it to `Retriever` as the
  additive `lens_expander` kwarg. `Retriever.retrieve` calls it only when `req.lens_hint` is
  set: cached `lens_page` present → inject verbatim (0 LLM); else pre-filter the candidate
  pool to the lens's active `member_of` members and rank with the existing `order_score`
  (orders, never gates). `lens_hint=None` → unconstrained recall, unchanged. So `retrieve.py`
  *was* edited (the expander hook), but the resolution logic lives in `lens/expand.py`.
- `ntrp/memory/lens/tool.py` — the single `lens` tool (`define|show|edit|delete|split|
  merge|list`). Registered in the `_memory` integration (`integrations/core.py`) gated by
  `permissions={MEMORY_LENS_SERVICE}`; the registry hides it unless that capability is in
  `tool_services()`. `tools/memory.py` is therefore *unchanged* — the §3.8 "extend, don't add
  a top-level surface" intent holds (one `lens` tool, not seven), just in a sibling module.
- `server/runtime/knowledge.py` — `tool_services()` exposes `MEMORY_LENS_SERVICE` only when
  `self.lens_service` is set, which `_init_memory` does only inside the `memory_ready` branch
  (the §10 boot invariant: server boots unchanged with memory off).
- `services/chat.py` — `_retrieve_memory_context` populates `lens_hint` STRUCTURALLY from the
  project name (project-scoped chats); the expander resolves it by id/exact-name/FTS and
  returns None when no such lens exists. Never sniffed from prose (§0).
- `pipeline/reconcile.py` was NOT edited: `LensMembership` carries its own generalized recall
  (relaxed lens-kind filter) and a local copy of the `_salient_tokens` length floor, so the
  entity path is byte-for-byte unchanged. De-duplicating into a shared recall helper is
  deferred polish, not load-bearing (the axis split already prevents double-scoring).
- `pipeline/consolidate.py` was NOT edited: the §7 coverage / near-dup advisory and §6 dirty
  re-validate sweep are surfaced on demand (the `lens` tool's `list`/`show`, and `project`'s
  re-validate-at-read). Riding them on the background `ConsolidateLint` loop is deferred
  background polish; the core create/score/project/write-back/retrieve flows run end-to-end
  without it. `_inherit_members` remains untouched and unused for lens merge (§3.5).

Verified end-to-end on in-memory SQLite with the conftest fakes: create_lens → backfill (LLM
judge mints member edges) → Mode-1 incremental scoring on ingest → project (re-validate +
synth, cached structured page; degraded raw-list fallback on anchor-drop) → write-back ACCEPT
→ retrieve via `lens_hint` (page-inject AND member-constrained fallback both exercised). Tool
permission gating verified hidden-off / shown-ready. Full server tree imports; 951 tests pass.

---

## §9 Failure modes (frozen)

1. **No edge delete (§1.1).** Criterion narrowing / REJECT can never remove an edge;
   handled by re-validate-at-read (§6) and lens-scoped corrections (§3.3). Stale edges
   dangle harmlessly; reads filter by re-judged membership.
2. **`_inherit_members` misuse (§3.5).** Banned for lens merge; lens merge re-derives via
   backfill. The helper is claim→lens only.
3. **Out-of-range / hallucinated vote index.** Ignore the vote, default `out` (matches
   `_validate_rows`).
4. **Parse failure / empty structured output.** Treat the batch all-`out`; lint re-scores.
5. **Synthesis LLM failure.** `project` returns `synthesized=False` with a raw anchored
   member list — never blank, never hallucinated.
6. **Stale anchor (claim superseded between serve and edit).** EDIT/ACCEPT no-op on
   non-active rows (store.py:259,282) → op lands in `rejected` with "claim moved; re-open
   the page." No silent write to a dead row.
7. **Mid-band `defer`.** Escalate to strong; if still `defer`, surface to the user — never
   silently kept or dropped (§0).
8. **Embedder/FTS down.** Recall degrades to the surviving channels; the LLM still decides
   over the surfaced candidates. Degraded recall, never a degraded decision.
9. **Duplicate edge.** `add_edge` is INSERT OR IGNORE → no-op.
10. **Generic criterion.** Only inflates `coverage.ratio` (advisory). Cannot corrupt
    anything; the user narrows.
11. **Delete safety.** `delete_lens` physically cannot remove a claim (no store
    claim-delete path). Worst case: orphan `member_of` edges to an archived lens, which
    reads skip.
12. **Recall miss = fragmentation.** Membership quality is bounded by recall, not the
    prompt (same bound reconcile already lives with). Mitigation: recall over name +
    criterion (accrued aliases) + page summaries + embeddings; near-duplicate advisory (§7)
    surfaces residue for merge. Invest in recall; surface dupes — never a keyword backstop.
13. **Entity vs topic double-membership.** Expected and fine (`lens_exclusive=False`); the
    axis split (§2) prevents double-scoring the same edge.

---

## §10 Server-bootable + offline tests (frozen)

Purely additive: new components constructed like the existing ones, no schema/store/
invariant change, so `knowledge.py`/`chat.py` are unaffected and the server boots unchanged
with memory off (every new component is built only inside the `memory_ready` branch).

Tests under `tests/memory/pipeline/`, driving `FakeCompletionClient` (queue membership
verdicts + synthesis payloads; assert `.calls`) and `FakeEmbedder` (deterministic recall
ordering) from `tests/conftest.py`, in-memory SQLite only — **never open
`~/.ntrp/memory.db`, never touch the network.**

- `test_membership.py` — incremental writes edges only on `in`; **candidate-K bound**
  asserted via `len(fake_llm.calls) ≤ touched lenses` (proves no O(corpus) blowup);
  `defer` escalates to strong; **ban guard:** membership flips with the LLM verdict only —
  identical embeddings/length, opposite verdicts, both honored; degraded embedder → decision
  still made from FTS candidates.
- `test_lens_lifecycle.py` — create→backfill→edit_criterion re-derive→delete-leaves-claims;
  **§3.5 guard:** lens merge re-derives via backfill, `_inherit_members` not called for it.
- `test_lens_coverage.py` — ratio crosses `GENERIC_RATIO` → advisory only; **assert no
  edges mutated** and no member dropped.
- `test_lens_project_writeback.py` — anchored EDIT→supersede, REJECT→correction (edge
  persists, claim survives, page hides it), ADD→WriteSeam, ACCEPT→feedback; synthesis
  failure → `synthesized=False` raw list; **§6 test:** after criterion edit, `project`
  returns only still-`in` members though stale edges persist.
- `test_lens_retrieval.py` — `lens_hint` injects the cached page; member-constrained
  fallback ranks but never gates.

The delete-leaves-claims, coverage-is-advisory, §6 re-validate, and ban-guard tests are the
ones that directly assert the store invariant (§1.1) and the absolute ban (§0).

---

## §11 Resolved contradictions (frozen decisions)

1. **Edge deletion.** The store has no `remove_edge` (verified store.py). Designs assuming
   "drop the edge" on criterion edit / reject are **rejected**. Frozen: add-only +
   re-validate-at-read (§1.1, §3.3, §6). Hard pruning is future Stage-2 work.
2. **`_inherit_members` for lens merge.** Designs proposing it are **wrong** — it is
   claim→lens (`direction="from"`, consolidate.py:331). Frozen: lens merge re-derives via
   `backfill_lens` (§3.4, §3.5).
3. **Retriever has no strong model.** `Retriever` is `(store, embed, cheap_llm, model)`
   (runtime.py:119). Frozen: lens expansion in retrieve is read-only, no strong-model
   spend; synthesis/judgment live in projector/membership (§3.7).
4. **`lens_hint` already exists** (types.py:163) — not new; retrieve must implement its
   expansion, which is currently only documented (retrieve.py:4).
5. **Cluster-induction (LLooM Distill→Cluster→Synthesize proposing *new* lenses) is OUT OF
   SCOPE.** Stage 4 covers user-authored + entity lenses and the membership/scale/page
   mechanism for all kinds — not auto-induction. Induction is a later stage.
6. **Coverage band** default `0.5`, advisory knob, never a gate (§7).
7. **Backfill bounds** `BACKFILL_SCAN_CAP = 500`, `MEMBERSHIP_BATCH = 20` (§5).
