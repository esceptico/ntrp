import { memo } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { MOTION, EASE_EMPHASIZED } from "../../lib/tokens/motion";

const EASE = EASE_EMPHASIZED;

/**
 * Odometer-style slot. When `value` changes, the old token slides up and out
 * while the new token slides up and in from below. Width animates smoothly via
 * framer-motion's layout system. `mono` enables tabular-nums so digit width is
 * stable.
 *
 * Wrapped in React.memo so parent re-renders (which fire on every tool-tick
 * because the items array changes) don't trigger motion's layout-measurement
 * pass on tokens whose value didn't actually change. When 3 tokens sit in a
 * header and only the count changes, only that one pays the layout cost.
 */
export const RollingToken = memo(function RollingToken({
  value,
  mono = false,
  motionDisabled = false,
}: {
  value: string;
  mono?: boolean;
  motionDisabled?: boolean;
}) {
  return (
    <motion.span
      layout={motionDisabled ? false : "size"}
      transition={
        motionDisabled
          ? { layout: { duration: 0 } }
          : { layout: { duration: MOTION.trace, ease: EASE } }
      }
      className={clsx(
        "relative inline-block overflow-hidden align-text-bottom",
        mono && "tabular-nums",
      )}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={motionDisabled ? false : { y: "100%" }}
          animate={{ y: 0 }}
          exit={motionDisabled ? { y: 0 } : { y: "-100%" }}
          transition={
            motionDisabled
              ? { duration: 0 }
              : { duration: MOTION.palette, ease: EASE }
          }
          className="inline-block"
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </motion.span>
  );
});
