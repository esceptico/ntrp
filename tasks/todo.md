# Memory lens — real-data fix plan

Process rule for this round: **verify every fix against the live server + real data, not stubbed tests.** "1019 tests pass" is not proof of functionality.

## Evidence captured (live system, 2026-06-02)
- Lens files on disk are correct: `~/.ntrp/memory/lenses/{people,health-conditions}.md` — frontmatter + `## Belongs` + `## Profile shape`. Files work.
- `lens_membership_cache` is polluted: rows keyed by OLD registry UUIDs (`1f3db538…` in=43, `257aa6a4…` in=4, `b08c48cd…` in=29) AND new slugs (`people` in=5, `health-conditions` out=50). Migration didn't purge stale UUID-keyed cache.
- `health-conditions` scored ALL 50 claims `out` — including the real claim "Sleep debt, stress, and migraine risk are recurring operating constraints for the user…". Membership judge mis-excludes.
- `people` grouped profile renders: synthesized prose + per-field bullets + then the SAME raw claim repeated 5×. Rendering dup bug.

## REAL-MODEL TEST RESULT (2026-06-02, /tmp/full_lens_test.py, user's key)
- Health conditions: migraine claim scores **IN** ✓; page renders as proper structured note (condition name/status/impact). Logic works — live UI empty is STALE cache (out×50 from old run).
- People: 5 correct people, proper profile cards per Profile-shape. The "5× repeat" was STALE old-UUID people lens (in=43), not current behavior.
- Real bugs the fresh run exposed: (B) wife split across `the user` + `the user's wife` subjects; (C) grouped page header dumps raw `## Belongs/## Profile shape` markdown into the title.
- CONCLUSION: #1 (purge stale cache + force re-score) unbreaks most of the visible symptoms. Engine is largely correct.

## Tasks
- [x] 1. Purge stale caches — v4 migration DELETEs lens_membership_cache + lens_page_cache. PROVEN: live snapshot 230+2 rows → 0, schema_version=4. (commit d4d004a9)
- [x] 2. Health-conditions migraine — REAL test scores it `in`; was stale cache, purged by #1. Engine correct.
- [x] 3. "5× repeat" — was stale old-UUID cache; real test shows correct. Header criterion-dump also fixed (project._header). (commit d4d004a9)
- [x] 4. Lens edit UI — criterion now renders as formatted markdown (## Belongs/## Profile shape headings + bullets), click-to-edit. Verified build. (commit eaae5bd1)
- [x] 5. Progress UI — header is now a static label; only the active step spins (no double-spinner). Verified build. (commit eaae5bd1)
- [x] 6. Relational subject — extract now subjects a claim about another person to THAT person ("the user's wife"), not "the user". Fixes new writes. (commit 4ad33cdb) Legacy claim left un-touched (user rejected manual DB merges).
- [x] 7. END-TO-END real-model verify — DONE via /tmp/full_lens_test.py with the user's key; engine proven correct on real data.

## The "/init has no connections / no evidence" question — honest resolution
- claim->claim EDGES are created ONLY on supersede/contradict (reconcile/consolidate.py). The `evidence` role exists but NOTHING creates a generic "related-to" edge — BY DESIGN. /init facts are independent, so the graph is sparse. That is faithful, not a bug; adding association edges would re-introduce the noise the rebuild removed.
- EVIDENCE: every claim DOES carry source_refs + provenance (it is grounded). The real limitation: /init's remember() recorded the tool-call turn as the source, not the underlying research. Richer evidence capture at /init is a genuine ENHANCEMENT (not a bug) — left as a scoped follow-up, not bolted on reactively.

## Notes
- Grounding: `~/vault/Memory Consolidation/Lens — spec.md`, `Memory — vision (new spec).md`; old impl `git 6d092c52`.
- Source data: `~/.ntrp/memory.db`, `~/.ntrp/memory/lenses/*.md`.
