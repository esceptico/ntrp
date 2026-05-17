# Glass Settings — Design

**Date:** 2026-05-17
**Scope:** Desktop Electron app at `apps/desktop/`.

## Purpose

Give the user full per-variant control over the glass material framework. Previous attempts to expose 3–4 global knobs were reverted; this round skips global presets entirely and exposes per-variant primitives. Same change adds two new variants (Smoke, Milk) per the recent demo-stealing pass and codifies the layering depth rule as a doc comment.

## Components

### 1. New CSS variants

Inside the existing `@layer components { … }` block in `apps/desktop/src/styles.css`:

- **`.glass-smoke`** — always-dark glass that ignores host theme. Use for floating surfaces over saturated/photo backdrops needing ink-text contrast. Default values: tint `rgba(10,10,30,0.55)`, blur 20px, saturate 120%, rim 0.06.
- **`.glass-milk`** — content-safe tier between frosted (35%) and static (86%). Default values: tint `rgba(255,255,255,0.5)`, blur 24px, saturate 140%, rim 0.9. Dark mode override: tint `rgba(255,255,255,0.18)`, same blur/saturate.

### 2. CSS variant rewrite — consume custom properties

Every glass variant rewrites its hardcoded values to consume CSS custom properties of the form `--gp-{variant}-{knob}` with `var(name, fallback)` syntax. Fallback values are the current defaults so the change is invisible when no settings are applied.

Variants affected: `frosted` (the base `.glass-surface`), `heavy`, `static`, `clear`, `smoke`, `milk`.

Knobs per variant:
- `--gp-{variant}-tint` — `rgba(...)` background fill
- `--gp-{variant}-blur` — px value for `backdrop-filter: blur(...)`
- `--gp-{variant}-saturate` — % value for `backdrop-filter: saturate(...)`
- `--gp-{variant}-rim` — opacity (0–1) for the top-edge inset specular shadow

### 3. State + types

`apps/desktop/src/store/types.ts` adds:

```ts
export type GlassVariantId = "frosted" | "heavy" | "static" | "clear" | "smoke" | "milk";

export interface GlassParams {
  /** Tint opacity 0–100 (% white). */
  tint: number;
  /** Backdrop-filter blur in px. */
  blur: number;
  /** Backdrop-filter saturate %. */
  saturate: number;
  /** Top-edge specular rim opacity 0–100 (%). */
  rim: number;
}

export type GlassPrefs = Record<GlassVariantId, GlassParams>;
```

`Prefs` interface gains `glass: GlassPrefs`.

`apps/desktop/src/store/prefs.ts` adds `DEFAULT_GLASS_PREFS` matching the current `styles.css` defaults for each variant. `DEFAULT_PREFS.glass` set to it.

### 4. Effect — write CSS custom properties

`apps/desktop/src/lib/theme.ts` (or a sibling `glass.ts` file — implementation detail) gains a `useGlassEffect` that subscribes to `prefs.glass` and writes the resolved values to `:root` as CSS custom properties:

```ts
:root {
  --gp-frosted-tint: rgba(255, 255, 255, 0.35);
  --gp-frosted-blur: 20px;
  --gp-frosted-saturate: 180%;
  --gp-frosted-rim: 0.6;
  /* ... × 6 variants */
}
```

Hooked into `App.tsx` alongside `useThemeEffect`.

### 5. Glass tab in SettingsModal

New tab added to `apps/desktop/src/components/SettingsModal.tsx` tab list, between Appearance and Models (or wherever fits).

New file: `apps/desktop/src/components/settings/GlassTab.tsx`.

**Layout — two columns inside the tab content area:**

- **Left rail (~180px):** Variant list (6 rows). Each row shows variant name + 24×24 mini preview of the variant material. Clicking selects it. Active row highlighted with `data-active` + bg-surface-soft (same convention as memory pane row selection).
- **Right pane:** Controls for the selected variant.

**Right pane contents:**

1. **Header row** — variant name as h3 + `Reset to default` link button (per-variant reset). Top-right of the pane.
2. **Live preview tile** — 240×140 card. Renders with `class="glass-surface glass-{variant}"`. Sits over a constrained "busy backdrop" — small mesh gradient + a single line of scrolling serif text, like a 160×80 micro version of the demo's stage. Updates in real time as sliders move (the CSS custom properties drive everything).
3. **Four sliders** (use a new `<RangeField>` primitive built for this tab — same visual language as the existing `LabeledField`/`NumberField`):
   - Tint (0–100%)
   - Blur (0–60px)
   - Saturate (100–250%)
   - Rim (0–100%)

Each slider shows: label, current value, the slider control, and an optional unit hint (px, %).

**Tab header** has a `Reset all variants` button (right-aligned).

### 6. Layering depth doc comment

Add to `styles.css` immediately above the `@layer components { }` block:

```css
/* Glass layering rule:
   When stacking glass surfaces, each elevation step up = +4px blur,
   +5% tint, +0.05 rim opacity. Don't break this without reason —
   it's what makes depth read as depth instead of as visual noise. */
```

## State flow

```
SettingsModal → GlassTab
  └── reads prefs.glass[variantId]
  └── slider onChange → setPrefs({ glass: { ...prefs.glass, [variantId]: { ...params, [knob]: value } } })

App.tsx
  └── useGlassEffect()
        └── subscribes prefs.glass
        └── writes :root CSS custom properties
        └── all .glass-{variant} rules read those properties

styles.css
  └── .glass-{variant} uses var(--gp-{variant}-{knob}, defaultValue)
```

## Out of scope

- Matrix calibration tool (Blur × Saturation). The live preview tile in Settings is sufficient.
- Per-theme split (separate light/dark values per variant). One set of values × current theme — the variant's own light/dark *recipe* already handles framing differences.
- Layering rule as anything other than a doc comment. No enforcement, no "elevation" prop.
- Iridescent / Liquid variants from the demo. Smoke and Milk are the only adds.
- Animation reduction toggle. Defer until perf-tier prefs come up separately.

## Verification

After each task: `cd apps/desktop && bun run typecheck` must pass clean.

Manual verification of the Glass tab:
1. Open Settings → Glass.
2. Pick "Frosted". Drag Tint slider to 80%. Confirm: live preview tile updates AND the actual SettingsModal background (which uses `.glass-surface .glass-frosted`) updates in real time. This is the headline test — it proves the effect is wired correctly.
3. Pick "Smoke". Confirm the new variant renders with dark-glass material.
4. Click "Reset to default". Sliders snap back, preview restores.
5. Click "Reset all variants". All variants restore.
6. Close and reopen Settings — values persist (prefs storage).

## Risks

- **The settings modal IS made of glass.** Changing `frosted` tint affects the SettingsModal itself, which is the surface the user is looking at while adjusting. This is intentional ("instant feedback on the real surface") but may briefly disorient. Consider it the right tradeoff — alternative would be a previews-only model that doesn't update real surfaces, which defeats the purpose.
- **Bad values can make text illegible.** Tint at 0% in dark mode = invisible panel. The Reset-to-default escape hatch handles this; no validation/clamping beyond slider min/max.
- **`backdrop-filter: blur(0)` still creates a compositor pass.** A user dragging Blur to 0 will not gain perf; they'll just remove the visual blur. Note in comments; don't engineer around it.
