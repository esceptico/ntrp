import { AnimatePresence, motion } from "motion/react";
import { Loader2 } from "lucide-react";
import { useStore } from "@/store";
import { MOTION, EASE_OUT } from "@/lib/tokens/motion";
import { ICON } from "@/lib/icons";

export function CompactionIndicator() {
  const compacting = useStore((s) => s.compacting);

  return <CompactionIndicatorContent compacting={compacting} />;
}

export function CompactionIndicatorContent({ compacting }: { compacting: boolean }) {
  return (
    <AnimatePresence>
      {compacting ? (
        <motion.div
          key="compacting"
          role="status"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -2, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
          transition={{ duration: MOTION.palette, ease: EASE_OUT }}
          className="flex items-center gap-2 my-1"
        >
          <Loader2
            size={ICON.XS}
            strokeWidth={2}
            aria-hidden
            className="text-muted animate-spin"
          />
          <span className="text-sm font-medium text-muted">
            Compacting conversation…
          </span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
