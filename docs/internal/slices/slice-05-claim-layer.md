# Slice 5 — Pattern finder pass 2 (`observation → claim`) + fact-consolidation rebuild

**Status:** Draft for PM A/B gate, then codex fire. **REVISED 2026-05-28 05:20** — repo-surface corrections after auditing `items_store.py` (see §17 audit log).
**Prereqs:** slice 4 shipped (`863ce546`). 832 tests passing + 3 xfailed. Ruff clean. Token-bug fix landed (`3b66a04`). Repo cleanup done (`bfb4148f`).
**Backlog absorbed from `slice-07-backlog.md`:** §1 (LongMemEval xfails), §2A (`test_knowledge_next_level.py` resurrection — 14 tests), §3A (dead `search_*` wrappers in `memory/service.py`).
**Out of scope:** contradiction watcher (slice 6), skill inducer + `is_toolable` (slice 7), UI, retrieval-layer changes, entity-resolution revival.

---

## 0. TL;DR

Cluster recently-written `kind=observation` rows (and existing `kind=claim` rows from prior runs) by embedding similarity + entity overlap + tag overlap. For each cluster ≥ 2 evidence items, LLM-summarize into one `kind=claim` row with `role=evidence` parent edges to source observations/claims. Add `PatternFinder.run_pass2()` next to the existing `run_pass1()`. Keep pass 2 fully separate (different prompt, different threshold env var, different result dataclass). Wire it into the same `/admin/memory/pattern-finder/run` endpoint + same scheduler. Delete 4 dead `search_*` wrappers in `memory/service.py`. Resurrect 14 of the deleted `test_knowledge_next_level.py` tests against the new `memory_items` API. Unxfail 3 LongMemEval tests once claim rows surface as `object_type=fact` candidates.

---

## 1. Goal — concrete

After slice 5 ships, this works end-to-end:

1. Slice 4's pass 1 has already populated `kind=observation` rows (already shipping).
2. **NEW:** `PatternFinder.run_pass2()` clusters those observations (plus existing claims) by similarity, summarizes each cluster, writes `kind=claim` rows linked via `memory_item_parents(role='evidence')`.
3. **NEW:** `POST /admin/memory/pattern-finder/run` accepts `pass=2` (or `pass=both`) and returns clusters + claims written for the requested pass(es). Default remains `pass=1` for backward compat with slice 4.
4. **NEW:** Daily Trigger.dev scheduler stub fires both passes back-to-back (pass 1 then pass 2 — pass 2 must see fresh observations from this run, so order matters).
5. `MemoryRetrieval.search()` (slice 3) surfaces claims alongside observations and episodes for the same query — no retrieval-layer changes needed; claims are `memory_items` rows with `kind=claim`.
6. **NEW:** Claim rows are returned by `MemoryRetrieval` with `reason='claim_match'` so LongMemEval's `object_type=fact` candidate test passes.
7. **NEW:** 4 dead `search_*` wrappers in `memory/service.py` deleted. Zero callers, zero behavior change.
8. **NEW:** 14 tests from `test_knowledge_next_level.py` (recoverable at `git show 64f0ef24~1:apps/server/tests/test_knowledge_next_level.py`) ported to `tests/memory/test_claim_layer.py` against the `memory_items` surface where applicable; entity-resolution sub-tests dropped (deferred to slice 8+).

**Verification:** seed a fresh DB with 4 observations (2 about topic A, 2 about topic B, with overlapping entities), run pass 2, assert 2 claims exist with correct evidence edges and `reason='claim_match'` retrievable.

---

## 2. Hard scope boundaries

### Files codex MAY touch

**Add (new files):**
- `apps/server/ntrp/memory/prompts/pass2.txt` — pass 2 LLM prompt (mirror shape of `pass1.txt`).
- `apps/server/tests/memory/test_claim_layer.py` — ≥12 tests for pass 2.
- `apps/server/tests/memory/test_knowledge_next_level_migrated.py` — the resurrected subset of the deleted `test_knowledge_next_level.py` (14 → ~10 tests after dropping entity-resolution).

