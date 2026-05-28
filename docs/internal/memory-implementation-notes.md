# Memory Implementation Notes

Date: 2026-05-24

## Current phase

Implementing the roadmap in `docs/internal/memory.md` with the smallest safe backend slice first: fact consolidation proposal plumbing before any destructive/automatic merge behavior.

## Decisions / tradeoffs

- Start with backend-only duplicate/near-duplicate proposal generation for active facts, not UI and not automatic merging. Reason: the doc explicitly says conflicts should route to review and supersession should use existing fields; a proposal layer lets us inspect clusters without mutating live memory.
- Reuse the existing supersession model/commit path where possible instead of inventing a separate merge table in this first pass. If the UI later needs durable review items, we can add a review-object representation after the proposal quality is known.
- Keep consolidation scoped to `fact` for the first pass. Lessons/artifacts have different semantics and are easier to over-merge.
- Canonical/source rollup is treated as proposal metadata first. Actual source rollup onto the canonical object should happen only when a merge/supersession is approved.
- Extend existing health reporting for roadmap quality gates instead of creating a separate eval runner yet. Tradeoff: this gives cheap always-on counts, but deeper contradiction/usefulness sampling still needs a later offline/LLM-assisted eval.
- Put the first UI affordance in the existing Review pane rather than adding a new Memory tab. Reason: duplicate merge/supersede is review behavior, and reusing Review avoids inventing another navigation surface before proposal quality is proven.

## Caveats / follow-ups

- The latest backend episode guard still needs the user to restart/reload the server before it protects live future episode creation. Do not restart it from the agent.
- Existing unrelated working-tree changes are present; avoid touching them.

## Implementation log

- Added proposal-only fact consolidation plumbing:
  - `KnowledgeFactConsolidationProposal`
  - `KnowledgeFactConflictProposal`
  - `KnowledgeFactConsolidationResult`
  - `KnowledgeObjectService.propose_fact_consolidation(...)`
  - read-only API endpoint: `GET /knowledge/facts/consolidation`
- The first heuristic is intentionally conservative: active facts only, lexical/synonym token overlap, shared source/entity bonus, semantic-conflict pairs excluded from duplicate clusters.
- Proposal generation does not mutate live memory. Added an explicit commit method that:
  - preflights all duplicate supersessions before mutating to avoid partial merges when a proposal is invalid;
  - commits via the existing supersession path;
  - rolls duplicate/canonical source IDs onto the canonical fact;
  - records a bounded `fact_consolidations` metadata history on the canonical fact.
- Added health counters for roadmap quality gates:
  - active legacy objects (`entity_profile`, `pattern`, legacy `procedure`, active `procedure_candidate`);
  - active tool-looking episodes;
  - episode-extracted facts/lessons/artifacts without episode source ids;
  - duplicate fact clusters from the proposal engine.
- Added manual UI review for fact consolidation:
  - Review pane now fetches consolidation proposals alongside draft review items;
  - shows canonical fact, duplicate facts, confidence, source/evidence counts, and conflicts held out;
  - `Merge duplicates` calls the commit endpoint, which supersedes duplicate facts and rolls sources onto the canonical fact.

## Verification log

- `uv run pytest tests/test_knowledge_next_level.py::test_fact_consolidation_proposes_duplicate_fact_supersession -q` — passed after adding commit/source-rollup coverage.
- `uv run pytest tests/test_knowledge_next_level.py -q` — 15 passed before commit method.
- `uv run pytest tests/test_knowledge_activation.py tests/test_knowledge_next_level.py -q` — 71 passed after consolidation commit + health counters and again after adding the commit API endpoint.
- `uv run ruff check ntrp/knowledge/models.py ntrp/knowledge/__init__.py ntrp/knowledge/processors.py ntrp/memory/service.py ntrp/server/routers/knowledge.py tests/test_knowledge_activation.py tests/test_knowledge_next_level.py` — passed after consolidation commit + health counters and again after adding the commit API endpoint.
- `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` — passed after Review-pane consolidation UI.
- `npx -y node@22.12.0 $(which npm) run build` — passed after Review-pane consolidation UI; existing Vite large-chunk warnings remain.
- `git diff --check -- apps/server/ntrp/knowledge/models.py apps/server/ntrp/knowledge/__init__.py apps/server/ntrp/knowledge/processors.py apps/server/ntrp/memory/service.py apps/server/ntrp/server/routers/knowledge.py apps/server/tests/test_knowledge_activation.py apps/server/tests/test_knowledge_next_level.py apps/desktop/src/api.ts apps/desktop/src/components/memory/KnowledgeReviewPane.tsx docs/internal/memory-implementation-notes.md` — passed after UI.
- `uv run pytest tests -q` — 847 passed, 1 failed in unrelated `tests/test_spawn_salvage.py::test_spawn_emits_live_token_usage_for_child_response` (`FakeLLM` lacks `complete`, so no token usage event emitted after salvage summary call failed). Not caused by memory changes; leave as existing tree issue unless user wants that detour.

