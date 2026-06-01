# Memory Pipeline — Stage 3 CONTRACTS (frozen)

The integration backbone for the consolidation pipeline. Every builder follows this
document. It defines the shared data shapes, each component's async interface, the
prompt I/O schemas, how each component uses the Stage-2 store, the per-exchange LLM-call
budget, the file layout, and the component boundaries. Where the six component designs
disagreed, the resolution is stated inline under **RESOLUTION**.

Grounding (read these, do not re-derive):
- `/Users/escept1co/vault/Memory Consolidation/Memory — vision (new spec).md`
- `/Users/escept1co/vault/Memory Consolidation/Lens — spec.md`
- `/Users/escept1co/vault/Memory Consolidation/_grounding (validated).md`
- Stage-2 store (FROZEN — invariants must not change):
  - `/Users/escept1co/src/ntrp/apps/server/ntrp/memory/store.py`
  - `/Users/escept1co/src/ntrp/apps/server/ntrp/memory/models.py`
  - `/Users/escept1co/src/ntrp/apps/server/ntrp/memory/SCHEMA.md`

---

## 0. Pipeline shape & principles

```
Capture → Admit → Extract → Reconcile → (Consolidate/Lint, background) → Retrieve
                                                  ↑
                              remember() tool enters Admit→Reconcile via write seam
```

Non-negotiable principles inherited from the vision (every component obeys them):

1. **One decision per stage.** Capture bounds; Admit gates; Extract atomizes+grounds;
   Reconcile resolves+writes; Consolidate/Lint forgets+dedups; Retrieve reads+compresses.
   No stage reaches into another's decision.
2. **Signals route, the LLM decides** (vision principle #2). Cheap heuristics (FTS bands,
   embedding margins, length floors) may *route* who/what the model judges. They may
   **never gate** a keep/drop/merge outcome by threshold. The only deterministic gates
   permitted are categorical facts (scope, validity/status, empty-content) and the
   correction short-circuit.
