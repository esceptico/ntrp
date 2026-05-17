/**
 * Motion tokens — Phase 1 of the design-system tokens spec
 * (docs/superpowers/specs/2026-05-17-design-system-tokens-design.md §2.2).
 *
 * Springs, eases, and durations named by use case rather than by feel.
 * Existing consumers still import from `../motion`; this module is the
 * canonical destination — Phase 2 will sweep call sites.
 */
import { SPRING_SMOOTH as LEGACY_SPRING_SMOOTH } from "../motion";

// ─── Springs ──────────────────────────────────────────────────
// Stiffness/damping pairs tuned to use case. Higher stiffness = faster
// settle; higher damping = less overshoot. `mass: 1` keeps the visual
// scale consistent with framer-motion defaults.

/** Modals, sheets, drawers. Confident settle, no perceptible bounce. */
export const SPRING_MODAL = { type: "spring", stiffness: 380, damping: 32, mass: 1 } as const;
/** Cards lifting on hover, smaller surfaces. Softer than MODAL. */
export const SPRING_CARD = { type: "spring", stiffness: 260, damping: 26, mass: 1 } as const;
/** Press/release feedback. Snappy so an interrupted release re-targets. */
export const SPRING_TAP = { type: "spring", stiffness: 380, damping: 30, mass: 1 } as const;
/** Layout / FLIP / list reorders. Slower, longer settle for shared element. */
export const SPRING_LAYOUT = { type: "spring", stiffness: 220, damping: 28, mass: 1 } as const;

/**
 * Compatibility re-export — keeps `import { SPRING_SMOOTH } from ".../motion-tokens"`
 * working while Phase 2 sweeps imports to `SPRING_MODAL`. Mirrors the legacy
 * SPRING_SMOOTH value (not SPRING_MODAL) so re-export semantics are exact;
 * Phase 2 retargets at call sites.
 */
export const SPRING_SMOOTH = LEGACY_SPRING_SMOOTH;

// ─── Eases (cubic-bezier tuples) ─────────────────────────────

/** Material 3 emphasized — default for transitions. */
export const EASE_STANDARD = [0.2, 0, 0, 1] as const;
/** Material 3 emphasized-decelerate — entries that should "land". */
export const EASE_DECELERATE = [0.05, 0.7, 0.1, 1] as const;
/** Snappy out-cubic for hover brightness/color shifts. */
export const EASE_HOVER = [0.16, 1, 0.3, 1] as const;
/** Sidebar / inspector route slides. Existing curve, kept for parity. */
export const EASE_EMPHASIZED = [0.32, 0.72, 0, 1] as const;

// ─── Durations (seconds) ─────────────────────────────────────

export const DURATION_TAP = 0.1;
export const DURATION_HOVER = 0.14;
export const DURATION_POPOVER = 0.18;
export const DURATION_PANEL = 0.24;
export const DURATION_ROUTE = 0.36;

// ─── Per-material entry curves ───────────────────────────────
// Glass entries decelerate (the slab "lands"); linen entries use the
// modal spring so the body and surface arrive together. Content fade
// delay for glass (~100 ms) is wired by the consumer in Phase 2.

export const ENTRY_GLASS = {
  ease: EASE_DECELERATE,
  duration: 0.22,
} as const;

export const ENTRY_LINEN = {
  spring: SPRING_MODAL,
} as const;
