# Slice 6 — Contradiction watcher (claim conflict detection + supersession)

**Status:** Draft for PM A/B gate, then codex fire. **PRE-REQUISITE: slice 5 must land first.** Brief is speculative until then; revise post-slice-5 if pass-2 claim shape diverges from §3.3 spec.
**Prereqs:** slice 5 shipped (claim layer + `'claim_match'` reason label). Pass 2 producing `kind=claim` rows with `memory_item_parents(role='evidence')` edges. Test baseline ≥ 844 passed.
**Backlog absorbed:** none directly; this slice consumes the supersession-edge infrastructure already added in slice 4 and exercised in slice 5.
**Out of scope:** skill inducer (slice 7), UI surfacing of contradictions (post-slice-7), entity-resolution-based contradiction grouping (slice 8+), bi-temporal range queries (post-slice-7).

---

## 0. TL;DR

When a new `kind=claim` row is written (by pass 2 or eventually user-typed), find existing `status=active` claims that semantically contradict it. Within the same scope: auto-flip the older claim to `status='superseded'`, set `invalid_at=now`, write `role='contradicts'` and `role='supersedes'` edges from the new claim to the old. Across scopes (e.g. `user` vs `project:ntrp`): write a `role='contradicts'` edge BUT leave both `status='active'` — retrieval layer surfaces the conflict to the LLM as a scoped-override annotation. New module: `apps/server/ntrp/memory/contradictions.py`. Hook point: `PatternFinder._persist_claim()` calls `ContradictionWatcher.scan_for_new_claim(claim_id)` after the claim row + evidence edges are written. Manual `POST /admin/memory/contradictions/scan` endpoint for back-filling against existing claims.

---

## 1. Goal — concrete

After slice 6 ships, this works end-to-end:

1. Pass 2 writes a new claim row (slice 5).
2. **NEW:** `ContradictionWatcher.scan_for_new_claim(claim_id)` fires synchronously inside `_persist_claim` after the evidence edges are written.
3. **NEW:** Finds candidate active claims with entity-shared metadata + cosine similarity > `NTRP_CONTRADICTION_THRESHOLD` (default 0.85) + `content_negation_score(a, b) > 0.6` (or model-judged opposition signal — see §4).
4. **NEW:** For each candidate at same scope: writes `role='contradicts'` edge, writes `role='supersedes'` edge, sets old claim `status='superseded'`, `invalid_at=now`.
5. **NEW:** For each candidate across scopes: writes ONLY `role='contradicts'` edge. Both claims stay `status='active'`. Marked in metadata as `cross_scope_override=True` for retrieval-time annotation.
6. **NEW:** `MemoryRetrieval.search()` (slice 3) is extended: when a returned claim has cross-scope `contradicts` edges, render an annotation `"general: <user-claim>. In current scope: <project-claim>."` in the surfaced context. **Only this single retrieval change.** No ranking changes, no new scoring.
7. **NEW:** `POST /admin/memory/contradictions/scan` body `{ "scope": "user", "window_days": 30 }` runs a back-fill scan against all active claims in the window, idempotent (skip pairs that already have `contradicts` edges).
8. **NEW:** `POST /admin/memory/contradictions/{edge_id}/undo` reverts a within-scope supersession: removes `contradicts` + `supersedes` edges, restores old claim `status='active'`, clears `invalid_at`.

**Verification:** seed DB with 2 claims about the same entity with opposed content ("user prefers tea" vs "user prefers coffee"), run pass 2 or `/admin/memory/contradictions/scan`, assert: old claim superseded, edges present, retrieval surfaces only the new claim.

---

## 2. Hard scope boundaries

### Files codex MAY touch

**Add:**
- `apps/server/ntrp/memory/contradictions.py` — `ContradictionWatcher` class, `ContradictionCandidate` dataclass, scan + scoring helpers.
- `apps/server/ntrp/memory/prompts/contradiction_judge.txt` — LLM prompt for opposition judgment (used when heuristic score is borderline 0.5–0.7).
- `apps/server/tests/memory/test_contradictions.py` — ≥ 12 tests.