3. **Raw is immutable and is never memory** (vision principle #3). Only Capture reads raw.
   Claims carry `source_refs` pointing back into raw; re-grounding is always possible.
4. **Scope is mandatory** (vision principle #6). No global implicit scope; no cross-scope
   contamination. `Scope` is assigned by Capture/remember from structural metadata,
   never inferred by an LLM.
5. **Never delete.** Removal is `invalidate()`/`supersede()` only. Consolidated/inferred
   conclusions never out-rank direct evidence; user-confirmed claims are never
   merged/invalidated by background lint.
6. **The store is frozen.** No schema change, no new column, no new edge role, no new
   table. The pipeline lives entirely above the store's public API. The one watermark
   datum the pipeline persists lives in the store's existing `meta(key, value)` table.

---

## 1. Stage-2 store: the consumed surface (FROZEN)

These are the only store entry points the pipeline uses. Builders treat them as the
contract; they do not add to or alter `store.py`/`models.py`/`SCHEMA.md`.

### 1.1 Reads
- `store.get(item_id) -> MemoryItem | None`
- `store.query(*, scope, kind, status, valid_at, limit, …) -> list[MemoryItem]`
  — scope- and validity-filtered; the only scope-aware recall primitive.
- `store.search(query_text, *, limit, include_inactive=False) -> list[MemoryItem]`
  — FTS5 over `content, lens_name, lens_criterion, lens_page`. **Active-only by default;
  NOT scope-filtered.** Returns `[]` when FTS5 is unavailable.
- `store.list_edges(item_id, *, direction, role) -> list[Edge]`
- `store.has_fts -> bool` — **NEW public read-only property** over the existing private
  `_has_fts`. Adds no state, no schema, no invariant change. It exists so a consumer can
  distinguish "FTS ran and matched nothing" from "FTS unavailable." (Resolves the
  Retrieve empty-vs-degraded ambiguity at the consumer, not the store.) This is the only
  permitted addition to the store surface, and it is read-only.

### 1.2 Writes (Reconcile, Consolidate/Lint, and the write seam only)
- `store.create_item(item) -> id` — ADD a claim, or mint a NEW entity-lens.
- `store.supersede(old_id, new_item) -> id` — closes predecessor
  (`status=superseded`, sets `invalid_at`), creates successor, links a `SUPERSEDES`
  edge, in one transaction. Used for both UPDATE and CONTRADICT.
- `store.invalidate(item_id, *, status)` — close a claim's validity (e.g. `ARCHIVED`).
- `store.bump_corroboration(item_id)` — increments the corroboration counter **only**.
- `store.add_edge(child, parent, role)` — `MEMBER_OF | EVIDENCE | SUPERSEDES | CONTRADICTS`.
- `store.set_feedback(item_id, feedback)` — used by NOOP to stamp `CONFIRMED`.

### 1.3 Verified store ground-truths the pipeline depends on
- FTS5 indexes exactly `content, lens_name, lens_criterion, lens_page`. Alias recall via
  `lens_criterion`/`lens_page` text needs **no** schema change.
- `supersede()` is the single mechanism for UPDATE and CONTRADICT (validity close +
  history edge). CONTRADICT additionally adds a `CONTRADICTS` edge.
- **`bump_corroboration` does NOT touch `last_relevant_at`.** There is **no setter for
  `last_relevant_at`** in the frozen store. NOOP therefore cannot freshen the recency
  trust signal today. Builders must NOT assume NOOP touches `last_relevant_at` — it
  cannot. (Logged as the one store gap; see §11.)
- `store.search` is active-only and **not** scope-filtered. Scope-correct recall =
  intersect `search()` hits with a scoped `store.query(...)` id-set in the consumer.
- Enums (frozen, in `models.py`):
  - `Kind`: includes `CLAIM`, `LENS`.
  - `Status`: includes `ACTIVE`, `SUPERSEDED`, `ARCHIVED`.
  - `Provenance` ordinal (high→low): `USER_AUTHORED > RECORDED > INFERRED > EXTERNAL`;
    `INDUCED` is used for lenses.
  - `Feedback`: `NONE`, `CONFIRMED`, `CORRECTED`.
  - `EdgeRole`: `EVIDENCE`, `SUPERSEDES`, `CONTRADICTS`, `MEMBER_OF`.
  - `Scope` is mandatory; `ScopeKind` ∈ user/project/session; user-scope ⇒ `key is None`
    (enforced by `Scope.__post_init__`).
  - `SourceRef`: `{kind, ref, captured_at}`.

---

## 2. Shared pipeline data shapes (extend models.py, never change its invariants)

These transient dataclasses live in `ntrp/memory/pipeline/types.py`. They are **not**
stored rows and add **no** columns to the store. They reuse `Scope`, `SourceRef`,
`Provenance`, `Kind`, `MemoryItem`, `Edge` from `models.py` verbatim. A `ClaimCandidate`'s
`content`/`source_refs`/`provenance` map by trivial field-copy onto a
`MemoryItem(kind=CLAIM, …)` at write time — no translation layer.

```python
# ntrp/memory/pipeline/types.py
from dataclasses import dataclass, field
from enum import Enum
from ntrp.memory.models import (
    Scope, SourceRef, Provenance, Kind, MemoryItem,
)

# --- Capture output -------------------------------------------------
class BoundaryKind(Enum):
    EXPLICIT   = "explicit"      # /close or remember()
    SESSION    = "session"       # chat session / automation run finished
    IDLE       = "idle"          # no activity within idle window
    SEMANTIC   = "semantic"      # background topic-shift cut
    CAP        = "cap"           # max-window force-cut (runaway stream)

class ExchangeRole(Enum):
    LIVE_CHAT  = "live_chat"
    AUTOMATION = "automation"
    SCHEDULED  = "scheduled"

@dataclass
class RawExchange:
    """Verbatim raw turn / tool-run / source event. Held in memory only."""
    turn_id: str                 # stable id within the unit, used as the grounding token
    text: str
    source_ref: SourceRef        # pointer back into the immutable raw layer

@dataclass
class Watermark:
    source_id: str
    cursor: str                  # raw store's own monotonic position
    swept_at: str                # ISO instant work began (advance-after-success)

@dataclass
class CaptureUnit:
    """The unit Admit judges. Transient — never a stored row."""
    scope: Scope
    role: ExchangeRole
    exchanges: list[RawExchange]
    source_refs: list[SourceRef]     # one per exchange; == the refs claims will inherit
    boundary: BoundaryKind
    watermark: Watermark
    forced: bool = False             # explicit (/close, remember) → pin ADMIT in Admit

# --- Admit output ---------------------------------------------------
class Verdict(Enum):
    ADMIT  = "admit"
    REJECT = "reject"

@dataclass
class AdmitResult:
    verdict: Verdict
    unit: CaptureUnit
    residual: str | None                 # part memory could NOT predict; None on REJECT
    reason: str                          # one line, for trace + eval audit
    candidates: list[MemoryItem]         # recalled set the judgment was made against
    forced: bool                         # correction/remember short-circuit fired

# --- Extract output -------------------------------------------------
@dataclass
class ClaimCandidate:
    content: str                         # atomic, self-contained, coref resolved inline
    source_refs: list[SourceRef]         # the SUBSET grounding THIS claim
    provenance: Provenance               # coarse rule, see §6
    scope: Scope
    canonical_subject: str               # LLM-resolved stable referent; the recall key
    subject_surfaces: list[str]          # observed surface forms; recall + alias fuel

@dataclass
class DroppedSpan:
    turn_id: str | None
    attempted_content: str
    reason: str                          # grounded_false | subject_unresolved | evidence_missing

@dataclass
class ExtractResult:
    candidates: list[ClaimCandidate]
    dropped: list[DroppedSpan]

# --- Reconcile output -----------------------------------------------
class Op(Enum):
    ADD        = "add"
    UPDATE     = "update"
    NOOP       = "noop"
    CONTRADICT = "contradict"

@dataclass
class ReconcileResult:
    claim_index: int
    op: Op
    subject_lens_id: str | None
    written_id: str | None = None        # successor/new claim id for ADD/UPDATE/CONTRADICT
    target_claim_id: str | None = None    # superseded/corroborated target
    subject_created: bool = False
    escalated: bool = False

# --- Lint output ----------------------------------------------------
class LintOpKind(Enum):
    MERGE       = "merge"
    INVALIDATE  = "invalidate"
    DROP_ORPHAN = "drop_orphan"
    NOOP        = "noop"

@dataclass
class LintReport:
    scope: Scope
    merged: int
    invalidated: int
    dropped: int
    contradictions_flagged: int
    degraded: bool                       # FTS unavailable → neighborhood collapsed

# --- Retrieve output ------------------------------------------------
@dataclass
class Retrieval:                         # input (config object; >5 fields per CLAUDE.md)
    goal: str
    scope: Scope
    also_scopes: list[Scope] = field(default_factory=list)
    valid_at: str | None = None
    token_budget: int = 2000
    kinds: tuple[Kind, ...] = (Kind.CLAIM,)
    lens_hint: str | None = None

@dataclass
class RankedItem:
    item: MemoryItem
    fts_rank: float | None
    vector_rank: float | None
    rrf: float
    freshness: float
    provenance_ord: int
    corroboration: int
    order_score: float                   # transparent scalar; ORDERS, never gates

@dataclass
class RetrievedContext:
    rendered: str
    items: list[RankedItem]
    degraded: bool
    diagnostics: dict
```

---

## 3. Component interfaces (exact async signatures)

All processors are async, take their store/LLM/embedder by constructor injection, and
follow CLAUDE.md's config-object rule for >5 params. The cheap model class (haiku/flash
tier) is shared by Capture's boundary check, Admit, Extract, Reconcile, Lint, and
Retrieve compression; the strong model is used **only** for Reconcile/Lint contested
merges.

```python
# capture.py
class CaptureService:
    def __init__(self, raw_sessions, raw_automations, store: MemoryStore,
                 cheap_llm: CompletionClient, *, config): ...
    async def sweep(self, source_id: str) -> list[CaptureUnit]: ...
    async def close(self, session_id: str, boundary: BoundaryKind) -> CaptureUnit | None: ...
    async def on_remember(self, text: str, scope: Scope, source_ref: SourceRef) -> CaptureUnit: ...
    # watermark advance is a callback Admit invokes on durable acceptance:
    async def commit_watermark(self, wm: Watermark) -> None: ...

# admit.py
class AdmitGate:
    def __init__(self, store: MemoryStore, cheap_llm: CompletionClient,
                 embed: EmbeddingClient): ...
    async def admit(self, unit: CaptureUnit) -> AdmitResult: ...

# extract.py
class Extractor:
    def __init__(self, cheap_llm: CompletionClient): ...   # NO store dependency
    async def extract(self, admitted: AdmitResult, *, model) -> ExtractResult: ...

# reconcile.py
class Reconciler:
    def __init__(self, store: MemoryStore, cheap_llm: CompletionClient,
                 strong_llm: CompletionClient, embed: EmbeddingClient): ...
    async def reconcile(self, candidates: list[ClaimCandidate], scope: Scope,
                        *, prior_candidates: list[MemoryItem] | None = None
                        ) -> list[ReconcileResult]: ...

# consolidate.py  (background)
class ConsolidateLint:
    def __init__(self, store: MemoryStore, cheap_llm: CompletionClient,
                 strong_llm: CompletionClient, *, model: str, config): ...
    async def run_once(self, *, scope: Scope) -> LintReport: ...
    async def run_loop(self) -> None: ...   # while True: sweep eligible scopes; sleep(consolidation_interval)

# retrieve.py
class Retriever:
    def __init__(self, store: MemoryStore, embed: EmbeddingClient,
                 cheap_llm: CompletionClient): ...
    async def retrieve(self, req: Retrieval) -> RetrievedContext: ...

# write.py  (the shared admit→write seam; remember() and future writers use it)
@dataclass
class WriteRequest:
    content: str
    scope: Scope
    provenance: Provenance
    source_refs: list[SourceRef]
    valid_from: str | None = None
    bypass_admit: bool = False

@dataclass
class WriteOutcome:
    written: bool
    item_id: str | None
    reason: str

class WriteSeam:
    def __init__(self, store: MemoryStore, reconciler: Reconciler,
                 admit: AdmitGate): ...
    async def admit_and_write(self, request: WriteRequest) -> WriteOutcome: ...
```

### 3.1 The hand-off chain (who passes what to whom)
- Capture → Admit: `CaptureUnit`. Admit calls `capture.commit_watermark(unit.watermark)`
  on durable acceptance (at-least-once; re-emit is idempotent on stable `source_refs`).
- Admit → Extract: the full `AdmitResult` (so Extract sees `residual` and `scope`).
  Extract runs **only** on `verdict == ADMIT`.
- Admit → Reconcile (carried via Extract): `AdmitResult.candidates`. **Reconcile reuses
  the exact recalled set Admit already built** as `prior_candidates`, so Admit and
  Reconcile share one consistent view of memory and a NOOP becomes near-impossible if
  Admit did its job. Reconcile still runs its own subject-recall (it recalls *entity
  lenses*, a different axis than Admit's claim recall) but seeds from Admit's candidates.
- Extract → Reconcile: `list[ClaimCandidate]`.
- Reconcile → store: writes. End of the per-exchange path.
- Consolidate/Lint and Retrieve are decoupled (background sweep / read path).

---

## 4. Capture — bounding + durability

**Owns:** turning the raw stream into discrete, scoped, evidence-anchored `CaptureUnit`s.
**Never:** summarizes, extracts, judges worth, or writes `memory_items`.

- **Boundaries** (priority order): EXPLICIT (`/close`, `remember()`) → SESSION/run-close →
  IDLE → SEMANTIC (background-only). A CAP force-cut bounds runaway never-closing streams.
- **Trigger:** background, watermark-driven sweep (Fork B) is the safety net and the only
  mechanism for never-closing automations. Interactive boundaries (1–3) are an inline
  optimization on top. The semantic-shift LLM call runs **only** in the background sweep,
  never on the hot path.
- **Scope assignment (deterministic):** chat session `project_id` → project scope; bare
  chat → user scope; automation run → session scope keyed by `origin_automation_id` /
  `session_id`. Read from structural metadata; never LLM-inferred.
- **Store usage:** reads raw stores (`context/store.py` sessions/runs, `automation/store.py`)
  + the memory `meta(key,value)` table for watermarks (keys `capture:wm:<source_id>`).
  Writes nothing to `memory_items`/edges.
- **Durability contract:** record `swept_at` before work; advance the watermark **only**
  after Admit durably accepts the unit (the `commit_watermark` callback). Crash mid-sweep
  re-reads from the un-advanced cursor → at-least-once, idempotent on stable `source_refs`.

**LLM:** boundary kind SEMANTIC only, background only.
- Input: prior window's last few exchanges (continuity = first line of prior window, not a
  summary) + next un-segmented batch + source kind.
- Output (structured): `{shift: bool, cut_after_index: int | null, reason: str}`.
- Interactive + idle boundaries are zero-LLM.

---

## 5. Admit — the one cheap gate that governs volume

**Spine:** Approach 2 (retrieval-grounded surprise test) — recall first, judge the
residual against what memory already knows; "most exchanges admit nothing" is a
structural consequence. **Grafted:** Approach 1's zero-LLM free-rejection tier (the call
fires only where judgment is open) + Approach 3's recall-grounded prompt framing (nearest
existing claims shown beside the exchange). **Dropped:** Approach 1's stateful
structural-key cache and Approach 3's salience segmentation — both add a second heuristic
surface and risk false-drop.

