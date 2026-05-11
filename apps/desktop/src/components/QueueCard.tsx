import { Loader2, X } from "lucide-react";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { cancelQueuedMessage } from "../actions";
import { useStore, type QueuedMessage } from "../store";

const CARD_TRANSITION = { duration: 0.24, ease: [0.32, 0.72, 0, 1] as const };
const ROW_TRANSITION = { duration: 0.18, ease: [0.32, 0.72, 0, 1] as const };

/** Pending user messages submitted while the agent was running. Renders
 *  as a stack of cards peeking out from behind the composer — the
 *  composer covers the bottom of this card via negative margin so the
 *  visual reads as "next up in the queue".
 *
 *  Animation budget:
 *  - Card: rises out from behind the composer on first add, sinks back
 *    on last remove. `layout` smooths height as rows are added /
 *    removed mid-life.
 *  - Row: fade + slight rise on enter, collapse height on exit. The
 *    height collapse is what makes neighbors slide up instead of
 *    snapping. */
export function QueueCard() {
  const queued = useStore((s) => s.queuedMessages);
  return (
    <AnimatePresence initial={false}>
      {queued.length > 0 && (
        <motion.div
          key="queue-card"
          layout
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 12 }}
          transition={CARD_TRANSITION}
          className="queue-card pointer-events-auto relative mx-4 -mb-3 rounded-t-[12px] rounded-b-[14px] border border-line border-b-0 bg-surface shadow-[var(--shadow-sm)]"
        >
          <motion.div layout className="flex flex-col gap-1 px-3 pt-2 pb-5">
            <AnimatePresence initial={false}>
              {queued.map((message) => (
                <motion.div
                  key={message.clientId}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0, marginTop: 0, marginBottom: 0 }}
                  transition={ROW_TRANSITION}
                  className="overflow-hidden"
                >
                  <QueueRow message={message} />
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function QueueRow({ message }: { message: QueuedMessage }) {
  const cancelling = message.status === "cancelling";
  const failed = message.status === "failed";
  const disabled = cancelling || message.status === "sent";
  return (
    <div className="group/queue-row flex items-center gap-2 min-w-0">
      <motion.span
        aria-hidden
        animate={{
          backgroundColor: failed
            ? "var(--color-bad)"
            : cancelling
              ? "var(--color-faint)"
              : "var(--color-accent)",
        }}
        transition={{ duration: 0.18 }}
        className="shrink-0 w-1 h-1 rounded-full"
      />
      <span
        className={clsx(
          "min-w-0 flex-1 truncate text-[13px] tracking-[-0.005em] transition-colors",
          cancelling ? "text-faint italic" : failed ? "text-bad" : "text-ink-soft",
        )}
        title={message.text}
      >
        {message.text || (message.images?.length ? `${message.images.length} image(s)` : "")}
      </span>
      {message.images && message.images.length > 0 && !cancelling && (
        <span className="shrink-0 text-[11px] text-faint tabular-nums">
          +{message.images.length} img
        </span>
      )}
      <button
        type="button"
        onClick={() => void cancelQueuedMessage(message.clientId)}
        disabled={disabled}
        title={cancelling ? "Cancelling…" : "Cancel"}
        aria-label="Cancel queued message"
        className="grid place-items-center w-5 h-5 shrink-0 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-faint"
      >
        {cancelling ? <Loader2 size={12} strokeWidth={2} className="animate-spin" /> : <X size={12} strokeWidth={2} />}
      </button>
    </div>
  );
}