**Modify:**
- `apps/server/ntrp/memory/pattern_finder.py` — `_persist_claim` calls `ContradictionWatcher.scan_for_new_claim(claim_id)` after evidence edges are written. ONE line added at the end of the method. No other changes.
- `apps/server/ntrp/memory/retrieval.py` — add cross-scope annotation rendering when surfacing claims with `contradicts` edges to other-scope claims. Single helper `_render_cross_scope_annotation(item)` + one call site in the search-result rendering path.
- `apps/server/ntrp/memory/repository.py` (or wherever `MemoryItemsRepository` lives — codex must locate) — add `set_status(item_id, status, invalid_at=None)` if not already present. If present, skip.
- The slice-5 admin router — add 2 endpoints: `/admin/memory/contradictions/scan` + `/admin/memory/contradictions/{edge_id}/undo`.

### Files codex MUST NOT touch (frozen zones)

- `apps/server/ntrp/memory/connectors/*` — slice 2.
- `apps/server/ntrp/memory/buffers_store.py`, `episode_close.py` — slice 2.
- `apps/server/ntrp/memory/activation.py` — slice 3.
- `apps/server/ntrp/memory/pattern_finder.py` body — EXCEPT the one-line `ContradictionWatcher.scan_for_new_claim` call at the end of `_persist_claim`. Do NOT refactor pass-1 or pass-2 logic.
- `apps/server/ntrp/knowledge/contradictions.py` — old `KnowledgeObject`-based contradiction code. Slice 6's new module lives at `apps/server/ntrp/memory/contradictions.py` (different path). Do NOT modify the knowledge/ version. Deprecation comment only.
- `apps/server/ntrp/knowledge/skill_promotions.py`, `write_gate.py` — slice 7.
- Desktop UI — post-slice-7.

### Files codex MUST NOT delete

No deletions. The old `knowledge/contradictions.py` stays in place (still referenced by `fact_consolidation.py`, still has callers in knowledge routes). Removal is post-slice-7.

---

## 3. Algorithm — candidate discovery

### 3.1 Trigger

```python
# inside PatternFinder._persist_claim, after evidence edges written:
await self._contradiction_watcher.scan_for_new_claim(claim_id, scope=scope)
```

Synchronous. If the watcher raises, the pass-2 run logs the error but does NOT roll back the new claim (the claim is still valuable; missing contradiction detection is graceful degradation).

### 3.2 Candidate pool

```python
async def scan_for_new_claim(self, claim_id: str, *, scope: str) -> list[ContradictionCandidate]:
    new_claim = await self.repo.get_item(claim_id)
    new_entities = set(new_claim.metadata.get("entities", []))
    if not new_entities:
        return []  # no entities → no contradiction grounding; skip

    # candidates: active claims sharing at least one entity
    candidates = await self.repo.list_items_by_entities(
        kind="claim",
        status="active",
        entities=list(new_entities),
        exclude_ids=[claim_id],
        limit=200,
    )
    ...
```

If `list_items_by_entities` doesn't exist on the repo, codex adds it (it's a natural extension and slice 6 is the right place for it). The implementation is a `LIKE '%entity%'` over `metadata->entities` or a JOIN against a future entity table — codex picks the simplest working SQL.

### 3.3 Scoring per candidate

```python
@dataclass(slots=True)
class ContradictionCandidate:
    new_claim_id: str
    old_claim_id: str
    cosine_similarity: float          # both claims' embeddings
    entity_overlap: float             # Jaccard over entity sets
    negation_score: float             # heuristic 0-1 (see §4)
    judge_verdict: str | None         # "opposed" | "compatible" | None (LLM, only if borderline)
    final_score: float                # weighted combination
    cross_scope: bool                 # new.scope != old.scope
```

`final_score = 0.4 * cosine + 0.2 * entity_overlap + 0.4 * negation_score`.

Threshold: `NTRP_CONTRADICTION_THRESHOLD` (default 0.65 final). Above threshold AND `negation_score > 0.5` → contradiction.

**Borderline rule** (`0.5 ≤ final_score ≤ 0.75` AND `negation_score ≤ 0.6`): call `judge_pair_with_llm` (§4.2) to get a tiebreaker verdict. If verdict == "opposed", treat as contradiction; else skip.

