/**
 * Motion duration tokens (seconds, framer-motion friendly) and shared
 * easing curves. Mirrors the CSS --motion-* tokens in styles.css so the
 * timing language stays consistent across CSS transitions and
 * framer-motion `transition` props.
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
