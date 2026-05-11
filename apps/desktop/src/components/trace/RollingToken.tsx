import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { MOTION, EASE_EMPHASIZED } from "../../lib/motion";

const EASE = EASE_EMPHASIZED;

/**
 * Odometer-style slot. When `value` changes, the old token slides up and out
 * while the new token slides up and in from below. Width animates smoothly via
 * framer-motion's layout system. `mono` enables tabular-nums so digit width is
 * stable.
 */
export function RollingToken({ value, mono = false }: { value: string; mono?: boolean }) {
  return (
    <motion.span
      layout="size"
      transition={{ layout: { duration: MOTION.trace, ease: EASE } }}
      className={clsx(
        "relative inline-block overflow-hidden align-text-bottom",
        mono && "tabular-nums",
      )}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "-100%" }}
          transition={{ duration: MOTION.palette, ease: EASE }}
          className="inline-block"
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </motion.span>
  );
}
