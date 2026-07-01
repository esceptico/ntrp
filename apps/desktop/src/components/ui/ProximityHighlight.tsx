import { useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { EXIT_FAST, MOTION, SPRING_PROXIMITY } from "@/lib/tokens/motion";

type Rect = { top: number; height: number };

// Vertical gap (px) above which the highlight cross-fades instead of sliding —
// distinguishes adjacent rows (touching) from rows split by a section
// label/divider, so the strip never travels over a header/divider.
const SECTION_GAP = 14;

/**
 * THE single definition of the traveling proximity-hover highlight used by every
 * popover menu and selection list (AnchoredPopover, the model picker, Select,
 * and the RadioGroup/CheckboxGroup/SegmentedControl hover ghost). One element
 * eases toward the row nearest the pointer.
 *
 * Owns all three behaviours so they stay consistent everywhere — change them
 * HERE, never in a consumer:
 *   - fill: `bg-ink/[0.08]` (reads on any surface, both themes)
 *   - speed: SPRING_PROXIMITY (tracks the pointer near-instantly, no lag)
 *   - section-aware: cross-fades across a gap (bumps the AnimatePresence key)
 *     instead of sliding over a header/divider; adjacent rows still slide.
 *
 * `rect` is the active row's layout box (`{ top, height }`, relative to the
 * positioned scroll container). Pass `null` when nothing is hovered. `className`
 * tunes only LAYOUT (inset/radius) per host; the fill/motion are fixed.
 */
export function ProximityHighlight({
  rect,
  className,
}: {
  rect: Rect | null;
  className?: string;
}) {
  const segmentRef = useRef(0);
  const prevRef = useRef<Rect | null>(null);
  if (rect) {
    const prev = prevRef.current;
    if (prev) {
      const [lo, hi] = prev.top <= rect.top ? [prev, rect] : [rect, prev];
      if (hi.top - (lo.top + lo.height) > SECTION_GAP) segmentRef.current += 1;
    }
    prevRef.current = rect;
  } else {
    prevRef.current = null;
  }

  return (
    <AnimatePresence>
      {rect && (
        <motion.div
          key={segmentRef.current}
          aria-hidden
          className={clsx("absolute pointer-events-none bg-ink/[0.08]", className ?? "inset-x-1 rounded-md")}
          initial={{ opacity: 0, top: rect.top, height: rect.height }}
          animate={{ opacity: 1, top: rect.top, height: rect.height }}
          exit={{ opacity: 0, transition: EXIT_FAST }}
          transition={{ ...SPRING_PROXIMITY, opacity: { duration: MOTION.fast } }}
        />
      )}
    </AnimatePresence>
  );
}
