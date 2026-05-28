# Slice 7+ backlog — work owed by earlier slices

**Status:** Captured 2026-05-28 immediately after slice 3 commit `64f0ef24`.
**Owner:** PM (this file is the durable home for deferred work).

This is not a slice brief — it's a tracking doc. Each item lists what was
deferred, where it lives, the verification path, and the slice (per the
spec build order in `ntrp-memory-redesign-spec.md` §7) that probably absorbs
it. Items get re-homed into the actual slice briefs when those slices fire.

---

## Labeling correction

Throughout slice 3, I wrote "slice 7" in xfail strings and commit messages
to mean "the future slice that rebuilds fact consolidation + reason labels."
**That was wrong.** Per the spec §7 build order:

- **Slice 4** = Pattern finder pass 1 (`episode → observation`)
- **Slice 5** = Pattern finder pass 2 (`observation/claim → claim`) — this
  is where fact consolidation lives
- **Slice 6** = Contradiction watcher
- **Slice 7** = Skill inducer + `is_toolable` gate
- **Slice 8/9** = UX
- **Slice 10** = External connectors

The xfail strings + commit message in `64f0ef24` say "slice 7" but mean
"slice 5 (fact consolidation rebuild)" for items 2A–2C below. **Do not
re-label until we land slice 5 and verify** — premature renaming creates
its own confusion. Just know it when you read those strings.

---

## 1. LongMemEval xfails (3 tests) — slice 5

Location: `apps/server/tests/test_longmemeval_benchmark.py`

| Test | xfail reason in code | Real owner |
|------|---------------------|------------|
| `test_longmemeval_semantic_alias_retrieves_named_streaming_service` | `slice 7: semantic_alias_match reason label not implemented in MemoryRetrieval yet` | slice 5 |
| `test_longmemeval_extracted_variant_uses_turn_fact_candidates` | `slice 7: object_type=fact candidate labels deferred to fact consolidation rebuild` | slice 5 |
| `test_longmemeval_extracted_variant_can_use_model_episode_extraction` | `slice 7: model-extracted memory ingestion deferred per longmemeval.py:224` | slice 5 |

**What needs to happen:**

1. `MemoryRetrieval` needs richer reason labels beyond `fts_match` /
   `vector_match`. At minimum: `semantic_alias_match` (entity alias hit),
   plus whatever pass-2 claim consolidation produces.
2. `memory_item.kind=claim` rows produced by pass 2 need to surface as
   `object_type=fact` candidates (or we update the test to assert on the
   new label — TBD when slice 5 lands).
3. `ntrp/benchmarks/longmemeval.py:224` raises `RuntimeError("model-extracted
   LongMemEval memories are deferred after the memory_items retrieval
   swap")`. This is a deliberate marker. Lit back up by re-implementing
   `_ingest_model_extracted_memories` against the slice-4 episode-close
   extraction pipeline.

**Verification when slice 5 ships:** remove the 3 xfail decorators; expect
9 → 12 passed in `test_longmemeval_benchmark.py`.

---

## 2. Deleted test files — slice 5 (fact consolidation) + slice 7 (write gate)

### 2A. `tests/test_knowledge_next_level.py` (14 tests) — slice 5

Recoverable: `git show 64f0ef24~1:apps/server/tests/test_knowledge_next_level.py`

Covered:
- `KnowledgeObjectRepository.search_entities` + entity graph metadata
- Entity resolution pipeline (mentions, aliases, candidates, alias collisions)
- Entity merge/split reversibility
- Knowledge object backfill embeddings
- Procedure candidate → lesson promotion
- Semantic conflict routing
- Model-proposed supersession (deterministic overlap, unrelated objects)
- Fact consolidation duplicate-fact supersession
- Source trace with related + superseded objects
- Memory eval suite precision/recall

**Re-home plan when slice 5 fires:**
1. Migrate the 14 tests to `tests/memory/` against the new `memory_items`
   surface (where applicable).
2. Drop the entity-resolution sub-tests that depended on the old
   `KnowledgeObjectRepository.search_entities` API — slice 5 should decide
   whether entity resolution comes back or is genuinely cut.
3. Restore `MemoryEvalSuite` (or replacement) against `memory_items`.

