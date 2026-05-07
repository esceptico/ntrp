import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2, Sparkles } from "lucide-react";
import { useStore } from "../store";
import { MOTION, EASE_OUT } from "../lib/motion";

const TOAST_VISIBLE_MS = 4500;

export function CompactionIndicator() {
  const compacting = useStore((s) => s.compacting);
  const lastCompaction = useStore((s) => s.lastCompaction);
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    if (!lastCompaction) return;
    setShowToast(true);
    const t = setTimeout(() => setShowToast(false), TOAST_VISIBLE_MS);
    return () => clearTimeout(t);
  }, [lastCompaction]);

  return (
    <AnimatePresence mode="wait">
      {compacting ? (
        <motion.div
          key="compacting"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -2 }}
          transition={{ duration: MOTION.palette, ease: EASE_OUT }}
          className="flex items-center gap-2 my-1"
        >
          <Loader2
            size={12}
            strokeWidth={2}
            className="text-muted animate-spin"
          />
          <span className="text-[12px] font-medium text-muted">
            Compacting conversation…
          </span>
        </motion.div>
      ) : showToast && lastCompaction ? (
        <motion.div
          key="compacted"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: MOTION.palette, ease: EASE_OUT }}
          className="flex items-center gap-2 my-1"
        >
          <Sparkles size={12} strokeWidth={1.8} className="text-faint" />
          <span className="text-[12px] text-faint">
            Conversation compacted ({lastCompaction.before} → {lastCompaction.after} messages)
          </span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
