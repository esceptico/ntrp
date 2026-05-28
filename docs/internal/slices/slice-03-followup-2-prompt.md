# Slice 3 — follow-up cleanup pass #2

You are finishing the slice 3 memory retrieval cleanup. Slice 3 swapped the
`KnowledgeActivationService` for `MemoryRetrieval` over `memory_items`. The first
two passes shipped the new retrieval and removed the dead activation cluster,
but left the working tree with **46 test failures (vs 14 baseline)** and **22
ruff errors (vs 0 baseline)**. Your job is to drive both back to baseline
without touching the slice 3 implementation.

## Hard constraints

- **DO NOT touch:**
  - `apps/server/ntrp/memory/retrieval.py`
  - `apps/server/ntrp/memory/activation.py`
  - `apps/server/ntrp/memory/facts.py`
  - `apps/server/ntrp/memory/connectors/`
  - `apps/server/tests/memory/`
  - `apps/desktop/`
- **Allowed to touch** (relaxed from previous pass):
  - `apps/server/ntrp/memory/service.py` — only to remove duplicate
    `count_by_type_and_status` definitions
  - `apps/server/ntrp/knowledge/store.py` — only to remove duplicate
    `count_by_type_and_status` definitions
  - everything else under `apps/server/ntrp/` and `apps/server/tests/`
    needed for the buckets below
- Run all gate commands yourself before reporting done.
- The goal is **gate parity**, not preserving every test. Deleting dead-surface
  tests is encouraged and explicit below.

## Bucket A — Delete dead `knowledge_objects` test files (43 failures)

The old `KnowledgeObjectRepository` + `knowledge_objects` table is being
replaced by the `memory_items` retrieval surface. Slice 7 will rebuild this
cluster. For now, the entire surface is dead and the tests can't run.

1. **Delete** `apps/server/tests/test_knowledge_write_gate.py`
   - 30 tests, 29 failing with `sqlite3.OperationalError: no such table:
     knowledge_objects`. The 1 passing test is incidental (tests legacy episode
     normalization that no longer has a consumer).
2. **Delete** `apps/server/tests/test_knowledge_next_level.py`
   - 15 tests, 14 failing with the same `knowledge_objects` table error. The
     1 passing test (`test_knowledge_object_repository_round_trips_links_and_supersession_chain`)
     is also dead-surface; delete the whole file.
3. After deletion, run `pytest tests/ --co -q` to confirm collection still
   succeeds and the missing tests are gone (expected: ~822 collected vs 865
   currently).

## Bucket B — xfail the 3 LongMemEval failures (slice 7 reasons)

`tests/test_longmemeval_benchmark.py` has 3 failures driven by reason-label
drift in the new retrieval. **Do NOT delete the file** — the 9 passing tests are
valuable retrieval coverage. Mark each failure with
`pytest.mark.xfail(reason=...)` so the suite reports `xfailed`, not `failed`.

1. `test_longmemeval_semantic_alias_retrieves_named_streaming_service`
   - Reason: `'semantic_alias_match' in trace["candidates"][0]["reasons"]`
     fails because `MemoryRetrieval` only emits `fts_match`/`vector_match`.
   - xfail reason: `"slice 7: semantic_alias_match reason label not implemented
     in MemoryRetrieval yet"`
2. `test_longmemeval_extracted_variant_uses_turn_fact_candidates`
   - Reason: `object_type == "fact"` candidate filter; new retrieval surfaces
     `memory_item` rows without that label.
   - xfail reason: `"slice 7: object_type=fact candidate labels deferred to
     fact consolidation rebuild"`
3. `test_longmemeval_extracted_variant_can_use_model_episode_extraction`
   - Reason: `RuntimeError` deliberately raised in
     `ntrp/benchmarks/longmemeval.py:224` ("model-extracted LongMemEval
     memories are deferred after the memory_items retrieval swap").
   - xfail reason: `"slice 7: model-extracted memory ingestion deferred per
     longmemeval.py:224"` — also add `strict=False` so the deferred path can
     be lit back up without churn.
   - **Leave the `raise RuntimeError` in `longmemeval.py:224` as-is** — it's
     the deferred-marker; the xfail makes the test honest about it.

## Bucket C — Ruff (22 errors → 0)

Baseline is "All checks passed!". Restore that.

1. **F811 duplicates** (2 errors) — these are slice 3 additions that left the
   old method in place:
   - `apps/server/ntrp/knowledge/store.py`: two
     `count_by_type_and_status` definitions (lines 161 and 864). Keep the
     **newer dict-of-dict signature** (`dict[str, dict[str, int]]` at line 864)
     and delete the older `dict[tuple[...], int]` at line 161 — verify callers
     by `grep -rn 'count_by_type_and_status' apps/server/ntrp` first and
     migrate any tuple-key consumer.
   - `apps/server/ntrp/memory/service.py`: same dupe at lines 1354 / 1829.
     Same rule — keep `dict[str, dict[str, int]]`, drop the tuple-key version.
2. **E402** (5 errors) — `apps/server/tests/test_skills.py` has imports at
   lines 178–183 mid-file. Move them all to the top of the file with the
   other imports.
3. **I001 + UP035** (14 auto-fixable) — run `ruff check ntrp/ tests/ --fix`
   from `apps/server/` to clean these up. Do not pass `--unsafe-fixes`.
4. Final gate: `cd apps/server && .venv/bin/ruff check ntrp/ tests/` must
   print exactly `All checks passed!`.

## Verification — run ALL of these and paste the output in your report

```
cd apps/server
.venv/bin/pytest tests/ --co -q 2>&1 | tail -5
.venv/bin/pytest tests/memory/ -q 2>&1 | tail -5
.venv/bin/pytest tests/ -q 2>&1 | tail -10
grep -rn 'ActivationBundle\|ActivationRequest\|ActivationCandidate\|ActivationSelectionTrace\|ActivationRecallBundle' ntrp/ --include='*.py' | grep -v MemoryActivation
grep -rn 'from ntrp.knowledge.activation\b\|KnowledgeActivationService' . --include='*.py'
.venv/bin/ruff check ntrp/ tests/ 2>&1 | tail -5
```

## Expected gate results

1. Collection: ~822 collected, 0 errors
2. tests/memory/: 42 passed
3. Full suite: **0 failed**, ~819 passed, 3 xfailed (the LongMemEval trio).
   If you see >0 failures, stop and investigate — don't paper over.
4. Activation grep: empty
5. Activation/KnowledgeActivationService grep: empty
6. Ruff: `All checks passed!`

## Out of scope (do not touch)

- The dead `_repo.search_entities` / `search_*` wrappers in `memory/service.py`
  — leave them. Slice 7 or a separate cleanup will handle.
- Restoring `semantic_alias_match` / `object_type=fact` reason labels — slice 7.
- The slice 2 `episode_buffers.tokens=546940` anomaly — separate issue.
- Schema migration v31 — leave as-is. The deleted tests were testing the old
  schema; v31 is correct for slice 3.

When all 6 gates are green, report **done** with the verification output and
the list of files modified/deleted. If a gate fails, stop and report the
failure — do not push past red.
