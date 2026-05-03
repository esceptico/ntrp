import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";

const EASE = [0.32, 0.72, 0, 1] as const;

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
      transition={{ layout: { duration: 0.2, ease: EASE } }}
      className={clsx(
        "relative inline-block overflow-hidden align-baseline",
        mono && "tabular-nums",
      )}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "-100%" }}
          transition={{ duration: 0.18, ease: EASE }}
          className="inline-block"
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </motion.span>
  );
}
