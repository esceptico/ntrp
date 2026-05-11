import { useEffect } from "react";
import { useStore } from "../store";
import { fetchAutomations } from "../actions";
import { type AppConfig } from "../api";

/** SSE events emitted on `/automations/events`. The backend multiplexes
 *  all automations onto this single stream (one channel for the whole
 *  system, not per-task). `status` is a short human-readable string the
 *  backend assembles from the latest tool call, e.g. "bash_exec..." or
 *  "read_file: tasks.md". `automation_finished` carries the final result
 *  string and signals that the row should drop out of the running list. */
type AutomationEvent =
  | { type: "automation_progress"; task_id: string; status: string }
  | { type: "automation_finished"; task_id: string; result: string | null };

function headersFor(config: AppConfig): HeadersInit {
  return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
}

/** Subscribe to `/automations/events` for the lifetime of the app. Live
 *  status strings land in `state.automationStatuses[task_id]`; on
 *  `automation_finished` we drop the key and refresh the automations
 *  list so the sidebar card removes the now-stopped row immediately
 *  (without waiting for the 20s poll). */
export function useAutomationEvents(): void {
  const config = useStore((s) => s.config);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;

    const setStatus = (taskId: string, status: string) =>
      useStore.getState().setAutomationStatus(taskId, status);
    const clearStatus = (taskId: string) =>
      useStore.getState().clearAutomationStatus(taskId);

    const url = `${config.serverUrl}/automations/events`;

    // Long-running SSE loop with reconnect on drop. Mirrors the chat
    // events fallback in useEvents (the desktop preload's
    // event-bridge is keyed to chat session_ids so we can't reuse it
    // here — automations have their own URL).
    void (async () => {
      while (!disposed && !controller.signal.aborted) {
        try {
          const response = await fetch(url, {
            headers: { ...headersFor(config), Accept: "text/event-stream" },
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            throw new Error(`automation event stream failed: ${response.status}`);
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (!disposed && !controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                const event = JSON.parse(line.slice(6)) as AutomationEvent;
                if (event.type === "automation_progress") {
                  setStatus(event.task_id, event.status);
                } else if (event.type === "automation_finished") {
                  clearStatus(event.task_id);
                  // Refresh the automations list so the row leaves the
                  // sidebar card immediately rather than after the next
                  // 20s poll catches up to running_since going null.
                  void fetchAutomations();
                }
              } catch {
                /* keep-alive / non-data line */
              }
            }
          }
        } catch {
          if (controller.signal.aborted) return;
          // Backoff briefly before reconnecting so a server flap
          // doesn't turn into a tight reconnect loop.
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    })();

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [config]);
}