### 3.4 Cross-scope detection

```python
cross_scope = (new_claim.scope != old_claim.scope)
```

The current scope hierarchy in `memory_items` is flat strings (`"user"`, `"project:<slug>"`). Cross-scope means string inequality. Slice 6 does NOT introduce scope inheritance (`user` is NOT a parent of `project:ntrp` in the data model yet) — that's slice 8+ territory. So `user` vs `project:ntrp` are equally "cross-scope" as `project:foo` vs `project:bar`.

---

## 4. Negation scoring

### 4.1 Heuristic (cheap, runs on every candidate)

`negation_score(text_a, text_b) -> float in [0, 1]`:

```python
NEGATION_MARKERS = {
    ("prefers", "dislikes"),
    ("uses", "avoids"),
    ("loves", "hates"),
    ("supports", "opposes"),
    ("believes", "rejects"),
    ("present tense", "past tense"),
    ("active", "inactive"),
    ("on", "off"),
    ("true", "false"),
    ("enabled", "disabled"),
    # ... codex may extend, but keep < 30 pairs to stay fast
}

def negation_score(a: str, b: str) -> float:
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    for word_a, word_b in NEGATION_MARKERS:
        if word_a in a_tokens and word_b in b_tokens:
            return 0.9
        if word_b in a_tokens and word_a in b_tokens:
            return 0.9
    # "not X" / "no longer X" patterns
    if any(re.search(rf"\b(not|no longer|never|stopped)\s+\w+", t) for t in [a, b]):
        return 0.6
    return 0.0
```

This is intentionally crude — the LLM judge (§4.2) handles the cases this misses.

### 4.2 LLM judge (only for borderline candidates)

Prompt at `apps/server/ntrp/memory/prompts/contradiction_judge.txt`:

```
You are deciding whether two claims about a user contradict each other.

Claim A: {claim_a}
Claim B: {claim_b}

Shared entities: {entities}

Answer with exactly ONE word:
- "opposed" if the claims cannot both be true at the same time for the same context
- "compatible" if the claims can coexist (different contexts, refinements, or unrelated facets)
- "unclear" if you genuinely cannot tell

Then on a new line, give a one-sentence reason.
```

Parse first line as verdict. Use temperature 0. Reuse the `summary_client` from `PatternFinder` (already injected).

### 4.3 Cost guard

Never call the judge unless heuristic is in the 0.5–0.75 final-score band. In practice this should fire on < 10% of candidate pairs. If it fires on > 30%, codex must surface this in the PM checklist — the threshold is mis-calibrated.

---

## 5. Persistence — edges + status flips

### 5.1 Within-scope (`cross_scope = False`)

```python
# write contradicts edge (both directions semantically, one row practically)
await self.repo.add_parent(
    item_id=new_claim_id,
    parent_id=old_claim_id,
    role="contradicts",
)
# write supersedes edge
await self.repo.add_parent(
    item_id=new_claim_id,
    parent_id=old_claim_id,
    role="supersedes",
)
# flip old claim status
await self.repo.set_status(
    item_id=old_claim_id,
    status="superseded",
    invalid_at=now,
)
```

### 5.2 Cross-scope (`cross_scope = True`)

```python
# write contradicts edge ONLY
await self.repo.add_parent(
    item_id=new_claim_id,
    parent_id=old_claim_id,
    role="contradicts",
)
# tag new claim's metadata for retrieval-time annotation
metadata = dict(new_claim.metadata)
metadata.setdefault("cross_scope_overrides", []).append(old_claim_id)
await self.repo.update_metadata(item_id=new_claim_id, metadata=metadata)
# NO status change. NO invalid_at. NO supersedes edge.
```

### 5.3 Idempotency

Before either branch: check if a `contradicts` edge already exists between this pair (either direction). If yes, skip. This makes the back-fill scan endpoint safe to run repeatedly.

### 5.4 Undo

`POST /admin/memory/contradictions/{edge_id}/undo`:

1. Look up the `contradicts` edge by ID. If not found, 404.
2. If within-scope (old claim was superseded): remove `contradicts` + `supersedes` edges, restore old claim `status='active'`, clear `invalid_at`.
3. If cross-scope: remove `contradicts` edge, remove the new claim's `cross_scope_overrides[old_claim_id]` metadata entry.
4. Idempotent: if state already shows the undo applied (old claim is active, no edges), return 200 with `already_undone: true`.