### 2B. `tests/test_knowledge_write_gate.py` (30 tests, 29 dead) — slice 7

**NOT recoverable from git** (was untracked when deleted). Source module
`apps/server/ntrp/knowledge/write_gate.py` still exists untracked. If you
need the test file back, check your IDE's local history / Time Machine /
git stash before relying on this doc.

Covered (inferred from grep + module surface):
- Workflow cluster discovery from repeated tool usage
- Workflow cluster candidate body capping
- Workflow cluster review markers (rejection, promotion blocking)
- Episode legacy-type normalization to `lesson`
- Unsourced/legacy durable candidate routing
- Invalid source-ref → review routing
- Duplicate/conflict → review routing
- Direct create/update legacy + unsourced gating

**Re-home plan when slice 7 fires (skill inducer):**
The write-gate logic gated old `KnowledgeObject` writes. Slice 7's skill
inducer produces `memory_item.kind=skill` rows with `kind=proposal`
intermediaries. The write-gate role transforms into the proposal-acceptance
gate. Rewrite tests against the new flow, don't restore the old file.

### 2C. `tests/memory/test_facts_store.py` + `tests/memory/test_observations_store.py` — DELETION UNSTAGED 2026-05-28 03:40

**Earlier claim ("deleted in slice 1, no action needed") was wrong.**
Verified via `git ls-tree HEAD`: both files still exist as blobs at HEAD,
deletion is **working-tree only**.

```
$ git status apps/server/tests/memory/
 D apps/server/tests/memory/test_facts_store.py
 D apps/server/tests/memory/test_observations_store.py
?? apps/server/tests/memory/test_pattern_finder.py
?? apps/server/tests/memory/test_slice01_schema.py
```

The intended replacement (`test_slice01_schema.py`) is also untracked.

**Fresh-clone consequence:** Both old test files reappear on `git clone`.
They import deleted facts/observations APIs and will fail to collect.
This is a second flavor of the §3B HEAD-is-broken problem.

**Fix shape (bundle with §3B commit):**

```bash
git rm apps/server/tests/memory/test_facts_store.py
git rm apps/server/tests/memory/test_observations_store.py
git add apps/server/tests/memory/test_slice01_schema.py
git commit -m "fix(tests): stage slice 1 test cleanup (deletes + new schema test)"
```

The slice 4 codex run, executing gates on this local tree, won't surface
this because the files are already missing locally. **Fresh-clone CI
would catch it.**

---

## 3. Dead code landmines

### 3A. `memory/service.py` `search_*` wrappers — VERIFIED DEAD 2026-05-28 03:34

**Actually 4 dead wrappers, not 1.** All call non-existent
`KnowledgeObjectRepository` methods AND have zero callers in the codebase.

| Wrapper (memory/service.py) | Line | Calls | Callers |
|------|-----:|-------|--------:|
| `search_text` | 1354 | `self._repo.search_text(...)` (not defined) | 0 |
| `search_vector` | 1371 | `self._repo.search_vector(...)` (not defined) | 0 |
| `search_entities` | 1387 | `self._repo.search_entities(...)` (not defined) | 0 |
| `search_temporal` | 1397 | `self._repo.search_temporal(...)` (not defined) | 0 |

Verified empirically:

```bash
grep -nE 'def search_' apps/server/ntrp/knowledge/store.py
# (no output — none of these methods exist on the repo)

grep -rnE '\.(search_text|search_vector|search_entities|search_temporal)\(' \
  apps/server/ntrp/ | grep -v memory/service.py
# (no callers anywhere)
```

These are 100% dead — safe to delete in slice 5 with no semantic change.
The earlier note that "no test exercises this path" was correct but
understated: **nothing at all exercises this path**.

**Verification after fix:** `grep -nE 'def search_(text|vector|entities|temporal)' apps/server/ntrp/memory/service.py`
should return 0 lines.

### 3B. Untracked knowledge modules — HEAD IS BROKEN — verified 2026-05-28 03:32

**Earlier draft of this section was wrong.** I claimed these modules
"wouldn't even import" because slice 3 deleted their dependencies. Verified
empirically: **all 11 import cleanly** and **are wired into committed code**.

The actual situation is worse than "open question."

