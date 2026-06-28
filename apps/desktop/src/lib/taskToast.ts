import type { BackgroundAgent } from "@/store/background-agent-domain";

export type ToastStatus = "completed" | "failed" | "cancelled";

export type ToastTarget =
  | { kind: "session"; sessionId: string }
  | { kind: "automation" };

export interface Toast {
  id: string;
  title: string;
  detail?: string;
  status: ToastStatus;
  target: ToastTarget;
}

/** Terminal states that warrant a toast. Deliberately excludes "interrupted"
 *  and "cancel_requested" — those are mid-cancel, not user-facing completions. */
export function isTerminalStatus(status: string): status is ToastStatus {
  return status === "completed" || status === "failed" || status === "cancelled";
}

/** Toast for a background agent that reached a terminal state. Returns null
 *  when it is not terminal, or when the user is already looking at its session
 *  (suppress redundant noise). */
export function backgroundAgentToast(
  agent: BackgroundAgent,
  currentSessionId: string | null,
): Toast | null {
  if (!isTerminalStatus(agent.status)) return null;
  if (agent.sessionId === currentSessionId) return null;
  return {
    id: `bg:${agent.sessionId}:${agent.taskId}`,
    title: agent.command,
    detail: agent.detail,
    status: agent.status,
    target: { kind: "session", sessionId: agent.sessionId },
  };
}

/** Toast for a finished scheduled automation. Returns null when the automations
 *  modal is open (the user is already looking at it). */
export function automationToast(args: {
  taskId: string;
  name: string | null;
  result: string | null;
  automationsOpen: boolean;
}): Toast | null {
  if (args.automationsOpen) return null;
  return {
    id: `auto:${args.taskId}`,
    title: args.name ?? "Scheduled task",
    detail: args.result ?? undefined,
    status: "completed",
    target: { kind: "automation" },
  };
}
