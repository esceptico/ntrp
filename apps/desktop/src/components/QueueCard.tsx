import { Loader2, X } from "lucide-react";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { cancelQueuedMessage } from "../actions";
import { useStore, type QueuedMessage } from "../store";

/** Pending user messages submitted while the agent was running. Renders
 *  as a stack of cards peeking out from behind the composer — the
 *  composer covers the bottom of this card via negative margin so the
 *  visual reads as "next up in the queue". */
export function QueueCard() {
  const queued = useStore((s) => s.queuedMessages);
  if (queued.length === 0) return null;

  return (
    <div className="queue-card pointer-events-auto relative mx-4 -mb-3 rounded-t-[12px] rounded-b-[14px] border border-line border-b-0 bg-surface shadow-[var(--shadow-sm)]">
      {/* Inner padding leaves room for the composer to overlap the
          bottom edge without clipping any row content. */}
      <div className="flex flex-col gap-1 px-3 pt-2 pb-5">
        <AnimatePresence initial={false}>
          {queued.map((message) => (
            <motion.div
              key={message.clientId}
              layout
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
            >
              <QueueRow message={message} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function QueueRow({ message }: { message: QueuedMessage }) {
  const cancelling = message.status === "cancelling";
  const failed = message.status === "failed";
  const disabled = cancelling || message.status === "sent";
  return (
    <div className="group/queue-row flex items-center gap-2 min-w-0">
      <span
        aria-hidden
        className={clsx(
          "shrink-0 w-1 h-1 rounded-full",
          failed ? "bg-bad" : cancelling ? "bg-faint" : "bg-accent",
        )}
      />
      <span
        className={clsx(
          "min-w-0 flex-1 truncate text-[12.5px] tracking-[-0.005em]",
          cancelling ? "text-faint italic" : failed ? "text-bad" : "text-ink-soft",
        )}
        title={message.text}
      >
        {message.text || (message.images?.length ? `${message.images.length} image(s)` : "")}
      </span>
      {message.images && message.images.length > 0 && !cancelling && (
        <span className="shrink-0 text-[10.5px] text-faint tabular-nums">
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
        {cancelling ? <Loader2 size={11} strokeWidth={2} className="animate-spin" /> : <X size={11} strokeWidth={2} />}
      </button>
    </div>
  );
}
