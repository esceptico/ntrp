/**
 * Motion duration tokens (seconds, framer-motion friendly) and shared
 * easing curves. Mirrors the CSS --duration-* / --ease-* tokens in
 * styles.css so the timing language stays consistent across CSS
 * transitions (Tailwind utilities like `duration-fast`,
 * `ease-emphasized`) and framer-motion `transition` props.
 *
 * Spec lives in docs/internal/ui-ux-intelligence.md "Motion Direction".
 */
export const MOTION = {
  fast: 0.1,
  check: 0.12,
  row: 0.14,
  palette: 0.18,
  trace: 0.2,
  panel: 0.22,
  route: 0.28,
} as const;

/** Emphasized ease for layout slides (sidebar, inspector, route). */
export const EASE_EMPHASIZED = [0.32, 0.72, 0, 1] as const;

/** Ease-out used for landings on popovers and small UI scale-ins. */
export const EASE_OUT = [0.2, 0.8, 0.2, 1] as const;

/**
 * Apple SwiftUI spring presets, converted to framer-motion via
 * stiffness = (2π / duration)², damping = 4π × (1 − bounce) / duration.
 *
 * `SPRING_SMOOTH` is tuned to ~0.3s instead of SwiftUI's 0.5s default —
 * the longer duration felt too slow on modal entries. Other presets
 * keep the SwiftUI defaults for now; reach for these only when a user
 * test confirms the feel is right.
 *
 * Spec lives in docs/internal/apple-design-intel.md.
 */
export const SPRING_SMOOTH = { type: "spring", stiffness: 439, damping: 42, mass: 1 } as const;
export const SPRING_SNAPPY = { type: "spring", stiffness: 158, damping: 21.4, mass: 1 } as const;
export const SPRING_BOUNCY = { type: "spring", stiffness: 158, damping: 17.6, mass: 1 } as const;

/** Popover / menu reveal — origin-anchored, snappy with a hint of bounce. */
export const SPRING_POPOVER = { type: "spring", stiffness: 350, damping: 26, mass: 1 } as const;

/** Tap release — snappy spring so an interrupted release re-targets cleanly. */
export const SPRING_TAP_RELEASE = { type: "spring", stiffness: 400, damping: 22, mass: 0.8 } as const;

/** Row settles — Control Center–style spring for sibling-row entrances.
 *  Used by `TurnGroup`'s work-block stagger (Rauno's Depth essay:
 *  "Spring rows = organic feedback — Control Center–style spring per row").
 *  Snappier than SPRING_SMOOTH; not as elastic as SPRING_BOUNCY. */
export const SPRING_ROW_ENTRY = { type: "spring", stiffness: 360, damping: 28, mass: 0.8 } as const;

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
