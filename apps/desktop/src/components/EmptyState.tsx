import { Sparkles } from "lucide-react";
import { useStore } from "../store";
import { ICON } from "../lib/icons";

export function EmptyState() {
  const connected = useStore((s) => s.connected);
  return (
    <div className="mt-[14vh] mx-auto grid gap-5 justify-items-center text-center">
      <span
        aria-hidden
        className="grid place-items-center w-12 h-12 rounded-2xl bg-accent-soft text-accent-strong"
      >
        <Sparkles size={ICON.HERO} strokeWidth={1.6} />
      </span>
      <div className="grid gap-1.5 max-w-[420px]">
        <h2 className="m-0 text-2xl font-semibold tracking-[-0.018em] text-ink">
          {connected ? "What's on your mind?" : "Connect to get started"}
        </h2>
        <p className="m-0 text-base text-muted leading-snug">
          {connected
            ? "Send a message, or press ⌘K to search memory, agents, and tools."
            : "Open settings to point ntrp at your server."}
        </p>
      </div>
    </div>
  );
}
