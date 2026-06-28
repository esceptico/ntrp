import clsx from "clsx";
import { statusDotClass, type AgentRunStatus } from "@/lib/agentRun";

// Outcome is encoded by hue (green/red/grey/accent), so the dot needs a
// non-color cue: it carries an accessible name (and native title) per status.
// On terminal-capable surfaces (agent rows, trace) it is often the only
// status read-out, so a failed run must not be indistinguishable from a done
// one to SR/colorblind users.
const STATUS_LABEL: Record<AgentRunStatus | "running", string> = {
  running: "Running",
  cancel_requested: "Stopping",
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Idle",
};

// Generic semantic palette for non-agent dots (mcp connection state, budget
// dots, …). `neutral` is the currently-missing "off/disconnected" colour;
// the rest reuse the same hues as the run-status variants. Both bg-* and
// text-* so the breathing halo (box-shadow via currentColor) tints to match.
export type StatusDotTone = "neutral" | "ok" | "warn" | "bad" | "accent";

const TONE_CLASS: Record<StatusDotTone, string> = {
  neutral: "bg-line text-line",
  ok: "bg-ok text-ok",
  warn: "bg-warn text-warn",
  bad: "bg-bad text-bad",
  accent: "bg-accent text-accent",
};

// Small colored "this thing is X" dot. The breathing halo (a box-shadow
// using `currentColor`) only fires while running/pulsing. Shared by the
// sidebar agents hub, session rows, the inline agent card, automations
// (via `status`), and generic surfaces like mcp/budget dots (via `tone`).
export function StatusDot({
  status,
  tone,
  pulse = false,
}: {
  status?: AgentRunStatus | "running";
  tone?: StatusDotTone;
  pulse?: boolean;
}) {
  // `tone` drives a generic dot; otherwise the run-status path is unchanged.
  const breathing = tone
    ? pulse
    : pulse && (status === "running" || status === "cancel_requested");
  const colorClass = tone ? TONE_CLASS[tone] : statusDotClass(status!);
  const label = tone ? undefined : STATUS_LABEL[status!];
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={clsx(
        // transition-colors eases the status color change (running→done→
        // failed) instead of hard-cutting; the breathe halo is a separate
        // keyframe that just stops when `breathing` drops. panel (220ms) is
        // the gentlest interactive stop on the scale — a snappier flip reads
        // as a glitch on something this small.
        "inline-block w-1.5 h-1.5 rounded-full shrink-0 transition-colors duration-panel ease-out",
        colorClass,
        breathing && "status-dot-breathe",
      )}
    />
  );
}