Flow inside `admit(unit)`:
1. **Correction short-circuit (0 LLM).** If the unit carries `forced` (a
   `Feedback.CORRECTED` marker or `remember()` path) → `forced=True`, `verdict=ADMIT`.
   Still runs recall (step 3) so `candidates` flow downstream; skips the judgment call.
2. **Free-rejection tier (0 LLM).** REJECT without a call ONLY when definitionally
   empty: below a trivial-length floor. This is "is there anything here at all" — a
   length check, not content matching. **No keyword/prefix/word list** (banned):
   tool-status chatter, operational repeats, and known SOPs all flow to the judge
   (step 4), which rejects them (memory already holds them → surprise ≈ 0 → REJECT).
   Pure-tool-turn cost, if it matters, is bounded structurally upstream at capture by
   message-role — never by matching content here.
3. **Recall (0 LLM, store-only).** Query = the exchange text:
   - `store.search(text, limit≈8)` (FTS over content + lens text),
   - `store.query(scope=unit.scope, kind=CLAIM, status=ACTIVE, …)`,
   - optional entity-lens union via `store.search` over lens fields.
   `has_fts == False` → fall back to scope-filtered `query()` only; judgment runs with
   thinner context, **biased toward ADMIT** (false-admit recoverable; false-reject of a
   new fact is not).