Files untracked on disk:

- `ntrp/knowledge/conflict_reviews.py`
- `ntrp/knowledge/corrections.py`
- `ntrp/knowledge/fact_consolidation.py` (250 lines)
- `ntrp/knowledge/health.py`
- `ntrp/knowledge/metadata.py`
- `ntrp/knowledge/review_promotions.py`
- `ntrp/knowledge/similarity.py`
- `ntrp/knowledge/skill_promotions.py` (1001 lines)
- `ntrp/knowledge/usage_events.py`
- `ntrp/knowledge/workflow_lifecycle.py`
- `ntrp/knowledge/write_gate.py` (436 lines)

Plus untracked tests covering them.

#### Verified import wiring (committed HEAD)

```
apps/server/ntrp/memory/service.py            (HEAD-committed) imports:
  - KnowledgeConflictReviewService    from ntrp.knowledge.conflict_reviews
  - KnowledgeFactConsolidationService from ntrp.knowledge.fact_consolidation
  - KnowledgeReviewPromotionService   from ntrp.knowledge.review_promotions
  - KnowledgeWriteGate, KnowledgeWriteGateService from ntrp.knowledge.write_gate

apps/server/ntrp/server/routers/knowledge.py  (HEAD-committed) imports:
  - skill_promotions, usage_events

apps/server/ntrp/knowledge/processors.py      (WORKING-TREE-MODIFIED) imports:
  - workflow_lifecycle  (via skill_promotions)
```

#### HEAD is broken without these files

Verified by stashing untracked + working tree: with the 11 files missing,
`memory/service.py` cannot import. **The HEAD commit `64f0ef24` landed
import lines without committing the target files.** Anyone cloning at HEAD
gets an import-error server.

#### What to do

This is **not** a slice 5 PM decision anymore. This is a "fix HEAD" task:

1. **Verify the modules are correct** — read them, check tests pass.
2. **Commit them** as a fixup to `64f0ef24` (or new commit) — title:
   `fix(knowledge): commit modules referenced by memory/service slice 3 imports`.
3. The untracked tests should be reviewed at the same time — if they pass,
   commit; if they're WIP, mark xfail or delete.

#### Why this matters for the slice 4 plan

Slice 4 pattern finder doesn't depend on these modules directly — but if
any slice-4 verification step boots the server, it'll surface the
broken-HEAD condition (or quietly hide it because the files exist locally
on this machine). The user should commit-or-decide before running
clean-clone integration tests.

**This is now the highest-priority backlog item** — every other item
assumes HEAD is buildable on a fresh clone. It currently isn't.

**See also §2C** — there's a *second* HEAD-breakage: two test files
exist at HEAD but are deleted in the working tree. A clean clone gets
broken tests trying to import deleted APIs. Fix shape: bundle the §2C
`git rm` commit with the §3B `git add` commit.

**Action when slice 4 finishes:** raise this with the user as a blocking
fixup before slice 5 starts.

---

## 4. Slice 2 — token-counter anomaly — ROOT CAUSE FOUND 2026-05-28

`episode_buffers.tokens` is wildly wrong. Original anomaly: 546k tokens
on one episode. After more data accumulated, observed values are far worse
(see SQL snapshot below).

### Observed in production DB (2026-05-28 03:28)

```sql
SELECT id, turn_count, tokens, length(content_so_far) AS content_len
FROM episode_buffers ORDER BY tokens DESC LIMIT 5;
```

| id (prefix) | turn_count | tokens | content_len |
|-------------|-----------:|-------:|------------:|
| b72ef7… | 6 | **3,294,785** | 11,582 |
| fe753a… | 5 | **2,470,333** | 9,000 |
| 7f52d6… | 6 | **2,343,122** | 10,059 |
| f59209… | 4 | **1,227,514** | 6,351 |
| 2cf089… | 6 | **1,166,745** | 9,585 |

Expected token count for ~10k chars of conversation: ~2-3k tokens
(4 chars/token rule). Observed: 1-3M. **Off by ~1000×.**

### Root cause — `memory/connectors/chat.py:72`

```python
turn = TurnUpdate(
    content=content,
    tokens=max(0, event.usage.total_tokens),  # ← BUG
    ...
)
```

