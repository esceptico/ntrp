# Lessons

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
