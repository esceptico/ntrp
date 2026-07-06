import { motion } from "motion/react";
import type { SliceAsk } from "@/api/slices";
import type { Automation } from "@/api/types";
import { useStore } from "@/stores";
import { runAutomation } from "@/actions/automations";
import { switchSession } from "@/actions/sessions";
import { resolveAsk } from "@/actions/slices";
import { primaryActionFor } from "@/lib/askActions";
import { IconButton } from "@/components/ui/IconButton";
import { RISE_IN, RISE_SETTLED, ROW_EXIT, SPRING_ROW_ENTRY, MOTION, EASE_OUT } from "@/lib/tokens/motion";
import { X } from "lucide-react";

// `kind` doubles as severity: `act`/`drift` need attention sooner than a
// routine `review`/`decide` — tinted dot only, no badge chrome.
const KIND_DOT: Record<SliceAsk["kind"], string> = {
  review: "bg-muted",
  decide: "bg-accent",
  act: "bg-warn",
  drift: "bg-bad",
};

/** Attention card for a slice's top ask: severity dot, ask text, a primary
 *  action mapped from `ask.actions[0]` (shared askActions logic — same
 *  verb→handler map Home's FocusRow uses), and a dismiss ✕ that resolves
 *  the ask as "dismissed". Retires with ROW_EXIT; list membership (removal
 *  on resolve) is driven by the caller's AnimatePresence. */
export function AskCard({ ask }: { ask: SliceAsk }) {
  const automations = useStore((s) => s.automations);

  const primaryAction = primaryActionFor(ask, automations as Automation[] | null, {
    switchSession: (id) => void switchSession(id),
    runAutomation: (taskId) => void runAutomation(taskId),
    openSlice: (key) => useStore.getState().openSlice(key),
  });

  return (
    <motion.div
      layout
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_ROW_ENTRY}
      className="flex items-start gap-3 rounded-[10px] bg-surface-soft px-3.5 py-3"
    >
      <span aria-hidden className={`mt-1.5 size-1.5 shrink-0 rounded-full ${KIND_DOT[ask.kind]}`} />
      <p className="min-w-0 flex-1 text-sm text-ink">{ask.text}</p>
      <div className="flex shrink-0 items-center gap-1.5">
        {primaryAction && (
          <button
            type="button"
            onClick={primaryAction.run}
            className="rounded-md bg-ink px-2.5 py-1 text-xs font-medium text-on-ink hover:opacity-90"
          >
            {primaryAction.label}
          </button>
        )}
        <IconButton
          size="sm"
          title="Dismiss"
          onClick={() => void resolveAsk(ask.slice_key, ask.id, "dismissed")}
        >
          <X className="size-3.5" />
        </IconButton>
      </div>
    </motion.div>
  );
}
