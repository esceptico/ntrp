import { AnimatePresence, motion } from "motion/react";
import { EASE_OUT, MOTION, originFromEvent, RISE_IN, RISE_SETTLED } from "@/lib/tokens/motion";
import { useStore } from "@/stores";

// The single load-bearing "needs you" signal: a run is paused waiting on
// an approval. One amber row that opens the review modal.
export function ApprovalsRow() {
  const count = useStore((s) => s.pendingApprovals.length);
  const firstToolId = useStore((s) => s.pendingApprovals[0]?.toolId);
  const review = useStore((s) => s.setReviewingApproval);

  return (
    <AnimatePresence initial={false}>
      {count > 0 && firstToolId && (
        <motion.div
          key="approvals"
          initial={{ ...RISE_IN, y: -4 }}
          animate={RISE_SETTLED}
          exit={{ opacity: 0, scale: 0.97, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
          transition={{ duration: MOTION.row, ease: EASE_OUT }}
        >
          <button
            type="button"
            onClick={(e) => review(firstToolId, originFromEvent(e.currentTarget))}
            className="flex w-full items-center gap-2 rounded-[8px] bg-warn/10 px-2.5 py-2 text-left transition-[background-color,scale] duration-row ease-out hover:bg-warn/15 active:scale-[0.985]"
          >
            <span className="inline-block w-1.5 h-1.5 rounded-full shrink-0 bg-warn" aria-hidden />
            <span className="flex-1 text-xs text-ink-soft">
              {count} awaiting approval
            </span>
            <span className="shrink-0 text-2xs text-warn">Review →</span>
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
