import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { backgroundAgentToast, isTerminalStatus } from "../lib/taskToast";

/** Watches background agents for terminal transitions and raises a toast the
 *  first time each one finishes. Scheduled-automation toasts are raised from
 *  useAutomationEvents (that is where their event arrives). */
export function useTaskResultToasts() {
  const rows = useStore((s) => s.backgroundAgents.rows);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const pushToast = useStore((s) => s.pushToast);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const agent of Object.values(rows)) {
      const key = `bg:${agent.sessionId}:${agent.taskId}`;
      if (!isTerminalStatus(agent.status) || seen.current.has(key)) continue;
      seen.current.add(key); // mark even if suppressed, so it cannot re-fire later
      const toast = backgroundAgentToast(agent, currentSessionId);
      if (toast) pushToast(toast);
    }
  }, [rows, currentSessionId, pushToast]);
}
