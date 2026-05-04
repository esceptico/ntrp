import { useStore } from "../store";

/** Inline "thinking" indicator shown at the bottom of the messages list when
 *  the agent is running but hasn't started producing visible output yet
 *  (no assistant text, no reasoning, no tool activity). The shimmer makes it
 *  obvious that something is happening, distinct from idle. */
export function ThinkingIndicator() {
  const running = useStore((s) => s.running);
  const order = useStore((s) => s.order);
  const messages = useStore((s) => s.messages);

  if (!running) return null;

  // Only show before the model has produced any visible output for this turn.
  // Once an assistant/reasoning/activity/tool message has been added, the run
  // chip in the header is enough — and the activity / reasoning blocks have
  // their own shimmers.
  const lastId = order[order.length - 1];
  const last = lastId ? messages.get(lastId) : null;
  if (last && last.role !== "user") return null;

  return (
    <div className="flex items-center gap-2 my-1 animate-fade-in">
      <span className="reasoning-head text-[12px] font-medium" data-state="streaming">
        Thinking
      </span>
    </div>
  );
}
