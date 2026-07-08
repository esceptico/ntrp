import { motion } from "motion/react";
import type { SliceAsk } from "@/api/slices";
import type { Automation } from "@/api/types";
import { useStore } from "@/stores";
import { runAutomation } from "@/actions/automations";
import { switchSession } from "@/actions/sessions";
import { fetchSliceDetail, resolveAsk } from "@/actions/slices";
import { primaryActionFor } from "@/lib/askActions";
import { IconButton } from "@/components/ui/IconButton";
import { Button } from "@/components/ui/Button";
import { ASK_KIND } from "@/lib/sliceKind";
import { RISE_IN, RISE_SETTLED, ROW_EXIT, SPRING_ROW_ENTRY, MOTION, EASE_OUT } from "@/lib/tokens/motion";
import { X } from "lucide-react";

/** Agent asks read as "headline — elaboration"; split on the first em-dash
 *  so the card can render the mock's title/description hierarchy. Asks
 *  without one are all title. */
function splitAsk(text: string): { title: string; detail: string | null } {
  const i = text.indexOf(" — ");
  if (i === -1) return { title: text, detail: null };
  return { title: text.slice(0, i), detail: text.slice(i + 3) };
}

/** Attention card for a slice's top ask: severity dot, title/detail, a
 *  buttons row (primary action + Discuss), dismiss ✕ in the corner.
 *  Discuss hands the ask to the room's scoped composer via `onDiscuss`.
 *  Retires with ROW_EXIT; list membership is the caller's AnimatePresence.
 *
 *  `open_page` actions route to `openSlice(ask.slice_key)` — a no-op
 *  inside the ask's own room, so the primary button is suppressed there
 *  and Discuss carries the card. */
export function AskCard({ ask, onDiscuss }: { ask: SliceAsk; onDiscuss?: (ask: SliceAsk) => void }) {
  const automations = useStore((s) => s.automations);
  const { title, detail } = splitAsk(ask.text);

  const isNoOpOpenPage = ask.actions[0]?.verb === "open_page";
  const primaryAction = isNoOpOpenPage
    ? null
    : primaryActionFor(ask, automations as Automation[] | null, {
        switchSession: (id) => void switchSession(id),
        runAutomation: (taskId) => void runAutomation(taskId),
        openSlice: (key) => useStore.getState().openSlice(key),
      });

  const dismiss = async () => {
    try {
      await resolveAsk(ask.slice_key, ask.id, "dismissed");
    } catch {
      useStore.getState().pushToast({
        id: `ask-dismiss-fail:${ask.slice_key}:${ask.id}`,
        title: "Couldn’t dismiss",
        status: "failed",
        target: { kind: "automation" },
      });
      await fetchSliceDetail(ask.slice_key);
    }
  };

  return (
    <motion.div
      layout
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_ROW_ENTRY}
      className="flex min-w-0 items-start gap-3 rounded-xl bg-surface-soft px-4 py-3.5"
    >
      <span aria-hidden className={`mt-[7px] size-1.5 shrink-0 rounded-full ${ASK_KIND[ask.kind].dot}`} />
      <div className="grid min-w-0 flex-1 gap-1">
        <div className="flex min-w-0 items-center gap-2">
          <p className="m-0 min-w-0 text-sm font-medium text-ink">{title}</p>
          <span className="shrink-0 text-2xs font-medium uppercase tracking-wide text-faint">
            {ASK_KIND[ask.kind].label}
          </span>
        </div>
        {detail && <p className="m-0 text-sm leading-snug text-muted">{detail}</p>}
        <div className="mt-2 flex items-center gap-2">
          {primaryAction && (
            <Button variant="primary" size="sm" onClick={primaryAction.run}>
              {primaryAction.label}
            </Button>
          )}
          {onDiscuss && (
            <Button variant="secondary" size="sm" onClick={() => onDiscuss(ask)}>
              Discuss
            </Button>
          )}
        </div>
      </div>
      <IconButton size="sm" title="Dismiss" onClick={() => void dismiss()}>
        <X className="size-3.5" />
      </IconButton>
    </motion.div>
  );
}