## 2026-05-24 — Post-restart live verification

- User restarted/reloaded the ntrp server. `/health` now responds with `config_loaded_at=2026-05-24T17:42:01.461865+00:00`, so the running server is newer than the pre-restart blocked state.
- Live SQLite integrity checks passed: `PRAGMA integrity_check` = `ok`; `PRAGMA quick_check` = `ok`.
- Live type counts after restart were: `fact active=4086`, `fact superseded=59`, `lesson active=51`, `lesson superseded=9`, `artifact active=69`, `memory_episode active=191`, `memory_episode archived=44`, `procedure_candidate archived=6`, `run_provenance archived=54`, plus one draft `action_candidate` created by the blocked restart request.
- Found one pre-restart active tool-prefixed episode (`knowledge_objects.id=19520`, title `Episode: tool: Todo list updated.`). This was stale data created before the newest guard was active, not a new post-restart regression.
- Cleanup decision: archived stale episode `19520` instead of rewriting it, because it started with tool output and should not remain source-of-truth narrative memory. Also archived completed restart action candidate `19591`.
- Backup before cleanup: `~/.ntrp/backups/post-restart-memory-cleanup-20260524T174922Z/memory.db`.
- Post-cleanup live checks: active/draft legacy retained types = `0`; active tool-prefixed episodes = `0`; draft action candidates = `0`.
- Direct in-process smoke of new processor health code completed: health duplicate cluster count returned `27` in about `13.9s` against the live DB. That is acceptable for the admin/review surface for now, but worth optimizing if Review becomes noticeably sluggish.
- API caveat: authenticated `/knowledge/...` endpoints returned `401` from raw curl because the plaintext desktop API key is not recoverable from settings (only hash is stored). I verified the public `/health`, live DB state, and the new backend code path in-process instead of resetting the user's API key.
- Existing caveat remains: `extracted_without_source_episode` is high (`4211`) because many older facts/lessons/artifacts predate the episode-source discipline. The new health counter exposes this; I did not attempt a risky mass backfill during this slice.

## 2026-05-24 — source relationship traces

- Implemented the next missing detail from `docs/internal/memory.md`: source traces now include relationship context, not just raw `source_ids`.
- Backend `/knowledge/objects/{id}/sources` now returns:
  - `derived_objects`: facts/lessons/artifacts/action candidates/episodes that cite `knowledge:{id}`. This makes episode details show extracted durable memory.
  - `related_objects`: memories sharing the same source IDs, excluding the object itself and explicit `knowledge:*` source objects.
  - `superseded_versions`: old versions whose `superseded_by_object_id` points at the selected object.
  - `superseded_by_object`: canonical replacement when the selected object has been superseded.
