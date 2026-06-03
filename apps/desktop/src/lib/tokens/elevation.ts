/**
 * Elevation tokens — Phase 1 of the design-system tokens spec
 * (docs/superpowers/specs/2026-05-17-design-system-tokens-design.md §2.3).
 *
 * The actual values live in CSS custom properties on `:root` / `:root.dark`
 * (see `styles.css`). This module exports their names as `var(--…)` strings
 * so TS consumers can write inline styles without typo'ing the var name.
 */

// ─── Ring alphas (universal) ─────────────────────────────────
// Used by panel rings and focus rings. Theme-aware variants resolve via
// `:root.dark` overrides in styles.css.

export const RING_LIGHT = "var(--ring-light)";
export const RING_LIGHT_SOFT = "var(--ring-light-soft)";
export const RING_LIGHT_STRONG = "var(--ring-light-strong)";
export const RING_DARK = "var(--ring-dark)";
export const RING_DARK_SOFT = "var(--ring-dark-soft)";
export const RING_DARK_STRONG = "var(--ring-dark-strong)";

// ─── Linen shadow recipes ────────────────────────────────────
// Stacked Tailwind pattern in light mode; Linear-style single contained
// shadow in dark mode (override on :root.dark).

export const SHADOW_LINEN_REST = "var(--shadow-linen-rest)";
export const SHADOW_LINEN_HOVER = "var(--shadow-linen-hover)";
export const SHADOW_LINEN_POPOVER = "var(--shadow-linen-popover)";
export const SHADOW_LINEN_MODAL = "var(--shadow-linen-modal)";

// ─── Focus ring ──────────────────────────────────────────────
// Drives `:focus-visible` across interactive primitives in Phase 3.

export const FOCUS_RING = "var(--focus-ring)";