4. **The one cheap call (structured).** Fires on everything surviving 1–2.
   - System rubric (prompt-cached prefix): the A-MAC five factors **as questions to
     weigh, never scored** (future utility, factual confidence, semantic novelty,
     temporal recency, content-type prior); the predictive-IB framing ("admit ONLY the
     part memory could NOT predict"); the hard bar verbatim ("Most exchanges admit
     NOTHING. Operational runs, the agent doing its job, restating known facts → REJECT.
     Never turn one short debugging/task segment into a durable fact."). `AUTOMATION`-role
     units get a stronger default-REJECT framing.
   - Dynamic tail: trimmed exchange (head/tail-truncate long dumps) + recalled
     candidates' `content` shown beside it.
   - Output: `{predictable_from_memory: bool, surprising_residual: str, reason: str}`.
     **No score, no confidence float.** `verdict = ADMIT if (forced or not
     predictable_from_memory)`; `residual = surprising_residual` (a seed/pointer that
     narrows Extract's surface — never a stored claim).
5. Return `AdmitResult` with `candidates` attached for Reconcile reuse.

**Store usage:** read-only — `search()`, `query()`, `get()`. Never writes.
**Cost:** ceiling **exactly 1 cheap call** per surviving exchange; correction/empty tiers
pull the amortized cost below 1. Rejected exchanges stop the whole pipeline here — Admit
is the cost governor.

---

## 6. Extract — atomize + ground (store-free)

**Owns:** turning an admitted exchange into atomic, self-contained `ClaimCandidate`s,
coreference resolved inline (Dense X self-contained, not decontextualized), each with a
`source_ref`. **Never:** decides worth (Admit did), dedups/merges/resolves-against-store
(Reconcile does), or writes. **No store dependency at all** — this is what lets the replay
corpus run Extract+Reconcile deterministically over history.

- **Provenance rule (coarse, not judgment):** user correction/explicit statement →
  `USER_AUTHORED`; agent/tool-observed fact → `RECORDED`; extractor synthesis spanning
  turns → `INFERRED`; external-sourced → `EXTERNAL`.
- **canonical_subject:** the LLM-resolved stable referent (coreference is already resolved
  for `content`; the subject is resolved the same way). It is the recall key — never a
  surface hint, never a stored id, never a pronoun/deictic/role-relative phrase. Identity at
  recall+merge time is still Reconcile's; this is the resolved name it recalls on.
- **subject_surfaces:** the surface forms the model actually saw for this subject
  (e.g. `["I","me","Timur"]`); recall + alias fuel only, decides nothing.

**LLM:** exactly one cheap call per admitted exchange, structured output
(`response_format: type[BaseModel]`).
- Input: rubric ("Extract atomic, self-contained claims. One fact per claim. Resolve all
  pronouns/references inline. Do not invent facts. Do not merge two facts. Do not split a
  fact." + faithfulness instruction: "set `grounded=true` only if every token of context,
  including pronoun antecedents AND the canonicalized subject, is recoverable from the cited
  turn") + the admitted raw turns each tagged with a stable `turn_id` + scope label (context only).
- Output: `{claims: [{content, source_turn_id, provenance, canonical_subject,
  subject_surfaces, grounded}]}`. Extract maps `source_turn_id` back to the real `SourceRef`.

**Guards (all post-LLM, no extra call), drop-on-doubt — categorical only.** No guard makes
a lexical/rule decision: there is no proper-noun regex and no stopword set. Named-entity
faithfulness is owned by the model's `grounded` flag, backed by re-groundable `source_refs`.
1. claim with no resolvable / out-of-range `source_turn_id` → `DroppedSpan` (`evidence_missing`).
2. `grounded == false` → `DroppedSpan` (`grounded_false`).
3. empty `canonical_subject` (model resolved no subject) → `DroppedSpan` (`subject_unresolved`).
   Pure empty-field check; the model emits identity, no regex mines it.
4. dropped spans are returned in `ExtractResult.dropped` and logged; the evidence is never
   lost (re-extractable from immutable raw).

**Cost:** exactly 1 cheap call; guards are pure CPU.

---

## 7. Reconcile — resolve subject, then ADD/UPDATE/NOOP/CONTRADICT (the only claim writer)

**Spine:** Approach 1's subject-batched call structure (cost `O(distinct subjects)`, not
`O(claims)`; bias-to-NEW under doubt). Subject identity rests on the extractor's
LLM-emitted `canonical_subject` — coreference is resolved upstream, so the self/User≡Timur
collapse is a property of extraction, not a recall heuristic here. **Grafted:** Approach
3's replay contract-test discipline and its honest scope-intersection handling. **Dropped:**
Approach 1's exact-fold pre-grouping (group by *resolved* subject instead — no string
heuristic owns correctness), the fictional `last_relevant_at` write, every lexical channel
(pronoun/role lists, proper-noun regex), and the cosine auto-MATCH band — **no heuristic
opens a recall channel or gates an identity decision**; embedding cosine survives only as
an RRF ranking signal that orders candidates into the judge.

Phases (each a pure function over store + LLM + embedder):

**Phase 1 — Subject candidate recall (no LLM, no heuristic gate).** Three signal-only
channels over the LLM-emitted `canonical_subject` (+ `subject_surfaces`), unioned,
recall-biased — they order the candidate set, they never decide identity:
1. **Alias/name channel (FTS).** `store.search(canonical_subject + " " +
   " ".join(subject_surfaces))` over `lens_name` / `lens_criterion` / `lens_page`. The
   accrued `lens_criterion` alias text *is* the alias index — no separate structure.
2. **Embedding channel.** `embed.embed_one(canonical_subject)`; cosine over each scoped
   entity lens's `lens_name`+`lens_page`. **Ranking signal only — orders candidates into
   the judge, never gates** (no `AUTO_MATCH_MARGIN`).
3. **Content-FTS channel.** `store.search(salient tokens of content)`.
   Merge with `rrf_merge` (reuse `search/retrieval.py`). **Scope:** intersect `search()`
   hits with `store.query(kind=LENS, scope=scope, status=ACTIVE)` (search is not
   scope-filtered). Filter to entity lenses. Cap K≈8.

**Phase 2 — Subject identity (LLM judge).**
- **0 candidates → NEW** (categorical empty set, no call).
- **≥1 candidate → exactly one cheap LLM call** decides MATCH/NEW. **No margin shortcut —
  a lone high-cosine candidate still goes to the judge.** Batched across claims sharing a
  candidate set → cost `O(distinct candidate-sets)`, still `O(distinct subjects)`.
- Input: `canonical_subject` (+ surfaces), claim `content`, ≤8 candidate cards `{lens_id,
  lens_name, lens_criterion, page-gist}`.
- Output: `{decision: MATCH <lens_id> | NEW, alias_to_add?: str}`.
- MATCH → use that lens; `lens_id` is validated against the recalled id-set, invalid →
  NEW (self-correcting); if `alias_to_add`, append the surface to `lens_criterion` so the
  next exchange recalls with an exact FTS hit (correction-feeds-the-lens loop).
- NEW → `create_item(lens)` (`kind=LENS`, `lens_kind="entity"`, `lens_exclusive=True`,
  `provenance=INDUCED`, criterion seeded "this item is about `<canonical_subject>`").
- **Under doubt → bias to NEW** (wrong-new is repairable by lint; wrong-merge poisons a
  profile). The alias append is the only lens write in Reconcile; `lens_page` synthesis
  stays deferred to Consolidate.
- Then **group claims by resolved `subject_lens_id`**.

**Phase 3 — Profile recall (no LLM).** Per subject:
`store.list_edges(subject_lens_id, direction="to", role=MEMBER_OF)` → `store.get` each
active member. **Large-subject guard:** topic-slice members via embedding/FTS over just
the group's claims when the member set exceeds budget. Cold cache → scope+subject content
FTS fallback (speed only).

**Phase 4 — Batch reconcile (LLM, one cheap call per subject).**
- Input: subject's `lens_page` summary + profile as a **numbered list**
  `{idx, claim_id, content, provenance, corroboration, feedback, valid_from}` + the
  group's extracted claims (numbered).
- Output (one row per extracted claim): `{claim_index, op, target_idx?, merged_text?,
  contested: bool, rationale}`. `target_idx` is an **index into the numbered profile,
  never a raw id**; out-of-range → re-prompt once with the valid set, never silent ADD.
  Intra-exchange dedup is free (all siblings in one call).
- **Escalation (the only strong-model spend):** a row that is `contested`, OR
  UPDATE/CONTRADICT against a high-trust target (`USER_AUTHORED` or high corroboration) →
  re-run that decision on the strong model. Typical exchange: zero escalations.
- **Provenance rule:** `USER_AUTHORED` claims always ADD/UPDATE and win supersession
  against `INFERRED`; never NOOP-suppressed.

**Store op → call mapping (invariants preserved):**

| op | store calls |
|---|---|
| ADD | `create_item(claim)`; `add_edge(child=claim, parent=subject_lens, role=MEMBER_OF)`; `source_refs` inline; optional `add_edge(role=EVIDENCE)` to cited priors |
| UPDATE | `supersede(old_id=target, new_item=merged_claim)`; then `add_edge(MEMBER_OF)` on the successor |
| CONTRADICT | `supersede(old_id=target, new_item=new_claim)` **plus** `add_edge(child=successor, parent=target, role=CONTRADICTS)`; then `MEMBER_OF` on successor |
| NOOP | `bump_corroboration(target_id)`; if incoming `USER_AUTHORED` over `INFERRED` target, also `set_feedback(target, CONFIRMED)`. **Does NOT touch `last_relevant_at` (no setter)** |
| subject NEW | `create_item(lens)` (`kind=LENS`, `lens_kind="entity"`, `lens_exclusive=True`, `provenance=INDUCED`) |
| alias add | append surface to `lens_criterion` via the create/update path |

Never deletes, never rewrites a successor chain, never branches on `lens_kind` in
storage. `lens_exclusive` is set but transitive A≡B≡C merge enforcement is **deferred to
background lint**. `lens_page` is **not** re-synthesized inline (lossy reparse) — Reconcile
only does the append-only `lens_criterion` alias edit; full page synthesis is amortized in
Consolidate.

---

## 8. Consolidate/Lint — forgetting, dedup, contradiction-flagging (background)

**Owns:** periodic health-check of the active layer — merge duplicates, invalidate
stale/contradicted, drop orphans. The only stage that *removes from circulation* (via
`invalidate`/`supersede`, never delete). **Never:** promotes up the compression spectrum
(skill/rule induction deferred), authors/splits lenses, or touches `kind=LENS` rows.
Operates on `kind=CLAIM` only.

- **Loop:** `run_loop` mirrors `CalendarMonitor` (`while True` / `asyncio.sleep`),
  interval = `config.consolidation_interval`. Started alongside other background workers.
- **Per-scope** sweeps (principle #4). One watermark per scope in `meta`:
  `consolidate_watermark:{scope_kind}:{scope_key}` → ISO of last successful instant.
- **Bounded candidate selection** (never the whole corpus): claims in scope with
  `updated_at > watermark`, capped at `MAX_ITEMS_PER_SWEEP` (~200); plus each delta
  claim's **recall neighborhood** (a handful of active claims via `store.search()`), so a
  new claim merges against an older one outside the delta.
- **Durability:** record `sweep_start` before work; advance watermark to `sweep_start`
  **only on full success**. A capped catch-up sweep advances only to the last processed
  claim's `updated_at` (not `sweep_start`), so the unprocessed tail is not skipped. Ops
  are idempotent (re-merging an already-merged pair is a NOOP — loser no longer active).

**The four ops (LLM judgment over recalled neighborhoods, banded routing, never a
threshold).** One structured cheap call per neighborhood:
1. **MERGE duplicates** → keep best-grounded survivor (higher provenance ordinal, then
   corroboration, then more `source_refs`); `supersede(old=loser,
   new=survivor-with-unioned-source_refs)`; `bump_corroboration(survivor)`; survivor
   inherits the loser's `MEMBER_OF` edges via `add_edge`.
2. **INVALIDATE stale/contradicted** → stale: `invalidate(status=ARCHIVED)`; genuine
   contradiction with a successor: `supersede` + `CONTRADICTS` edge. Never auto-erase on
   freshness alone (freshness means re-check).
3. **DROP_ORPHAN** → claims with empty/all-dangling `source_refs` and no connecting edge:
   `invalidate(status=ARCHIVED)`.
4. **NOOP** when unsure (high bar).
- Defragmenting a split procedure = MERGE with many→one survivor (no separate machinery).

**Entrenchment guard (critical):** lint may only *demote* (close intervals, merge); it
may **never raise trust**. Merge survivor provenance = max of inputs, **capped at
`INFERRED`** when the merge is the LLM's inference. A `feedback=CONFIRMED`
(user-touched) claim is **never** invalidated or merged-away — only flagged for review. A
later higher-provenance direct-evidence claim always wins over a lint-produced one
(invalidated rows persist, walkable, resurrectable via Reconcile).

**Prompt I/O:** system rubric ("health-check a slice of a personal KB. Propose only:
merge duplicates, invalidate stale/contradicted, drop orphans. Bar is high; when unsure,
NOOP. Never invent facts; reason only over the claims shown. Never raise trust. Never
touch a user-confirmed claim."). Input: the neighborhood as JSON
`{id, content, provenance, corroboration, feedback, valid_from/invalid_at, source_refs
summaries, edges note}` + scope. Output (`response_format`):
`LintOps = list[Merge | Invalidate | DropOrphan | NoOp]` with `reason` strings. The
processor validates every id exists/active before applying (hallucinated id dropped, not
dead-ended).

**Two contradictory high-provenance claims** → not auto-resolved; emit a `CONTRADICTS`
edge (both stay active) and surface in `LintReport`. Never silently pick a winner.

**Store usage:** reads `query`/`search`/`list_edges`; writes `supersede`/`invalidate`/
`bump_corroboration`/`add_edge(CONTRADICTS)`; watermark in `meta`. **FTS unavailable**
(`has_fts == False`) → neighborhoods collapse to the delta claim alone; degrade to
orphan-detection + intra-delta dedup; `degraded=True`, never crash.

---

## 9. Retrieve — read + query-aware compression (read-only)

**Owns:** producing a small, scope/validity-filtered, query-aware-compressed bundle to
inject. **Never:** writes, mutates trust, scores lens membership, or runs Admit/Reconcile/
Lint. Sits on top of the frozen store reads + `search/`'s `Embedder`.

Flow inside `retrieve(req)`:
1. **Candidate recall (hybrid, FTS-leaning).** Over `Kind.CLAIM`, scope+validity-filtered:
   - FTS leg: `store.search(goal, limit=N_fts)` (primary; entity-dense rows favor lexical).
   - Vector leg: `embedder.embed_one(goal)`, re-rank an over-fetched FTS pool
     (`N_fts*4`) by cosine of goal vs candidate `content` computed on the fly. **No vector
     column is added to the store** (would touch Stage-2 invariants); a persisted
     claim-embedding column is explicit future work, not now.
   - Fuse with weighted `rrf_merge` (FTS-weight > vector-weight). Reuse
     `search/retrieval.py`; do not reimplement.
   - Scope/validity is a recall **predicate** (intersect with `store.query(scope=,
     valid_at=)` id-sets), not a post-hoc filter. No superseded/archived/out-of-scope/
     expired claim reaches ranking.
2. **Entity/lens expansion (cheap, bounded).** If goal/`lens_hint` resolves to a lens,
   prefer its pre-synthesized `lens_page`; pull `MEMBER_OF` members via `list_edges` to
   boost candidates. Membership is a cache — stale/missing only costs recall, never
   correctness.
3. **Ranking (transparent scalar — ORDERS, never gates).** `order_score` combines `rrf`
   (dominant), `freshness` (monotone recency from `last_relevant_at`/`valid_from`, **not** a
   decay curve), `provenance` ordinal, `corroboration` (log-damped). It sorts; it never
   drops below a cutoff. Exclusion comes only from the hard categorical filters. Inferred/
   consolidated claims rank lower but are never silently vetoed.
4. **Query-aware compression at recall.**
   - Cheap default (no LLM): top-ranked claims verbatim to `token_budget`; atomic claims
     truncate losslessly per-item (drop whole low-rank claims).
   - LLM compression (only over budget AND large pool): one cheap query-conditioned call
     that selects + tersely re-renders into budget, **preserving each kept claim's
     `source_refs`**, never inventing claims (output constrained to the input set).

**`has_fts` resolution (the empty-vs-degraded fix):**
- FTS available, zero hits → genuinely empty. Still run `store.query` scope/validity as a
  recency-ordered fallback leg; vector leg ranks it. `degraded=False`.
- FTS unavailable → skip FTS leg; recall = `query()` pool ranked by vector + trust terms.
  `degraded=True` + diagnostic. Never empty purely because FTS is down.

**Store usage:** read-only — `search`, `query`, `get`, `list_edges`, `has_fts`,
`embedder.embed_one`. **No writes** — Retrieve does NOT bump `last_relevant_at`/
`corroboration` (write-path concern; a separate explicit "mark recalled" call is a future
product choice, not built here).

---

## 10. remember() tool + the shared write seam

**`remember()` is a plain tool** that enters the **same** admit→write path as future
writers — not a privileged shortcut. The seam is `ntrp/memory/pipeline/write.py`
(`WriteSeam.admit_and_write`).

- **Tool** `ntrp/tools/memory.py` via the `tool()` factory. Input model deliberately
  small: `{fact: str, valid_from: str | None}`. No `kind`/`confidence`/`tags`/`entities`
  (v1 cruft; Stage-2 store has no such columns). `provenance` fixed `USER_AUTHORED`;
  `kind` fixed `CLAIM`. Scope from the active project's `knowledge_scope`
  (`ScopeKind.PROJECT`/key=project_id) else `ScopeKind.USER` (key None). `SourceRef(kind=
  "chat_turn", ref=<run_id / session_id+tool_id>)`. Policy: `ALLOW`/`SESSION`, no approval
  gate (memory never deletes). Registered only when memory is ready.
- **The remember() asymmetry (within the path, not around it):** `remember()` sets
  `bypass_admit=True` → skips the "is this worth keeping" gate (user assertions are
  maximal-novelty) but still runs the **reconcile half** (recall + ADD/NOOP/CONTRADICT)
  so a repeat corroborates and a contradiction supersedes. Same recall, same reconcile,
  same store calls.
- **Seam flow:** recall (`store.search` scope-filtered in Python) → one cheap judge call
  → ADD (`create_item`) / NOOP (`bump_corroboration`) / CONTRADICT (`supersede`).
  - Judge output: `{decision: ADD|NOOP|CONTRADICT, target_id: str|null, reason}`;
    `target_id` must be one of the recalled candidate ids we passed in (self-correcting;
    invalid/unparseable → treat as ADD for remember, log).
  - Judge LLM error: with `bypass_admit=True` → fall back to plain ADD (never lose a user
    assertion); with `bypass_admit=False` → skip (don't pollute on uncertainty). Logged.
- **Returns** a truthful `WriteOutcome` → "Remembered." / "Already known (corroborated)." /
  "Updated — superseded a prior claim."

**RESOLUTION (seam vs. full Reconcile).** The remember-tool design described a small
inline judge; the Reconcile design is the full subject-batched processor. They are **one**
component: `WriteSeam` is the thin entry that, for a single user-authored claim, calls
`Reconciler.reconcile([candidate], scope, prior_candidates=recalled)`. There is no second
parallel reconcile implementation. The seam owns scope resolution + `SourceRef`
construction + `bypass_admit`; Reconcile owns the ADD/NOOP/CONTRADICT decision and all
store writes.

### Runtime wiring (minimum to boot)
- `server/runtime/knowledge.py`: open the store over `config.memory_db_path` (already
  exists, config.py — do **not** re-add) on its own connection; `await
  store.init_schema()`; build cheap+strong judges from `config.memory_model`; bind
  `self.memory = store` and `self.memory_write = WriteSeam(...)`; `memory_ready ->
  self.memory is not None`; expose `services["memory_write"]` in `tool_services()`;
  idempotent `reload_config`; close on `stop()`. Every memory branch gated on
  `config.memory` + a successfully-opened store; failure to open logs a warning and leaves
  `memory=None` (server still boots, tool absent).
- `services/chat.py` + `operator/runner.py`: replace `memory_context = None` with a thin
  scoped read `build_memory_context(store, scope)` = `store.query(kind=CLAIM, scope=,
  status=ACTIVE, valid_at=now, limit≈30)` rendered as the `## MEMORY CONTEXT` block. This
  is the floor, **not** hybrid Retrieve (ranking deferred to the Retrieve stage). Returns
  None when memory is off/empty.
- **RESOLUTION (operator injection).** Inject memory in chat now. For operator/automation
  runs, inject **only** when the run carries an explicit project scope; never call
  `remember()` from unattended automation runs in this stage (avoids the heartbeat
  feedback loop, vision §4.2/§9).

---

## 11. The one store gap (verified, surfaced for Stage 3 — NOT a store change here)

`bump_corroboration` increments the counter only; there is **no setter for
`last_relevant_at`**. Consequence: NOOP cannot freshen the recency trust signal. This
CONTRACTS document does **not** change the frozen store. Builders must code to the gap
(NOOP under-feeds freshness today). Adding `touch_relevance(item_id)` to the store is a
**separate, explicitly-out-of-scope** proposal requiring its own approval — it is NOT
part of Stage 3 and must not be assumed. The Approach-3 claim that NOOP "touches
`last_relevant_at`" is **false against the current store** and is rejected.

---

## 12. Per-exchange LLM-call BUDGET (vision §13: single → low-double-digit, never hundreds)

The cheap model class is shared; the strong model is reserved for Reconcile/Lint contested
merges only. Counts are per **admitted** exchange yielding `C` claims across `S` distinct
resolved subjects (`S` typically 1–3). Admit gates volume: **most exchanges admit nothing
and incur only Admit's ≤1 call**, then stop.

| stage | cheap calls | strong calls | notes |
|---|---|---|---|
| Capture | 0 (closeable) / ~1 per *sweep batch* (never-closing only) | 0 | hot path is zero-LLM; semantic-shift is background, amortized |
| **Admit** | **≤ 1** (ceiling exactly 1; correction/empty tiers → 0) | 0 | the volume gate; REJECT stops the whole pipeline here |
| Extract | exactly 1 | 0 | one atomization call |
| Reconcile | `S` (Phase 4) + `≤(distinct candidate-sets)` (Phase 2, ≈1; no 0-via-threshold) | 0–`S` (rare) | embeddings (`C`) are non-LLM; **batched by subject → independent of `C`** |
| Consolidate/Lint | background, `ceil(delta/neighborhood)` per scope per interval | rare (uncertain merges) | off the per-exchange path; O(delta), never O(corpus) |
| Retrieve | 0 or 1 (compression only, on budget pressure) | 0 | read path; embeddings non-LLM |

**Admitted-exchange total (excluding background Lint and read-path Retrieve):**
`1 (Admit) + 1 (Extract) + S..2S (Reconcile) + rare strong` ≈ **3–6 cheap calls** for a
typical 1–3-subject exchange — squarely "single-to-low-double-digit," strictly better than
per-claim. **Rejected-exchange total: ≤ 1** (Admit only). `remember()`: 1 cheap judge
call + 1 local FTS query. Sanity bar: if any sweep needs hundreds of calls, candidate
selection is mis-bounded.

---

## 13. File layout under ntrp/memory/pipeline/

```
ntrp/memory/pipeline/
  CONTRACTS.md          # this document (frozen)
  types.py              # all shared dataclasses/enums in §2 (reuses models.py types)
  capture.py            # CaptureService (§4)
  admit.py              # AdmitGate (§5)
  extract.py            # Extractor (§6)
  reconcile.py          # Reconciler (§7) — the only claim writer
  consolidate.py        # ConsolidateLint (§8) — background loop
  retrieve.py           # Retriever (§9) — read path
  write.py              # WriteSeam (§10) — admit→write seam; remember() entry
  prompts.py            # all stage rubrics / structured-output Pydantic schemas
```

Reused, not copied: `rrf_merge` + `Embedder` from
`ntrp/search/retrieval.py`/`index.py`; `completion(response_format=...)` from
`ntrp/llm/base.py`; background-loop pattern from `ntrp/monitor/calendar.py`;
`config.consolidation_interval`/`config.memory_model`/`config.memory_db_path` from
`ntrp/config.py`.

Outside `pipeline/` (wiring, §10): `ntrp/tools/memory.py` (remember tool),
`ntrp/server/runtime/knowledge.py`, `ntrp/services/chat.py`, `ntrp/operator/runner.py`.

**FROZEN, untouched:** `ntrp/memory/store.py`, `ntrp/memory/models.py`,
`ntrp/memory/SCHEMA.md` (the single read-only `has_fts` property in §1.1 is the only
permitted addition to the store surface), `ntrp/core/prompts.py` (already renders
`memory_context`).

---

## 14. Component boundaries (the one-line contract per stage)

- **Capture** bounds raw into scoped, evidence-anchored units. Reads raw + `meta`. Writes
  nothing to memory. ≤1 background LLM call per sweep batch.
- **Admit** decides keep/drop with one cheap call against recalled incumbents. Read-only.
  The volume governor.
- **Extract** atomizes + grounds, store-free, drop-on-doubt. One cheap call.
- **Reconcile** resolves subjects + ADD/UPDATE/NOOP/CONTRADICT. The **only** claim writer.
  `S`–`2S` cheap calls + rare strong.
- **Consolidate/Lint** forgets/dedups/flags-contradictions in the background, per scope,
  watermark-durable, demote-only. Writes via supersede/invalidate.
- **Retrieve** reads + query-aware-compresses for injection. Read-only. 0–1 cheap call.
- **WriteSeam/remember()** is the shared admit→write entry; `remember()` bypasses the
  worth-gate but runs the full reconcile half through `Reconciler`.

If two stages ever appear to need the same decision, the decision belongs to exactly one
of them per §0 principle #1; the other consumes the result. No stage re-derives another's
judgment.