- Tradeoff: relationship discovery is source-ID based instead of semantic-neighbor based. This is deterministic, provenance-safe, and cheap enough for the detail pane, but it will miss conceptually related facts that do not share source IDs. Semantic related-fact expansion can be added later once the duplicate/consolidation layer is more mature.
- Decision: kept raw non-`knowledge:*` source IDs (`session:*`, `run:*`, etc.) as source-native references. During relationship filtering I only exclude resolved `knowledge:*` source objects, because raw session/run IDs are ambiguous in the current store and `get_by_source_id("session:...")` can resolve to an arbitrary extracted object. This avoids hiding legitimate sibling memories.
- UI: Memory Library detail now has a `Source relationships` section with extracted-from-this-object, related-through-same-sources, superseded-versions, and superseded-by lists. This gives episodes/facts the hierarchy called for by the spec without dumping raw tool spam into episode memory.
- Verification added:
  - `test_source_trace_includes_related_and_superseded_objects` covers episode-derived objects, same-source siblings, superseded versions, and superseded-by canonical lookup.
  - Existing processor/source-trace test now verifies an episode surfaces its derived artifact.
- Targeted verification run after this change:
  - `uv run pytest tests/test_knowledge_next_level.py::test_source_trace_includes_related_and_superseded_objects -q` → `1 passed`.
  - `uv run pytest tests/test_knowledge_activation.py::test_processors_reflect_render_publish_and_feedback -q` → `1 passed`.
  - `uv run ruff check ntrp tests` → passed.
  - `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` in `apps/desktop` → passed.
- Broader verification after relationship trace change:
  - `uv run pytest tests/test_knowledge_activation.py tests/test_knowledge_next_level.py -q` → `72 passed`.
  - `npx -y node@22.12.0 $(which npm) run build` in `apps/desktop` → passed; only existing Vite chunk-size warnings.
- Added `fact_conflict_clusters` to the health result so contradiction/conflict rate is exposed alongside duplicate fact clusters. It reuses the conservative conflict detector from fact consolidation and does not auto-merge conflicts.
- Re-ran verification after adding the conflict health counter:
  - `uv run pytest tests/test_knowledge_activation.py tests/test_knowledge_next_level.py -q` → `72 passed`.
  - `uv run ruff check ntrp tests` → passed.
  - `npx -y node@22.12.0 ./node_modules/typescript/bin/tsc --noEmit` in `apps/desktop` → passed.
  - `npx -y node@22.12.0 $(which npm) run build` in `apps/desktop` → passed; only existing Vite chunk-size warnings.
- Remaining deliberate caveat: extraction/activation precision samples still require human judgment or a curated eval set. I exposed automated health counters and relationship traceability now, but did not fake a usefulness score from heuristics.

## 2026-05-24 live verification attempt after relationship-trace work

- Running server observed on `127.0.0.1:6877`, PID `36585`, started `2026-05-24 21:41:58 +04`, cwd `apps/server`.
- The newest touched backend/UI files are newer than that process (`service.py` `22:09:54`, `models.py` `22:14:05`, `processors.py` `22:14:13`, `KnowledgeLibraryPane.tsx` `22:08:23`), so the currently running process is stale for the latest source-relationship and `fact_conflict_clusters` work.
- Live API check with the desktop-stored API key confirmed the server responds, but it only returned the older `/knowledge/objects/{id}/sources` shape: keys were `object`, `policy_version`, and `sources`; `derived_objects`, `related_objects`, `superseded_versions`, and `superseded_by_object` were absent.
- Live `/knowledge/processors/health` responded `200` and still exposed `duplicate_fact_clusters = 27`, but the new `fact_conflict_clusters` field was absent, again confirming stale server code.
- Live `/knowledge/facts/consolidation?limit=500&max_proposals=3&min_confidence=0.86` responded `200` with `3` proposals, so the older duplicate proposal endpoint is live. I did not commit a live merge during this stale-code check.
- Decision: do not mark the latest work live-verified until the server is restarted/reloaded and the desktop app refreshes. Per user directive, I did not restart the server myself.

## 2026-05-24 live verification after user restart

- User restarted/reloaded. New live processes observed:
  - server PID `81428`, started `2026-05-24 23:20:37 +04`, listening on `127.0.0.1:6877`.
  - desktop Vite PID `81536`, started `2026-05-24 23:20:40 +04`, listening on `127.0.0.1:5175`.