---

## 6. Retrieval-side annotation

`apps/server/ntrp/memory/retrieval.py` — when surfacing a claim to the LLM context:

```python
def _render_claim_with_annotations(item: MemoryItem) -> str:
    overrides = item.metadata.get("cross_scope_overrides", [])
    if not overrides:
        return item.content
    # fetch the overridden claims (cached batch fetch)
    overridden = await self._batch_get_items(overrides)
    parts = []
    for prior in overridden:
        prior_scope = prior.scope
        new_scope = item.scope
        parts.append(f"general ({prior_scope}): {prior.content}")
    parts.append(f"in current scope ({item.scope}): {item.content}")
    return "\n".join(parts)
```

This is the ONLY retrieval-layer change. No ranking changes, no new score, no new reason label (it's still `'claim_match'` from slice 5; the annotation is rendering, not retrieval).

---

## 7. DI wiring

`ContradictionWatcher.__init__`:

```python
def __init__(
    self,
    *,
    repo: MemoryItemsRepository,
    embedder: Any,
    judge_client: Any | None = None,  # None disables LLM judge; tests pass a fake
    threshold: float | None = None,
):
    ...
```

`PatternFinder.__init__` gains an optional `contradiction_watcher` kwarg. If `None`, pass-2 skips the scan-call (graceful degradation for tests that don't care). Production DI builder injects it.

---

## 8. Tests — ≥ 12 cases

`apps/server/tests/memory/test_contradictions.py`:

1. `test_negation_score_detects_prefers_vs_dislikes`
2. `test_negation_score_returns_zero_for_unrelated_claims`
3. `test_negation_score_handles_not_X_pattern`
4. `test_scan_for_new_claim_writes_contradicts_edge_within_scope`
5. `test_scan_for_new_claim_writes_supersedes_edge_and_flips_status_within_scope`
6. `test_scan_for_new_claim_cross_scope_writes_only_contradicts_edge`
7. `test_scan_for_new_claim_cross_scope_tags_metadata_overrides`
8. `test_scan_idempotent_skips_existing_contradicts_edges`
9. `test_scan_skips_claims_with_no_shared_entities`
10. `test_scan_calls_judge_only_in_borderline_band`
11. `test_judge_unclear_verdict_is_treated_as_compatible`
12. `test_admin_scan_endpoint_processes_window`
13. `test_undo_endpoint_restores_old_claim_status_within_scope`
14. `test_undo_endpoint_idempotent`
15. `test_retrieval_renders_cross_scope_annotation`

Pick 12+ from this list.

---

## 9. Hard gates

1. `cd apps/server && uv run pytest tests/ --co -q 2>&1 | tail -5` → 0 errors.
2. `cd apps/server && uv run pytest tests/memory/ -q 2>&1 | tail -5` → ≥ 81 passed (69 from slice 5 + ≥ 12 new), 0 failed.
3. `cd apps/server && uv run pytest tests/ -q 2>&1 | tail -5` → ≥ 856 passed (slice-5 baseline + ≥ 12 new), 0 failed.
4. `cd apps/server && uv run ruff check ntrp/ tests/ 2>&1 | tail -3` → All checks passed!
5. `grep -c 'class ContradictionWatcher' apps/server/ntrp/memory/contradictions.py` → 1
6. `grep -c '^async def test_\|^def test_' apps/server/tests/memory/test_contradictions.py` → ≥ 12
7. `wc -l apps/server/ntrp/memory/contradictions.py` → ≥ 150, ≤ 400 (keep it focused)
8. `grep -n 'ContradictionWatcher' apps/server/ntrp/memory/pattern_finder.py` → exactly 2 lines (import + one call site)

---

## 10. PM checklist for codex's report

1. How often did the LLM judge fire in your test runs? If > 30%, why?
2. What's the actual `list_items_by_entities` SQL you wrote? Paste the query.
3. Did you have to add any new columns to `memory_items` (e.g. `invalid_at`)? Confirm migration or confirm it already existed from slice 4.
4. Paste output of all 8 gates from §9.
5. Confirm `knowledge/contradictions.py` was NOT modified (just deprecation-commented).
6. `git diff --stat` against `main` HEAD before commit.

---

## 11. Codex prompt (verbatim — extracted by invoke.sh §13)

```
You are implementing slice 6 of the ntrp memory redesign.

Prerequisite: slice 5 (`docs/internal/slices/slice-05-claim-layer.md`) must be landed and all its gates green. Verify with:
  cd apps/server && uv run pytest tests/memory/test_claim_layer.py -q

Read `docs/internal/slices/slice-06-contradiction-watcher.md` start to finish, then:
1. Read `docs/internal/slices/slice-05-claim-layer.md` for prior-slice conventions.
2. Read `apps/server/ntrp/memory/pattern_finder.py` for the `_persist_claim` hook point.
3. Read `apps/server/ntrp/memory/retrieval.py` for the rendering call site.
4. Read `docs/internal/ntrp-memory-redesign-spec.md` §3.4 (contradiction watcher) + §2.6 (roles) + §2.5 (claim).
5. Read `apps/server/ntrp/knowledge/contradictions.py` for prior-art inspiration ONLY — do not import from it.

Implement §1-§7 of the brief. Write tests per §8. Run gates §9. Answer §10.

Frozen zones in §2 — touching anything listed is a fail. Slice 7 modules (skill_promotions, write_gate) are off-limits.

Commit only when all 8 gates green:
  feat(memory): slice 6 — contradiction watcher (claim conflicts + supersession)

Do NOT push. Do NOT touch frozen zones. Ask in §10 if ambiguous.
```

---

## 12. Sequence of work

1. Read phase: spec §3.4, §2.6, §2.5; slice 5 brief; pattern_finder.py hook point.
2. Skeleton: `ContradictionWatcher` class, `ContradictionCandidate` dataclass.
3. `negation_score` heuristic + judge prompt file.
4. `scan_for_new_claim` candidate pool + scoring.
5. Persistence branches (within-scope vs cross-scope) + idempotency check.
6. Admin endpoints (`/scan`, `/undo`).
7. Retrieval annotation rendering.
8. `PatternFinder._persist_claim` 1-line hook.
9. Tests (≥ 12).
10. Gates + report.

---

## 13. Sequence of work — codex's plan (same as §12)

(Aliased for invoke.sh prompt-extraction symmetry with slice 5 §13.)

---

## 14. Out of scope explicitly

- **Skill inducer** — slice 7.
- **UI surfacing of contradictions** (one-click undo in chat, contradiction-history view) — post-slice-7.
- **Scope-inheritance hierarchy** (user → project nesting) — slice 8+.
- **Bi-temporal range queries** ("what did we believe on date X") — possible later; not slice 6.
- **Triple-scope contradictions** (3+ claims pairwise opposed) — handled as a sequence of pairwise scans; no special logic.
- **Contradiction-watcher-triggered-by-user-edit** — slice 6 only triggers on pass-2 + manual scan endpoint. User-typed claim contradictions wait for slice 7's proposal flow.

---

## 15. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM judge fires too often → token cost spikes | Medium | Medium | §4.3 cost guard + PM gate question (§10.1); threshold tunable. |
| `negation_score` is too crude → misses real contradictions | High | Medium | LLM judge covers the gap; expanding `NEGATION_MARKERS` is a slice-7+ follow-up if PR data shows missed cases. |
| Cross-scope annotation breaks retrieval prompt structure | Medium | High | Single render helper, opt-in based on metadata; turn off via env if it regresses. |
| Auto-supersede flips wrong claim (newer is wrong, older was right) | Medium | High | Undo endpoint is mandatory; surface every flip in run-result so user can audit. |
| `_persist_claim` hook adds latency to pass 2 runs | Medium | Low | Scan is candidate-bounded (≤ 200), judge is rare; budget < 500ms per claim. |
| Idempotency check has a race against concurrent pass-2 runs | Low | Medium | Same-row UPSERT semantics on edges (already in slice-4 schema); race produces duplicate edges at worst, not wrong supersessions. |

---

**End of brief.**
