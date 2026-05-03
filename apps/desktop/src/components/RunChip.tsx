import clsx from "clsx";
import { useStore } from "../store";

export function RunChip() {
  const running = useStore((s) => s.running);
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-medium tracking-[-0.005em]",
        running
          ? "bg-accent-soft text-accent-strong"
          : "bg-surface-soft text-muted",
      )}
    >
      <span
        className={clsx(
          "w-1.5 h-1.5 rounded-full",
          running ? "bg-accent animate-pulse-soft" : "bg-whisper",
        )}
      />
      {running ? "running" : "idle"}
    </span>
  );
}
