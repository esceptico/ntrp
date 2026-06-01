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
- [ ] 1. Purge stale UUID-keyed `lens_membership_cache` rows; cache keyed only by slug.
- [ ] 2. Membership misjudgment — `health-conditions` excludes the migraine/sleep claim. Root-cause criterion exclusion vs judge; fix so genuine conditions match. Verify that claim scores `in`.
- [ ] 3. Lens page rendering — repeated claim entries (5×) + raw plain list under the synthesized profile. Dedupe; show profile + claims once.
- [ ] 4. Lens edit UI — parse/show frontmatter; edit Belongs + Profile shape as a structured doc, not one plain italic blob.
- [ ] 5. Progress UI — "Generating view" + "Scoring members" spin at once; sequence + label stages correctly.
- [ ] 6. `people` "the user" grouping — profile framed about the wife, work claims not surfaced. Check membership + grouping + synthesis.
- [ ] 7. END-TO-END VERIFY on the live server with real data for each — not stubs.

## Notes
- Grounding: `~/vault/Memory Consolidation/Lens — spec.md`, `Memory — vision (new spec).md`; old impl `git 6d092c52`.
- Source data: `~/.ntrp/memory.db`, `~/.ntrp/memory/lenses/*.md`.
