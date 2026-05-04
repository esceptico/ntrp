import { useStore } from "../store";

/** Inline "Thinking" indicator shown whenever the agent is running but the
 *  user isn't currently watching tokens stream into an assistant message.
 *  Reasoning, tool calls, and activity blocks all keep the shimmer visible —
 *  the only thing that hides it is an actively-streaming assistant turn,
 *  where the streaming text is its own "something is happening" signal. */
export function ThinkingIndicator() {
  const running = useStore((s) => s.running);
  const order = useStore((s) => s.order);
  const messages = useStore((s) => s.messages);

  if (!running) return null;

  const lastId = order[order.length - 1];
  const last = lastId ? messages.get(lastId) : null;
  if (last?.role === "assistant") return null;

  return (
    <div className="flex items-center gap-2 my-1 animate-fade-in">
      <span className="reasoning-head text-[12px] font-medium" data-state="streaming">
        Thinking
      </span>
    </div>
  );
}