**Modify (existing files):**
- `apps/server/ntrp/memory/pattern_finder.py` — add `ClaimDraft` dataclass, `PatternFinderPass2RunResult` dataclass, `PatternFinder.run_pass2(...)`, `summarize_observation_cluster(...)`, `render_pass2_prompt(...)`, `cluster_observations(...)`, `_persist_claim(...)`. Do NOT modify the existing pass-1 functions/methods. The file may grow to ~500-550 lines; if it exceeds 600 lines, split pass 2 helpers into `pattern_finder_pass2.py` (re-exporting from `pattern_finder.py` for back-compat).
- `apps/server/ntrp/memory/service.py` — delete 4 dead `search_*` wrappers (lines 1354, 1371, 1387, 1397 per backlog §3A). No replacement.
- `apps/server/ntrp/memory/retrieval.py` — extend the reason-label set to include `'claim_match'` when a `kind=claim` row matches; **no other retrieval behavior changes** (no new ranking, no new scoring). One added branch in the reason-label assignment is the entire surface change.
- The slice-4 admin endpoint (codex must locate it — likely under `apps/server/ntrp/server/routers/`) — add `pass: int | str = 1` query/body parameter, branch on `pass in {1, 2, "both"}`.
- `apps/server/tests/benchmarks/test_longmemeval_benchmark.py` — remove the 3 `@pytest.mark.xfail` decorators called out in backlog §1 (or rewrite their assertions if the new label set diverges — codex's call, but document it in §12).
- `apps/server/ntrp/benchmarks/longmemeval.py:224` — replace the deferred-`RuntimeError` with the actual call path against pass-1 observations (the test that hits this is one of the 3 xfails).

### Files codex MUST NOT touch (frozen zones)

- `apps/server/ntrp/memory/connectors/*` — episode ingest layer, slice 2 territory.
- `apps/server/ntrp/memory/buffers_store.py`, `episode_close.py` — episode buffering, slice 2.
- `apps/server/ntrp/memory/activation.py` — activation/recency scoring, slice 3.
- `apps/server/ntrp/memory/pattern_finder.py` pass-1 code (`run_pass1`, `cluster_episodes`, `summarize_cluster`, `render_pass1_prompt`, `_persist_observation`, every helper from line 164 through line 301). **ADD pass 2 alongside; do NOT refactor pass 1.** Shared helpers like `_cosine`, `_tag_jaccard`, `_temporal`, `_clamp01`, `_as_utc` MAY be re-used as-is; do not change their signatures.
- `apps/server/ntrp/knowledge/fact_consolidation.py` — old `KnowledgeObjectRepository`-based consolidation. Slice 5 supersedes its **role** (pass 2 is the new consolidation path) but does NOT delete the file. Leaving it in place keeps the knowledge-route endpoints alive for the desktop UI. A deprecation note at the top of the file is the only allowed edit.
- `apps/server/ntrp/knowledge/contradictions.py` — slice 6.
- `apps/server/ntrp/knowledge/skill_promotions.py` — slice 7.
- `apps/server/ntrp/knowledge/write_gate.py` — slice 7.
- The 14 desktop UI components under `apps/desktop/src/components/memory/` — UI is post-slice-7.

### Files codex MUST NOT delete

Beyond the 4 dead `search_*` wrappers explicitly listed in §3A, **no other deletions**. If codex finds something that looks dead, add it to a "candidate deletions" appendix in the PR description and stop.

---

## 3. Algorithm — clustering

Identical shape to pass 1, but the **inputs** are observations (+ existing claims), and the **similarity** weights tilt slightly toward semantic content over temporal proximity (claims are more durable, time-of-write matters less).

### 3.1 Input set

```python
observations = await self.repo.list_recent_items(
    kind="observation",
    window_days=window_days,  # default 30 (vs 7 for pass 1 — claims live longer)
    limit=limit,
    scope=scope,
)
existing_claims = await self.repo.list_recent_items(
    kind="claim",
    window_days=window_days,
    limit=limit,
    scope=scope,
)
candidates = observations + existing_claims
```

Including existing claims is what enables "claim chains" (claim of claims) — they must be **marked** so the LLM prompt can render `[claim]` vs `[observation]` differently, and so the supersession logic at the end can distinguish "we updated this old claim with new evidence" from "we made a new claim entirely."

**Note on `list_recent_items` signature (audited 2026-05-28):** the real method is `list_recent_items(*, kind, window_days, limit, scope)` — no `status` filter today. Pass 2 must filter `status == 'active'` in Python after the fetch, OR codex adds an optional `status` kwarg to the repo (small extension, document in §12).

### 3.2 Similarity

Reuse `_cosine`, `_tag_jaccard`, `_temporal` from pass 1. New combined formula (NOT the same weights as pass 1):

```python
def claim_similarity(a: MemoryItem, b: MemoryItem) -> float:
    cos = _cosine(a.embedding, b.embedding)
    jac = _tag_jaccard(a.tags, b.tags)
    tmp = _temporal(a.created_at, b.created_at)
    # pass 1: 0.5 cos + 0.2 jac + 0.3 tmp
    # pass 2: 0.65 cos + 0.20 jac + 0.15 tmp  (more weight on semantic content for claims)
    return 0.65 * cos + 0.20 * jac + 0.15 * tmp
```

**Entity overlap deliberately omitted.** The `MemoryItem` dataclass (audited 2026-05-28) has no `metadata` column and no `entities` field; entities exist only in `tags` (which `_tag_jaccard` already covers). Reviving structured entity overlap is slice 8+ work alongside entity-resolution revival. Slice 5 must NOT add a `metadata` JSON column — that's a schema migration, out of scope.

If future entity extraction lands on `tags` with a `entity:<name>` prefix convention (decide in slice 8+), pass-2 similarity can be re-tuned without breaking compat.

### 3.3 Threshold

New env var `NTRP_PATTERN_FINDER_PASS2_THRESHOLD` (default 0.72; pass 1 uses 0.68 per `_threshold_from_env()` in `pattern_finder.py`). Higher threshold because false-positive claims are worse than false-positive observations — a bad claim survives until contradiction watcher (slice 6) catches it. Add a sibling `_pass2_threshold_from_env()` helper in `pattern_finder.py` (same shape as `_threshold_from_env` — one allowed addition).

### 3.4 Cluster shape

Reuse the union-find / connected-components approach from pass 1's `cluster_episodes`. Minimum cluster size: 2 (matching pass 1). Max cluster size: 8 (vs unlimited in pass 1 — keep claim summaries focused).

### 3.5 De-duplication against existing claims

Same shape as `_existing_observation_evidence` in pass 1 (line 269), but querying `kind=claim` evidence sets. Reuse the helper by parameterizing it: rename to `_existing_evidence(repo, *, kind, window_days, scope, limit)` and keep `_existing_observation_evidence` as a 1-line wrapper for back-compat. (This is the ONE allowed refactor inside the pass-1 file. Codex must keep the wrapper to avoid breaking imports.)

---

## 4. Algorithm — LLM summarization

### 4.1 Prompt

`apps/server/ntrp/memory/prompts/pass2.txt`:

```
You are decontextualizing a cluster of related observations into a single durable claim about the user.

A claim is a decontextualized statement that affects future behavior. It does NOT refer to specific conversations, sessions, or episodes. It states what is true about the user, their preferences, their work, or their world — as if writing it on an index card someone will read months from now.

Inputs (each item is either an observation or a prior claim):
{item_bullets}

Write ONE claim (1-3 sentences, no preamble) that captures what is durably true based on this evidence. Do NOT use phrases like "the user has been observed to" or "across recent sessions" — those mark observations, not claims. State the fact directly: "User prefers X." "User works on Y." "User believes Z."

If no decontextualized claim emerges (the evidence is too thin, too specific to one episode, or contradicts itself), write exactly: NO_CLAIM.
```

### 4.2 Rendering

`render_pass2_prompt(items: list[MemoryItem]) -> str` formats each item as:
```
- [observation] {content}
- [claim] {content}  (prior claim being refined)
```

Order items by `created_at` ascending so the LLM sees evolution-over-time when claims chain.

### 4.3 Rejection

Extend `_reject_summary` in `pattern_finder.py` to match both `NO_PATTERN` and `NO_CLAIM`. This IS an allowed edit inside the pass-1 file (one regex update).

### 4.4 Confidence

Each claim row gets `confidence = mean(evidence_confidences) * cluster_size_factor` where `cluster_size_factor = min(1.0, 0.5 + 0.1 * len(cluster))`. Field name is `confidence` on `MemoryItemInsert` (NOT `score` — audited 2026-05-28). Per spec §3.7 derivation. Codex MUST implement this — it's the field LongMemEval relies on for `object_type=fact` candidate ranking.

`evidence_confidences` = list of `item.confidence` for each evidence item (observations + prior claims) in the cluster. Slice 4 sets observation confidence to `PATTERN_FINDER_CONFIDENCE` (constant), so pass-2's mean is constant-dominated until pass-1 starts producing variable confidence. That's acceptable for slice 5; tuning is a follow-up.

---

## 5. Persistence

**Mirror slice-4's `_persist_observation` shape exactly** — `pattern_finder.py:111-159`. The real repo surface is:

- `repo.insert_item(MemoryItemInsert(...), commit=False)` — returns new item id
- `repo.insert_parent_edge(child_id, parent_id, role, commit=False)` — positional, NOT kwargs
- Status flips via raw SQL `UPDATE memory_items SET status='superseded', invalid_at=?, updated_at=? WHERE id=?`
- Transaction managed manually: `conn.execute("BEGIN")` → ops with `commit=False` → `conn.commit()` (or `rollback()` on exception)

`_persist_claim` (model on `_persist_observation`):

```python
async def _persist_claim(
    self,
    draft: ClaimDraft,
    *,
    scope: str,
    superseded_ids: list[str],
    now: datetime,
) -> str:
    embedding = await self.embedder.embed_one(draft.content)
    await self.repo.conn.execute("BEGIN")
    try:
        claim_id = await self.repo.insert_item(
            MemoryItemInsert(
                kind="claim",
                content=draft.content,
                provenance="inferred",
                source_refs=[],                  # claims carry evidence via edges, not source_refs
                confidence=draft.confidence,     # field is `confidence` on the dataclass, NOT `score`
                status="active",
                scope=scope,
                tags=draft.tags,
                embedding=embedding,
                valid_from=now,
            ),
            commit=False,
        )
        for evidence_id in draft.evidence_item_ids:
            await self.repo.insert_parent_edge(claim_id, evidence_id, "evidence", commit=False)
        for old_claim_id in superseded_ids:
            await self.repo.insert_parent_edge(claim_id, old_claim_id, "supersedes", commit=False)
            await self.repo.conn.execute(
                """
                UPDATE memory_items
                SET status = 'superseded', invalid_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), now.isoformat(), old_claim_id),
            )
        await self.repo.conn.commit()
        return claim_id
    except BaseException:
        await self.repo.conn.rollback()
        raise
```

**`ClaimDraft` dataclass:**

```python
@dataclass(slots=True)
class ClaimDraft:
    content: str
    tags: list[str]               # union of evidence tags, deduped, sorted
    confidence: float             # see §4.4
    evidence_item_ids: list[str]
```

No `entities`, no `metadata`, no `source_refs` — match the real `MemoryItem` shape.

**Supersession:** if a candidate cluster's evidence IDs are a strict superset of an existing claim's evidence IDs, that existing claim goes into `superseded_ids`. The check helper mirrors `_existing_observation_evidence` from pass 1 (line 269 of `pattern_finder.py`); generalize as described in §3.5.

**Idempotency:** if a claim already exists whose evidence set EQUALS `frozenset(item.id for item in cluster)`, skip. Mirror pass-1's `existing_evidence_ids in existing` short-circuit.

**Per-pass / cluster-size context lost:** since there's no `metadata` column, the `pass=2 / cluster_size / evidence_kinds` info I originally proposed has nowhere to land. Options:
  - (a) Encode in `tags` as `pf:pass=2`, `pf:cluster_size=N` (cheap, ugly, parseable).
  - (b) Skip entirely — pass and cluster_size are reconstructable from `list_parent_edges`.
  - (c) Add a future-proof `memory_items.metadata JSON` column in a separate migration slice.

Brief picks **(b)**. Codex confirms in §12.

---

## 6. Scheduler — Trigger.dev (or equivalent)

### 6.1 Registration

Modify the slice-4 scheduler stub (codex must find it — likely under `apps/server/ntrp/scheduler/` or referenced from the slice-4 admin router). Either:

**Option A** — add a second registration:
```python
pattern_finder_pass2_daily = schedule(
    name="pattern-finder-pass2-daily",
    cron="0 5 * * *",  # 04:00 UTC pass 1, 05:00 UTC pass 2
    handler=lambda: pattern_finder.run_pass2(),
)
```

**Option B** — update the single existing job to run both passes sequentially:
```python
async def daily_handler():
    pass1_result = await pattern_finder.run_pass1()
    pass2_result = await pattern_finder.run_pass2()
    return {"pass1": pass1_result.to_dict(), "pass2": pass2_result.to_dict()}
```

Codex picks based on what slice 4 actually shipped. Document the choice in §12.

### 6.2 Manual endpoint

`POST /admin/memory/pattern-finder/run` body:
```json
{ "pass": 1 | 2 | "both", "window_days": 30, "scope": "user" }
```

Default `pass=1` for back-compat with slice 4 callers. Response:
```json
{
  "pass1": { ...PatternFinderRunResult... },
  "pass2": { ...PatternFinderPass2RunResult... }
}
```

Missing pass keys when only one was run.

---

## 7. DI wiring

`PatternFinder.__init__` already takes `repo`, `summary_client`, `embedder`. Pass 2 needs the same dependencies — no new injectables. The threshold env var read happens lazily in `run_pass2` (mirrors `_threshold_from_env()` for pass 1).

Codex must verify the admin endpoint's `PatternFinder` factory still works. If the factory hardcodes a pass-1-only `run()` call, update it to dispatch on the new `pass` parameter.

---

## 8. Address slice-07-backlog items

### §1 — LongMemEval xfails (3 tests)

Per `slice-07-backlog.md` lines 34-58:

1. `test_longmemeval_semantic_alias_retrieves_named_streaming_service` — needs `MemoryRetrieval` to emit a richer reason label. Slice 5 adds `'claim_match'`. If the test asserts on `'semantic_alias_match'` specifically, codex updates the test to accept either `'claim_match'` or `'semantic_alias_match'` (note: real entity-alias work is slice 8). Document the decision in §12.

2. `test_longmemeval_extracted_variant_uses_turn_fact_candidates` — needs `kind=claim` rows surfaceable as `object_type=fact`. Add a tiny adapter in the LongMemEval candidate-generation path: `if row.kind == "claim": object_type = "fact"`.

3. `test_longmemeval_extracted_variant_can_use_model_episode_extraction` — needs `ntrp/benchmarks/longmemeval.py:224` un-deferred. Replace the `RuntimeError` with a call against pass-1 observations.

**Gate:** all 3 xfails removed. `tests/benchmarks/test_longmemeval_benchmark.py` should go from `9 passed, 3 xfailed` → `12 passed`. If only 2 of 3 can be unxfailed, document why in §12 and update the brief's gate count accordingly.

### §3A — dead `search_*` wrappers in `memory/service.py`

Delete:
- `search_text` (line 1354)
- `search_vector` (line 1371)
- `search_entities` (line 1387)
- `search_temporal` (line 1397)

Verification (codex MUST paste this in §12):
```bash
grep -nE 'def search_(text|vector|entities|temporal)' apps/server/ntrp/memory/service.py
# expect: 0 lines
grep -rnE '\.(search_text|search_vector|search_entities|search_temporal)\(' apps/server/ --include='*.py' | grep -v __pycache__
# expect: 0 lines (or only matches inside test fixtures that are also deleted)
```

### §2A — `test_knowledge_next_level.py` resurrection

Source: `git show 64f0ef24~1:apps/server/tests/test_knowledge_next_level.py` (recoverable from the slice-3 deletion commit).

Target: `apps/server/tests/memory/test_knowledge_next_level_migrated.py`.

**Port these subsets (≥10 of the original 14 tests):**
- Knowledge object backfill embeddings → port against `memory_items` `embedding` column
- Procedure candidate → lesson promotion → port against pass-2 claim-with-`is_toolable=False` semantics (toolable check itself is slice 7; for slice 5 just assert the claim row exists and is not a `kind=skill`)
- Semantic conflict routing → defer to slice 6 (contradiction watcher); add as `@pytest.mark.skip(reason="slice 6")` placeholder ONE test only
- Model-proposed supersession (deterministic overlap, unrelated objects) → port directly against pass-2's supersession edge logic
- Fact consolidation duplicate-fact supersession → IS pass 2; port directly
- Source trace with related + superseded objects → port against `memory_item_parents` edges
- Memory eval suite precision/recall → port if `MemoryEvalSuite` still exists; otherwise drop and document

**Drop (NOT ported):**
- `KnowledgeObjectRepository.search_entities` + entity graph metadata → entity resolution is deferred to slice 8+
- Entity resolution pipeline (mentions, aliases, candidates, alias collisions) → deferred
- Entity merge/split reversibility → deferred

Document in §12 which of the 14 were ported, which were dropped, and which were skip-marked.

---

## 9. Tests — ≥ 12 cases

`apps/server/tests/memory/test_claim_layer.py` MUST have ≥ 12 test functions. Suggested coverage:

1. `test_run_pass2_produces_claim_from_two_observations_with_shared_entities`
2. `test_run_pass2_skips_singleton_observation_clusters`
3. `test_run_pass2_writes_evidence_edges_for_each_source_observation`
4. `test_run_pass2_idempotent_when_evidence_set_unchanged`
5. `test_run_pass2_supersedes_old_claim_when_evidence_grows_strictly`
6. `test_run_pass2_does_not_supersede_overlapping_but_disjoint_evidence`
7. `test_run_pass2_rejects_no_claim_summary`
8. `test_run_pass2_handles_empty_observation_set`
9. `test_run_pass2_window_days_filters_old_observations`
10. `test_claim_similarity_weights_match_design_spec` (unit test: feed crafted MemoryItems, assert score)
11. `test_entity_overlap_returns_zero_when_either_side_empty`
12. `test_admin_endpoint_dispatches_pass_parameter` (`pass=1`, `pass=2`, `pass="both"` all work)
13. `test_pass2_claim_surfaces_with_claim_match_reason_in_retrieval` (integration)
14. `test_pass2_includes_existing_claims_in_input_set_for_chaining`

Codex picks 12+ from this list and may add their own. Each test must use the slice-4 test patterns (factories, fixtures, `aiosqlite` connection) from `tests/memory/test_pattern_finder.py`.

`apps/server/tests/memory/test_knowledge_next_level_migrated.py` MUST have ≥ 8 ported tests (target 10).

---

## 10. Run-result shape

```python
@dataclass(slots=True)
class PatternFinderPass2RunResult:
    window_days: int
    scope: str
    observations_considered: int
    existing_claims_considered: int
    clusters_found: int
    claims_written: int
    claims_superseded: int
    elapsed_ms: int

    def to_dict(self) -> dict[str, int | str]: ...
```

Symmetric with `PatternFinderRunResult` for pass 1 — same field naming pattern (`_considered`, `_found`, `_written`, `_superseded`, `elapsed_ms`).

---

## 11. Hard gates — codex MUST run ALL of these and paste output

Same shape as slice 4 §11. Codex pastes verbatim output:

1. `cd apps/server && uv run pytest tests/ --co -q 2>&1 | tail -5` → expect `0 errors` in the last line.
2. `cd apps/server && uv run pytest tests/memory/ -q 2>&1 | tail -5` → expect `≥ 69 passed` (57 prior + ≥ 12 new) `, 0 failed`.
3. `cd apps/server && uv run pytest tests/ -q 2>&1 | tail -5` → expect `≥ 844 passed, 0 xfailed` (832 prior + ≥ 12 new − 3 unxfailed = 841+; if only 2 of 3 xfails closed, expect `≥ 843 passed, 1 xfailed`).
4. `cd apps/server && uv run ruff check ntrp/ tests/ 2>&1 | tail -3` → expect `All checks passed!`.
5. `grep -nE 'def search_(text|vector|entities|temporal)' apps/server/ntrp/memory/service.py` → expect `0 lines` (4 dead wrappers gone).
6. `grep -rnE '\.(search_text|search_vector|search_entities|search_temporal)\(' apps/server/ --include='*.py' | grep -v __pycache__ | grep -v test_knowledge_next_level_migrated` → expect `0 lines`.
7. `wc -l apps/server/tests/memory/test_claim_layer.py` → expect `≥ 200 lines`.
8. `grep -c '^async def test_\|^def test_' apps/server/tests/memory/test_claim_layer.py` → expect `≥ 12`.
9. `grep -c '^async def test_\|^def test_' apps/server/tests/memory/test_knowledge_next_level_migrated.py` → expect `≥ 8`.

If ANY gate fails: stop, post the failure to the PM checklist (§12), do NOT commit.

---

## 12. PM checklist for codex's report

Codex's PR/report MUST answer:

1. Did you read `pattern_finder.py` start-to-finish before drafting pass 2? Confirm shape decisions (dataclass naming, helper reuse).
2. Where does the slice-4 scheduler live? Did you extend it or replace it (Option A vs B from §6.1)?
3. Where does the admin endpoint live? How did you wire the `pass` parameter?
4. Which 10 of the 14 `test_knowledge_next_level.py` tests did you port? Which did you drop? Which did you `@pytest.mark.skip`?
5. Did all 3 LongMemEval xfails close, or only 2? If only 2, which one didn't, why, and what's the deferred plan?
6. Paste the output of all 9 gates from §11. No paraphrasing.
7. Any candidate-deletions list (per §2 "MUST NOT delete" rule)?
8. Any cases where you had to touch frozen-zone files? Justify or revert.
9. Final `git diff --stat` against `main` HEAD before the slice 5 commit.

---

## 13. Codex prompt (verbatim — extracted by invoke.sh §11)

```
You are implementing slice 5 of the ntrp memory redesign.

Read `docs/internal/slices/slice-05-claim-layer.md` start to finish, then:
1. Read `docs/internal/slices/slice-04-pattern-finder.md` for voice and prior-slice conventions.
2. Read `apps/server/ntrp/memory/pattern_finder.py` start to finish — your pass 2 code must live alongside pass 1 without disturbing it.
3. Read `apps/server/ntrp/memory/prompts/pass1.txt` for prompt shape.
4. Read `apps/server/tests/memory/test_pattern_finder.py` for test patterns (fixtures, factories, async conventions).
5. Read `docs/internal/ntrp-memory-redesign-spec.md` §2.5 (claim) + §3.3 (pattern finder) + §3.7 (confidence).
6. Read `docs/internal/slices/slice-07-backlog.md` §1, §2A, §3A in full.

Implement everything in §1-§10 of the brief. Run every gate in §11. Answer every question in §12. Pay strict attention to the frozen zones in §2 — touching anything listed there is a fail.

Commit only when all 9 gates green. Commit message:
  feat(memory): slice 5 — pattern finder pass 2 (observation → claim)

Body: 5-7 lines summarizing what landed + the 3 absorbed backlog items + gate counts.

Do NOT push. Do NOT touch frozen zones. Do NOT refactor pass 1. Do NOT delete files beyond the 4 `search_*` wrappers explicitly authorized in §3A. If you encounter ambiguity, ASK in the PM checklist response (§12) instead of guessing.
```

---

## 14. Sequence of work — codex's plan

1. **Read phase** (no code yet): all 6 prereq files above. Take notes.
2. **Skeleton**: add `ClaimDraft`, `PatternFinderPass2RunResult` dataclasses to `pattern_finder.py`. Stub `run_pass2`, `cluster_observations`, `summarize_observation_cluster`, `render_pass2_prompt`, `_persist_claim`. Wire imports.
3. **Prompt**: write `pass2.txt` per §4.1.
4. **Clustering**: implement `claim_similarity`, `_entity_overlap`, `cluster_observations` per §3.
5. **Persistence**: implement `_persist_claim` + supersession-edge logic per §5.
6. **Endpoint + scheduler**: wire `pass` parameter + scheduler per §6.
7. **Retrieval label**: add `'claim_match'` reason in `retrieval.py` per §2.
8. **Backlog §3A**: delete 4 dead wrappers. Run verification greps.
9. **Backlog §1**: unxfail the 3 LongMemEval tests; fix `longmemeval.py:224`.
10. **Backlog §2A**: port 10+ tests from `test_knowledge_next_level.py` into `test_knowledge_next_level_migrated.py`.
11. **Tests**: write ≥ 12 cases in `test_claim_layer.py` per §9.
12. **Gates**: run all 9 from §11. Paste output.
13. **Report**: answer §12 checklist. Commit.

---

## 15. Out of scope explicitly

- **Contradiction watcher** — slice 6. Supersession edges from pass 2 are written, but no cross-claim conflict detection yet.
- **Skill inducer + `is_toolable`** — slice 7. Claims with `metadata.is_toolable=True` are NOT marked yet.
- **Entity resolution** — deferred to slice 8+. The dropped sub-tests from `test_knowledge_next_level.py` stay dropped.
- **Retrieval ranking changes** — slice 5 only adds the `'claim_match'` reason label. Score formula, top-K, recency-weighting all untouched.
- **`knowledge/fact_consolidation.py` deletion** — leave the file in place. Deprecation comment only. Removal is post-slice-7.
- **Desktop UI for claims** — post-slice-7.
- **External-connector claim short-circuits** (spec §3.3 mentions calendar→claim direct) — slice 8+.

---

## 16. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pass 2 LLM emits "NO_CLAIM" too often → no claims ever written | Medium | High (slice useless) | Threshold tuning via env var; gate test #7 catches universal rejection; PM can lower threshold post-commit. |
| Including existing claims in input set creates infinite supersession chains | Low | High | Idempotency check on evidence set; supersession only triggers on **strict** superset, not equal-or-superset. |
| `_entity_overlap` returns 0 too often because entity extraction in pass 1 was sparse | Medium | Medium | Pass-2 threshold weights `_entity_overlap` at only 0.20 — clustering still works on cosine + tag alone. |
| LongMemEval xfail #1 (`semantic_alias_match`) can't close because real alias-matching is slice 8+ | Medium | Low | Document in §12; either rewrite test to accept `'claim_match'` or leave 1 xfail in place (update gate count). |
| Dead-wrapper grep finds an unexpected caller (e.g. in a test we forgot) | Low | Medium | §11 gate 6 catches this; codex stops and reports. |
| Resurrected `test_knowledge_next_level_migrated.py` discovers bugs in slice 3/4 retrieval | Medium | Medium | Treat as out-of-scope: skip the failing tests with `@pytest.mark.skip(reason="slice 5 follow-up: <description>")` and add an entry to `slice-07-backlog.md`. |
| `pattern_finder.py` grows past 600 lines | Medium | Low | §2 allows split into `pattern_finder_pass2.py` with re-export shim. |
| Scheduler regressions break slice 4 daily run | Low | High | If extending the slice-4 scheduler, run pass 1 alone first as a smoke check; gate test #3 catches DB-level breakage. |

---

## 17. Repo-surface audit (2026-05-28 05:20 — post-draft correction)

Audited `apps/server/ntrp/memory/items_store.py` and `pattern_finder.py` after drafting v1 of this brief. Findings that corrected the brief:

### What the repo actually has

`MemoryItemsRepository` public API:
- `embedding_dim() -> int | None`
- `list_recent_items(*, kind, window_days, limit, scope) -> list[MemoryItem]`
- `insert_item(MemoryItemInsert, *, commit=True) -> str`
- `insert_parent_edge(child_id, parent_id, role, order=None, *, commit=True) -> None`
- `list_parent_edges(child_id) -> list[MemoryItemParent]`

That is the entire surface. No `get_item`, no `set_status`, no `update_metadata`, no `add_parent`, no entity lookup.

`MemoryItem` columns:
- `id, kind, content, provenance, source_refs, confidence, status, valid_from, invalid_at, scope, tags, artifact_ref, usage, feedback, created_at, updated_at, embedding`

**No `metadata` JSON column. No `entities` field.** The brief's v1 references to `metadata` and `entities` were invented; v2 (this rev) removes them.

`MemoryItemInsert` defaults: `confidence` is required, `provenance="inferred"`, `status="active"`, `usage`/`feedback` zero-init dicts, `source_refs=list[dict]`, `tags=list[str]`.

### What slice 5 must NOT add

- A `metadata` JSON column on `memory_items` — schema migration is its own slice.
- A `set_status` repo method — slice 4 already does status flips via raw SQL inside `_persist_observation`; pass 2 mirrors that pattern.
- Entity-specific repo queries — defer to slice 8+.

### What slice 5 MAY add

- `_pass2_threshold_from_env()` helper next to `_threshold_from_env()` in `pattern_finder.py`.
- Optional `status` kwarg on `list_recent_items` (default `'active'`) IF codex finds it cleaner than Python-side filtering. Document either way in §12.
- A generalization of `_existing_observation_evidence` → `_existing_evidence(repo, *, kind, ...)` with a back-compat wrapper (already authorized in §3.5).

### Carry-forward to slice 6 + 7 briefs

Slices 6 and 7 (already committed at `311ecd9b`) reference `add_parent`, `set_status`, `update_metadata`, `update_metadata_key`, `count_parents`, `get_evidence_chain`, `list_items_by_entities`, `update_metadata` — none of which exist. Those briefs will need a similar v2 pass before fire. **Do not fire slice-06-invoke.sh or slice-07-invoke.sh as currently committed.** Open question logged for the user.

---

**End of brief.**
