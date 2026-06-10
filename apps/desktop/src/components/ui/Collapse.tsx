import type { ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { EASE_EMPHASIZED, MOTION } from "../../lib/tokens/motion";

interface CollapseProps {
  open: boolean;
  children: ReactNode;
  /** Reveal duration in seconds; defaults to MOTION.panel. */
  duration?: number;
  className?: string;
}

/**
 * Disclosure reveal for SMALL, bounded content — one input row, a
 * breadcrumb, a short fieldset. Encapsulates the app's grid-rows tween
 * (0fr ↔ 1fr + inner min-h-0 clip) with the content blurring into focus.
 *
 * The height tween is layout-bound (siblings relayout every frame), which
 * is why this primitive is reserved for fixed-height reveals. Heavy or
 * unbounded content (markdown bodies, code blocks, row lists) must NOT
 * height-tween — snap the layout and enter the content with RISE_IN /
 * DISSOLVE_OUT instead; grid-rows reveals over large subtrees shipped
 * jank twice.
 *
 * Note: the animated `filter` makes this wrapper a containing block —
 * don't anchor position:fixed descendants inside (portals are fine).
 */
export function Collapse({ open, children, duration = MOTION.panel, className }: CollapseProps) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ gridTemplateRows: "0fr", opacity: 0, filter: "blur(2px)" }}
          animate={{ gridTemplateRows: "1fr", opacity: 1, filter: "blur(0px)" }}
          exit={{ gridTemplateRows: "0fr", opacity: 0, filter: "blur(2px)" }}
          transition={{ duration, ease: EASE_EMPHASIZED }}
          style={{ display: "grid" }}
          className={className}
        >
          <div className="min-h-0 overflow-hidden">{children}</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
