import { motion } from "motion/react";
import type { SliceAsk } from "@/api/slices";
import { useStore } from "@/stores";
import { runAutomation } from "@/actions/automations";
import { switchSession } from "@/actions/sessions";
import { primaryActionFor } from "@/lib/askActions";
import { RISE_IN, RISE_SETTLED, ROW_EXIT, SPRING_ROW_ENTRY, MOTION, EASE_OUT } from "@/lib/tokens/motion";

/** A single focus-set row: 52px tonal card, slice key small-caps on the
 *  left, ask text in the middle, primary action on the right. Enters with
 *  RISE_IN/SPRING_ROW_ENTRY, retires with ROW_EXIT (list membership is
 *  driven by AnimatePresence in FocusList — this component only owns its
 *  own pose). Rows are keyed by ask.id (not slice_key), so a text change
 *  is a fresh row mounting via AnimatePresence, not an in-place swap —
 *  FieldSwap (built for in-place swaps) would be inert here (dir={0}) and
 *  was removed. */
export function FocusRow({ ask }: { ask: SliceAsk }) {
  const openSlice = useStore((s) => s.openSlice);
  const automations = useStore((s) => s.automations);
  const primaryAction = primaryActionFor(ask, automations, {
    switchSession: (id) => void switchSession(id),
    runAutomation: (taskId) => void runAutomation(taskId),
    openSlice,
  });

  return (
    <motion.div
      layout
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_ROW_ENTRY}
      className="flex h-[52px] items-center gap-3 rounded-[10px] bg-surface-soft px-3.5"
    >
      <button
        type="button"
        onClick={() => openSlice(ask.slice_key)}
        className="w-[76px] shrink-0 text-left text-2xs font-semibold tracking-wide text-muted uppercase [font-variant-caps:small-caps] hover:text-ink"
      >
        {ask.slice_key}
      </button>
      <div className="min-w-0 flex-1 text-sm text-ink">
        <span className="block truncate">{ask.text}</span>
      </div>
      {primaryAction && (
        <button
          type="button"
          onClick={primaryAction.run}
          className="shrink-0 rounded-md bg-ink px-2.5 py-1 text-xs font-medium text-on-ink hover:opacity-90"
        >
          {primaryAction.label}
        </button>
      )}
    </motion.div>
  );
}
