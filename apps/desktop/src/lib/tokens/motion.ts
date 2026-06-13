/**
 * Motion tokens — springs, eases, and durations for framer-motion and
 * JS-driven animation. Single source of truth; the CSS side lives in
 * styles.css (`--duration-*`, `--ease-*`) and must stay in sync with the
 * MOTION mirror below.
 *
 * Spec: docs/superpowers/specs/2026-05-17-design-system-tokens-design.md §2.2
 *       docs/internal/ui-ux-intelligence.md "Motion Direction"
 */
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
/** Popover / menu reveal — origin-anchored, snappy with a hint of bounce. */
export const SPRING_POPOVER = { type: "spring", stiffness: 350, damping: 26, mass: 1 } as const;
/** Row settles — Control Center–style spring for sibling-row entrances.
 *  Used by `TurnGroup`'s work-block stagger. Snappier than SPRING_MODAL;
 *  livelier than SPRING_CARD. */
export const SPRING_ROW_ENTRY = { type: "spring", stiffness: 360, damping: 28, mass: 0.8 } as const;
/** Trace ticker rows. Heavier damping than ROW_ENTRY — zero overshoot so
 *  the most-fired animation in the app never wobbles mid-stream. */
export const SPRING_TRACE_ROW = { type: "spring", stiffness: 350, damping: 40, mass: 0.8 } as const;
/** Approval-stack cards (deck promotion, queue collapse). User-tuned:
 *  quick settle, no overshoot. */
export const SPRING_STACK = { type: "spring", stiffness: 340, damping: 32, mass: 0.9 } as const;

// ─── Eases (cubic-bezier tuples) ─────────────────────────────

/** Material 3 emphasized-decelerate — entries that should "land". */
export const EASE_DECELERATE = [0.05, 0.7, 0.1, 1] as const;
/** Snappy out-cubic for hover brightness/color shifts. */
export const EASE_HOVER = [0.16, 1, 0.3, 1] as const;
/** Sidebar / inspector route slides. Mirrors CSS `--ease-emphasized`. */
export const EASE_EMPHASIZED = [0.32, 0.72, 0, 1] as const;
/** Soft ease-out for popover landings and small scale-ins. Mirrors CSS
 *  `--ease-out-soft`. */
export const EASE_OUT = [0.2, 0.8, 0.2, 1] as const;

// ─── Durations (seconds) ─────────────────────────────────────
// MOTION mirrors the CSS --duration-* scale (named by feel) so CSS
// transitions and framer-motion props share one timing language. The
// use-case-named DURATION_* aliases below derive from it — single set of
// literals, no drift.

export const MOTION = {
  fast: 0.1,
  check: 0.12,
  row: 0.14,
  palette: 0.18,
  trace: 0.2,
  panel: 0.22,
  route: 0.36,
} as const;

export const DURATION_TAP = MOTION.fast;
export const DURATION_HOVER = MOTION.row;
export const DURATION_POPOVER = MOTION.palette;
export const DURATION_PANEL = MOTION.panel;
export const DURATION_ROUTE = MOTION.route;

// ─── Panel entry curve ───────────────────────────────────────

export const ENTRY_PANEL = SPRING_MODAL;

// ─── Blur-dissolve vocabulary ────────────────────────────────
// House enter/exit poses: content rises into focus, exits dissolve.
// Spread + override per surface (`{ ...RISE_IN, y: -4 }`); pick duration
// from MOTION per tier. Exits run FASTER than entrances (fast/row vs
// row/panel). Keep blur ≤4px — these are content-sized elements, and
// fill-rate cost scales with area.

/** Entrance pose — pair with `animate={RISE_SETTLED}`. */
export const RISE_IN = { opacity: 0, y: 6, filter: "blur(3px)" } as const;
export const RISE_SETTLED = { opacity: 1, y: 0, filter: "blur(0px)" } as const;
/** Exit pose for sections/banners/popunders — quicker, dissolving. */
export const DISSOLVE_OUT = { opacity: 0, scale: 0.97, filter: "blur(3px)" } as const;
/** Exit pose for popLayout list rows — the removed row dissolves while
 *  siblings FLIP up via their `layout` springs. */
export const ROW_EXIT = { opacity: 0, scale: 0.96, filter: "blur(4px)" } as const;

/** Shared modal panel pose — the single source for hand-rolled modal
 *  entrances (PageModal, ToolViewer, Mermaid) so the pose can't drift
 *  per call site. Pair with ENTRY_PANEL. */
export const POSE_MODAL = { opacity: 0, scale: 0.96, y: 6 } as const;

// ─── Spatial origin helpers ──────────────────────────────────

/** Returns the viewport-space center of an element. Used as the spatial
 *  origin for modal open animations — the modal then grows from this
 *  point, so users can see WHERE it came from. */
export function originFromEvent(
  target: Element | null | undefined,
): { x: number; y: number } | null {
  if (!target) return null;
  const rect = target.getBoundingClientRect();
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

/** Given a trigger origin (in viewport coords), return the initial
 *  transform a modal should use to "grow from" that origin. We clamp
 *  the delta — a full FLIP would make a corner-triggered modal slide
 *  across the entire screen, which feels too much. ~64px is enough
 *  motion to encode origin without being theatrical. Returns null
 *  when origin is missing → caller falls back to neutral fade. */
export function modalOriginTransform(
  origin: { x: number; y: number } | null,
): { x: number; y: number } | null {
  if (!origin) return null;
  const cx = window.innerWidth / 2;
  const cy = window.innerHeight / 2;
  const dx = origin.x - cx;
  const dy = origin.y - cy;
  const MAX = 64;
  const clamp = (v: number) => Math.sign(v) * Math.min(Math.abs(v) * 0.18, MAX);
  return { x: clamp(dx), y: clamp(dy) };
}
