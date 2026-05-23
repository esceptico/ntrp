import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2, Sparkles } from "lucide-react";
import { useStore } from "../store";
import { MOTION, EASE_OUT } from "../lib/motion";
import { ICON } from "../lib/icons";

const TOAST_VISIBLE_MS = 4500;
type LastCompaction = { before: number; after: number; at: number };
const claimedCompactionToasts = new Set<string>();

function compactionToastKey(sessionId: string | null, compaction: LastCompaction): string {
  return `${sessionId ?? "unknown"}:${compaction.at}:${compaction.before}:${compaction.after}`;
}

function claimCompactionToast(sessionId: string | null, compaction: LastCompaction | null): boolean {
  if (!compaction) return false;
  const key = compactionToastKey(sessionId, compaction);
  if (claimedCompactionToasts.has(key)) return false;
  claimedCompactionToasts.add(key);
  return true;
}

export const claimCompactionToastForTest = claimCompactionToast;

export function resetCompactionToastClaimsForTest() {
  claimedCompactionToasts.clear();
}

export function CompactionIndicator() {
  const sessionId = useStore((s) => s.currentSessionId);
  const compacting = useStore((s) => s.compacting);
  const lastCompaction = useStore((s) => s.lastCompaction);
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    if (!claimCompactionToast(sessionId, lastCompaction)) return;
    setShowToast(true);
    const t = setTimeout(() => setShowToast(false), TOAST_VISIBLE_MS);
    return () => clearTimeout(t);
  }, [sessionId, lastCompaction]);

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
            size={ICON.XS}
            strokeWidth={2}
            className="text-muted animate-spin"
          />
          <span className="text-sm font-medium text-muted">
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
          <Sparkles size={ICON.XS} strokeWidth={2} className="text-faint" />
          <span className="text-sm text-faint">
            Conversation compacted ({lastCompaction.before} → {lastCompaction.after} messages)
          </span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
