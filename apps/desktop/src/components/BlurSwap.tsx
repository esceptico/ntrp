import type { ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { EASE_OUT, MOTION } from "../lib/tokens/motion";

interface BlurSwapProps {
  /** Identity of the current content. A change triggers the crossfade. */
  swapKey: string;
  children: ReactNode;
  /** Blur radius (px) of the bridge. Tiny glyphs need less. */
  blur?: number;
  /** Crossfade duration in seconds; defaults to MOTION.check. */
  duration?: number;
  /**
   * When set, also scale from this value → 1, swapping the tween for the
   * no-bounce icon-swap spring. Pass 0.25 for the contextual-icon-animation
   * recipe (scale 0.25 → 1, opacity 0 → 1, blur 4px → 0). Omit for a plain
   * opacity + blur crossfade (text, multi-char glyphs).
   */
  scaleFrom?: number;
  className?: string;
}

/**
 * Overlapping blur crossfade for two states that share one slot — Emil
 * Kowalski's "use blur when nothing else works" (tip #7). The old and new
 * state co-exist mid-transition (sync mode) stacked in a single grid cell,
 * so they blur into each other in place. mode="wait" would finish the exit
 * before starting the enter, leaving an empty frame — the opposite of a
 * bridge. The grid stack lets both occupy cell 1/1 without reflowing
 * side-by-side, and sizes to the larger child so there's no width jump.
 */
export function BlurSwap({
  swapKey,
  children,
  blur = 4,
  duration = MOTION.check,
  scaleFrom,
  className,
}: BlurSwapProps) {
  const scaled = scaleFrom != null;
  const hidden = {
    opacity: 0,
    filter: `blur(${blur}px)`,
    ...(scaled ? { scale: scaleFrom } : {}),
  };
  const shown = {
    opacity: 1,
    filter: "blur(0px)",
    ...(scaled ? { scale: 1 } : {}),
  };
  return (
    <span className={clsx("inline-grid place-items-center", className)}>
      <AnimatePresence initial={false}>
        <motion.span
          key={swapKey}
          className="col-start-1 row-start-1 inline-flex"
          initial={hidden}
          animate={shown}
          exit={hidden}
          // Icon swaps (scaleFrom set) ride the mandated no-bounce spring;
          // plain glyph/text crossfades keep the soft tween.
          transition={scaled ? { type: "spring", duration: 0.3, bounce: 0 } : { duration, ease: EASE_OUT }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
