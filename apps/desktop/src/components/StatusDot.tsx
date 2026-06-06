import clsx from "clsx";
import { statusDotClass, type AgentRunStatus } from "../lib/agentRun";

// Small colored "this thing is X" dot. The breathing halo (a box-shadow
// using `currentColor`) only fires while running. Shared by the sidebar
// agents hub, session rows, the inline agent card, and automations.
export function StatusDot({
  status,
  pulse = false,
}: {
  status: AgentRunStatus | "running";
  pulse?: boolean;
}) {
  const breathing = pulse && (status === "running" || status === "cancel_requested");
  return (
    <span
      className={clsx(
        "inline-block w-1.5 h-1.5 rounded-full shrink-0",
        statusDotClass(status),
        breathing && "status-dot-breathe",
      )}
      aria-hidden
    />
  );
}