`event.usage.total_tokens` is the **LLM API's cumulative session token
count** (prompt + completion + full conversation history). It is NOT a
per-turn delta. Each turn adds the entire running conversation total to
the buffer, so the buffer accumulates a roughly-quadratic running sum.

Math sanity:
- Turn 1: response says total_tokens=10000 (prompt 8k + completion 2k)
- Turn 2: total_tokens=25000 (now includes turn 1 in the prompt)
- Turn 3: total_tokens=50000
- Real per-turn delta tokens: 10k + 15k + 25k = 50k
- What we store: buffer.tokens = 10k + 25k + 50k = **85k** (1.7× too high after 3 turns)

After 6 turns with long prompts, the multiplier balloons to ~250-400×
content length — exactly the 1-3M / 10k pattern we see.

### Fix shape (slice 5 or a focused fixup)

Use the per-turn token delta, not the cumulative total. Options:

1. **`completion_tokens` only** (simplest, mostly-right): only counts the
   LLM's response tokens for this turn. Misses the user message tokens
   from the new turn but those are small. ~5% under-count, acceptable.
2. **Tokenize the new content directly** (most correct): `len(tokenizer.encode(content))`.
   Decouples from LLM API quirks. ~5ms extra per turn.
3. **Compute delta**: track the previous turn's `total_tokens` in the
   buffer, store `event.usage.total_tokens - buffer.last_total_tokens`.
   Requires schema add (`last_total_tokens INTEGER`) and migration.

**Recommendation: (2)** — most correct, decouples from API quirks, the
tokenizer is already a dependency for embedding.

### Risk while unfixed

`episode_close.py:52` triggers a close when `buffer.tokens + turn_tokens
>= TOKEN_BUDGET=8000`. With cumulative token counts (the bug), turn 2 of
any session would already exceed 8k — except for one mitigating factor.

**Mitigation in chat path only**: `_explicit_close` (chat.py:81) is
checked first. For chat sessions that emit explicit-close signals at
session end, episodes finalize on the explicit path before the broken
token budget fires (verified empirically — see "Slice 4 implications"
below).

**Risk remains for non-chat sources**: any future connector that doesn't
have an `_explicit_close` equivalent will hit the inflated TOKEN_BUDGET
on turn 2 and ship tiny single-turn episodes.

**Risk remains for chat sessions without explicit close**: chat sessions
that drop without an explicit close (process kill, network drop, etc.)
will sit forever in the buffer until `IDLE_GAP` fires (10min). That's
fine in practice but worth knowing.

### Slice 4 implications — CORRECTED DIAGNOSIS 2026-05-28 03:42

Sampled all 42 `kind='episode'` rows from production memory.db:
- All 42 episodes have **exactly 6 source_refs** (suspiciously consistent)
- Content size 700-1100 chars per episode

**Earlier draft attributed this to `_explicit_close`. That was wrong.**
`_explicit_close` (chat.py:113) is an LLM-driven topic-shift classifier,
not a session-end signal. It can't explain the rigid 6-turn pattern.

**Actual cause — interaction of OVERLAP_TURNS + token bug:**

1. `_overlap_carry` (episode_close.py:112): when an episode closes, the
   **last 5 turns are carried** into the next buffer (`OVERLAP_TURNS=5`),
   and the carry sets `tokens=0`.
2. Token bug: turn 1 of the next buffer adds `event.usage.total_tokens`
   (cumulative session count, ~5-15k after a few turns of conversation).
3. `evaluate_triggers` (episode_close.py:52): `0 + (>8000) >= 8000` →
   **token_budget close fires after just 1 new turn**.
4. Net effect: episode = 5 carried + 1 new = **6 source_refs**, every time.

The 6-turn pattern is a **structural artifact of the token bug**, not
evidence the system is working as designed. Real intent was probably
20-50 turn episodes (TURN_BUDGET=50, OVERLAP_TURNS=5).

**Slice 4 implications:**
- Episodes ARE multi-turn (6 turns each), so clustering will produce
  meaningful patterns — slice 4 has usable data.
- But episodes are **shorter than designed** (~6 turns vs ~20-50 intended),
  so pattern-finder summaries will be more granular and clustering
  thresholds may need tuning.
