import { motion } from "motion/react";
import type { ReactNode } from "react";
import {
  RISE_IN,
  RISE_SETTLED,
  DISSOLVE_OUT,
  MOTION,
  EASE_OUT,
  EASE_DECELERATE,
} from "@/lib/tokens/motion";

/**
 * The house row/section reveal. Content rises into focus on a panel-tier
 * decelerate, and dissolves a tier quicker on exit. Wraps the verbatim
 * `initial={RISE_IN} animate={RISE_SETTLED} exit={…DISSOLVE_OUT…}` triplet
 * that was pasted across sections so it can't drift per call site.
 *
 * Put the `key` on `<Reveal>` directly (callers inside `<AnimatePresence>`);
 * React forwards it. Sites that override the pose (`{...RISE_IN, y: -4}`),
 * change the duration/ease, or add `layout` are NOT this animation — leave
 * them on a hand-rolled `motion.div`.
 */
export function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={{ duration: MOTION.panel, ease: EASE_DECELERATE }}
    >
      {children}
    </motion.div>
  );
}
