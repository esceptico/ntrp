import { motion } from "motion/react";
import type { SliceAsk } from "@/api/slices";
import { useStore } from "@/stores";
import { runAutomation } from "@/actions/automations";
import { switchSession } from "@/actions/sessions";
import { primaryActionFor } from "@/lib/askActions";
import { RISE_IN, RISE_SETTLED, ROW_EXIT, SPRING_ROW_ENTRY, MOTION, EASE_OUT } from "@/lib/tokens/motion";

// `kind` doubles as severity and verb. The dot uses the status palette
// (attention kinds warmer); the verb relabels an open_page button so the
// action reads as the judgment call ("Decide") instead of a generic
// "Review" on every row. Mirrors AskCard's KIND_DOT so Home and the room
// speak the same language.
const KIND: Record<SliceAsk["kind"], { dot: string; verb: string }> = {
  review: { dot: "bg-muted", verb: "Review" },
  decide: { dot: "bg-accent", verb: "Decide" },
  act: { dot: "bg-warn", verb: "Act" },
  drift: { dot: "bg-bad", verb: "Resolve" },
};

/** A single focus-set row: a slice's one ask, made legible. Eyebrow line is
 *  the slice title + a severity dot; the ask reads in full (up to two
 *  lines) instead of a truncated teaser; the action button carries the
 *  kind's verb. Enters RISE_IN/SPRING_ROW_ENTRY, retires ROW_EXIT via the
 *  caller's AnimatePresence (keyed by ask.id, so a text change is a fresh
 *  mount, not an in-place edit). */
export function FocusRow({ ask, sliceTitle }: { ask: SliceAsk; sliceTitle: string }) {
  const openSlice = useStore((s) => s.openSlice);
  const automations = useStore((s) => s.automations);
  const primaryAction = primaryActionFor(ask, automations, {
    switchSession: (id) => void switchSession(id),
    runAutomation: (taskId) => void runAutomation(taskId),
    openSlice,
  });

  const kind = KIND[ask.kind];
  // open_page is "go handle it in the slice" — relabel with the kind verb.
  // Behavioral verbs (Open/Retry) keep primaryActionFor's own label.
  const actionLabel =
    primaryAction && ask.actions[0]?.verb === "open_page" ? kind.verb : primaryAction?.label;

  return (
    <motion.div
      layout
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_ROW_ENTRY}
      className="group/row flex min-w-0 items-center gap-3.5 rounded-[12px] bg-surface-soft px-4 py-3"
    >
      <div className="grid min-w-0 flex-1 gap-1">
        <button
          type="button"
          onClick={() => openSlice(ask.slice_key)}
          className="flex min-w-0 items-center gap-2 text-left"
        >
          <span aria-hidden className={`size-1.5 shrink-0 rounded-full ${kind.dot}`} />
          <span className="min-w-0 truncate text-xs font-medium text-muted group-hover/row:text-ink">
            {sliceTitle}
          </span>
        </button>
        <p className="m-0 min-w-0 text-sm leading-snug text-ink line-clamp-2 [overflow-wrap:anywhere]">
          {ask.text}
        </p>
      </div>
      {primaryAction && (
        <button
          type="button"
          onClick={primaryAction.run}
          className="shrink-0 self-center rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-soft"
        >
          {actionLabel}
        </button>
      )}
    </motion.div>
  );
}