- `/health` returned `200` with config loaded at `2026-05-24T19:20:39.577765+00:00`, confirming the restarted server is serving.
- Live `/knowledge/processors/health` returned the new shape, including:
  - active retained counts: `artifact=74`, `fact=4088`, `lesson=51`, `memory_episode=191`.
  - `active_legacy_objects=0`.
  - `tool_episode_candidates=0`.
  - `extracted_without_source_episode=482` (mostly historical/pre-episode extracted objects; left as a surfaced remediation counter, not silently rewritten).
  - `duplicate_fact_clusters=29`.
  - `fact_conflict_clusters=175`.
  - `missing_provenance=0`, `stale=0`, `review_queue=0`.
- Live `/knowledge/objects/{id}/sources` now returns the relationship fields for valid objects: `derived_objects`, `related_objects`, `superseded_versions`, and `superseded_by_object`.
- Representative live source-trace checks:
  - active episode `18125`: `sources=3`, `derived=8`, `related=94`, `superseded_versions=0`.
  - recent active episode `19590`: `sources=3`, `derived=6`, `related=94`, `superseded_versions=0`.
  - active canonical fact `19603`: `sources=4`, `related=99`, `superseded_versions=4`.
  - superseded fact `4563`: `sources=1`, `superseded_by_object=19603`.
- Live duplicate proposal endpoint `/knowledge/facts/consolidation?limit=500&max_proposals=3&min_confidence=0.86` returned `200` with `3` proposals. I intentionally did not commit a live merge during verification to avoid mutating real memory without a specific approval target; commit behavior remains covered by backend tests.
- DB verification after restart:
  - `PRAGMA integrity_check` → `ok`.
  - `PRAGMA quick_check` → `ok`.
  - total `knowledge_objects=4589`.
  - status/type snapshot: `fact active=4088`, `fact superseded=64`, `lesson active=51`, `lesson superseded=9`, `artifact active=74`, `memory_episode active=192`, `memory_episode archived=46`, `procedure_candidate archived=6`, `action_candidate archived=1`, `run_provenance archived=58`.
  - active/draft legacy object count for `entity_profile`, `pattern`, `procedure`, and `procedure_candidate` → `0`.
- Caveat found during live verification: some historical `source_ids` still point at deleted/missing `knowledge:*` objects. Directly requesting one missing object (`18124`) caused a server `KeyError`/500 instead of a clean 404. Valid object traces work, and relationship resolution skips unresolved related objects, but the missing-ID route should be hardened separately and the dangling source refs should remain visible as provenance debt.

## 2026-05-24 missing source-trace object hardening

- Live verification exposed one API hardening bug: directly requesting `/knowledge/objects/{id}/sources` for a missing historical `knowledge:*` object raised `KeyError` and returned a server 500. This happened with missing object `18124`, which still appears in older `source_ids` even though the object row no longer exists.
- Change: the knowledge router now catches `KeyError` from `source_trace` and returns a clean HTTP `404` with the service's not-found detail instead of leaking an internal exception.
- Added regression test `tests/test_knowledge_routes.py::test_knowledge_object_sources_returns_404_for_missing_object`.
- Verification:
  - `uv run pytest tests/test_knowledge_routes.py -q` → `1 passed`.
  - `uv run pytest tests/test_knowledge_activation.py tests/test_knowledge_next_level.py -q` → `72 passed`.
  - `uv run ruff check ntrp tests` → passed.
- Caveat: this route hardening is code-verified but, per the no-self-restart directive, it will not be live until the server is restarted/reloaded again.

## 2026-05-24 live verification after 404 hardening restart

- User restarted/reloaded after the missing source-trace route fix. New server process observed:
  - server PID `88155`, started `2026-05-24 23:36:56 +04`, listening on `127.0.0.1:6877`.
  - `/health` returned `200`, config loaded at `2026-05-24T19:36:56.731004+00:00`.
- Live missing-object check: `GET /knowledge/objects/18124/sources` now returns HTTP `404` with `{"detail":"Knowledge object 18124 not found"}` instead of `KeyError`/500.
- Live valid-object smoke check: `GET /knowledge/objects/19603/sources` still returns the source-relationship shape with `derived_objects`, `related_objects`, `superseded_versions`, and `superseded_by_object`; sample counts were `related_objects=99`, `superseded_versions=4`.
