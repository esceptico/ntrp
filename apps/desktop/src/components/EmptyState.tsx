import { useStore } from "../store";

export function EmptyState() {
  const connected = useStore((s) => s.connected);
  return (
    <div className="mt-[10vh] grid gap-2.5 text-center text-muted">
      <h2 className="m-0 text-[22px] font-semibold tracking-[-0.02em] text-ink">
        {connected ? "What's on your mind?" : "Connect to get started"}
      </h2>
      <p className="m-0 text-[13.5px] text-muted">
        {connected
          ? "Send a message to begin a new exchange."
          : "Open settings to point ntrp at your server."}
      </p>
    </div>
  );
}
