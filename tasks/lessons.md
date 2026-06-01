# Lessons

## Memory work — the spec IS the implementation guide; read it FIRST, every time (Jun 2026)

Before ANY memory decision (diagnosis, fix, build, answer), read the governing docs FIRST — never improvise then check:
- `~/vault/Memory Consolidation/Memory — vision (new spec).md` (the model)
- `~/vault/Memory Consolidation/Lens — spec.md` (lenses)
- `tasks/memory-rebuild.md`, `tasks/lens-view-correction.md` (what was built / locked)

Cost of not doing this: I proposed routing `remember()` through Extract (user had explicitly said "remember is just a tool, no logic") and missed that the built lens layer (single `people` lens grouping by `canonical_subject`) DIVERGES from the spec, which says **entity = lens, membership by LLM scoring** (Lens spec §4). Two wrong fixes in a row because I reasoned from code + memory instead of the spec.

Rule: the spec is the source of truth. Read it before forming any opinion. If code diverges from spec, the divergence is the bug — don't rationalize the code.

## Memory rebuild — no hard-rule/lexical heuristics (Jun 2026)

Build/workflow agents repeatedly smuggle lexical heuristics in despite "no heuristic gate" — Stage 3 baked them into the CONTRACT and multiple components: `_PRONOUN_HINTS = {"i","me","user",...}` (reconcile subject recall), `_PROPER_NOUN_RE` regex + `_STOPWORD_CAPS` (extract), and a contract-level "Pronoun/role channel (deterministic)".

Rule: **every decision AND every recall channel is LLM/embedding/FTS — never a hand-maintained word list, keyword set, or regex-for-meaning.** Subject/coreference identity comes from the LLM resolving a canonical subject at extract time + embedding/FTS recall + LLM judge — not a pronoun list. (English-only word lists are also brittle/non-general.)

Prevention: workflow build prompts MUST say this explicitly (not just "no opaque gate"); a verify step MUST grep the pipeline for `frozenset`/`_WORDS`/`_TERMS`/`_HINTS`/`re.compile`/keyword-`in {`-sets and fail on any decision/recall use. Watch capture's idle/time boundary — a mechanical chunking trigger is OK; a *semantic* gate is not.


## Design-system tokens (May 2026)

### @property registration is required to transition CSS custom properties
A bare `--my-var: 0.3` declared in `:root` is a *string* to the browser — CSS
transitions on it snap rather than interpolate. To get smooth easing across
custom props (e.g. glass rim alpha drifting on hover), declare them with
`@property` so the browser knows the syntax/type:

```css
@property --rim-alpha {
  syntax: "<number>";
  inherits: true;
  initial-value: 0.18;
}
```

Bit us in Phase 5 of the tokens migration — the rim drift looked like a step
function until we registered the prop.

### Token migration: ship aliases first, retire later
When renaming or restructuring tokens (motion, color, elevation) across a large
component surface, the discipline that kept each phase reviewable was:

1. Land the new token module alongside the old one — re-export the old name as
   a back-compat alias from the new module.
2. Sweep call sites to the new name in a follow-up phase.
3. Delete the alias only in a final cleanup phase, after `tsc --noEmit` confirms
   zero remaining importers.

This keeps each commit small and bisectable. Trying to rename + sweep + delete
in one pass forces every consumer through review at once and makes the diff
unreadable. Phase 4 (color) deferred its alias-retirement entirely because
per-palette `:root.palette-*` blocks still override the defaults — aliases are
load-bearing until a separate palette-block sweep lands.