- The 5-turn overlap means consecutive episodes share 5/6 = 83% of their
  source_refs. Slice 4 clustering may over-merge consecutive episodes
  based on this shared evidence. **Worth a sanity check post-slice-4:**
  count clusters that contain >50% overlapping source_refs.

**Slice 4 is safe to proceed** with this caveat. The token-bug fix is
needed for episodes to reach their intended size, which would in turn
make pattern clustering more meaningful.

### Verification when fixed

```bash
# Open a fresh chat, send 5 turns, force episode close (or wait)
sqlite3 ~/.ntrp/memory.db 'SELECT turn_count, tokens, length(content_so_far) FROM episode_buffers ORDER BY started_at DESC LIMIT 3'
# Expect: tokens roughly equal to content_len / 4 (e.g. 10k chars → ~2500 tokens)
```

---

## 5. Slice 3 — naive §12 grep gate (PM lesson)

Slice 3 brief §12 grep verification was naive — it only checked for the
class names (`ActivationBundle`, etc.) but not for the import paths
(`from ntrp.knowledge.activation`). The first codex pass passed the §12
gate while still leaving 4 test collection errors from dead imports.

**Fix for future slice briefs:** every brief that deletes a module must
include in its verification gate:

1. `grep -rn 'from <deleted_module>\b' apps/server/ --include='*.py'` → 0
2. `pytest --co -q` → 0 collection errors (proves no test imports a dead module)
3. `ruff check ntrp/ tests/` → "All checks passed!" (catches F811 dupes
   and orphan imports)

Slice 3 brief was missing (1) and (2). Slice 4 brief draft should include
both as hard gates.

---

## Re-home log

When a slice absorbs an item from this doc, move it from here to the slice
brief and check it off below.

- [x] §1 LongMemEval xfails → slice 5 (commit `7aeb3d82`, all 3 xfails removed; LongMemEval now handles `claim`/`fact` candidate kinds)
- [x] §2A `test_knowledge_next_level.py` → slice 5 (commit `7aeb3d82`, ported as `tests/memory/test_knowledge_next_level_migrated.py`, 1 placeholder skipped pending slice-6 follow-up)
- [x] §2B `test_knowledge_write_gate.py` → slice 7 (commit `d6292ac4`, 28 new tests across `test_skill_inducer.py` + `test_proposal_flow.py` cover cluster discovery, body/evidence capping, review markers, promotion blocking, unsourced rejection, missing draft routing, duplicate proposal skip, slug collision, direct promote to skill, source claim refs, reject cleanup; dropped old `lesson` normalization + legacy direct create/update gating per spec)
- [x] §3A `_repo.search_*` landmine → slice 5 (commit `7aeb3d82`, 4 dead wrappers removed from `memory/service.py`, stale internal caller fixed)
- [x] §3B 11 untracked knowledge modules → resolved 2026-05-28 in HEAD-cleanup commits before slice 5; working tree clean, knowledge/ matches imports
- [x] §4 episode_buffers token anomaly → token-counter fix `3b66a043`, audit log `ba38b6ca` (per-turn delta, not cumulative)
- [x] §5 PM grep-gate lesson → slice 4 brief incorporated; carried forward into v2 slice-5/6/7 briefs (repo-surface audit §17)

**Final state 2026-05-28:** all 7 items closed. Slice 5 (`7aeb3d82`), Slice 6 (`7c457b34`), Slice 7 (`d6292ac4`) land the full pipeline `episode → observation → claim → resolved-claim → skill-proposal → skill-file`.

**Known follow-ups (not blockers):**
- `test_knowledge_next_level_semantic_conflict_routing_deferred_to_slice_6` (test_knowledge_next_level_migrated.py) remains `@pytest.mark.skip(reason="slice 6: contradiction watcher owns semantic conflict routing")` despite slice 6 landing. Body is empty (`assert conn`). Either unskip + flesh out, or delete. Logged for slice 8+.
- Slice 7 ships degraded `determinism` + `success_signal` gates (stubbed `True`) per `slice-07-skill-inducer.md §17` audit log. Future "memory-metadata-column" slice unlocks full spec §3.5 gate via `MemoryItem.metadata`.
