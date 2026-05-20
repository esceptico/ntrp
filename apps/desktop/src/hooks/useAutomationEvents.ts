import { useEffect } from "react";
import { useStore } from "../store";
import { fetchAutomations, refreshLoops } from "../actions";
import { type AppConfig } from "../api";

/** SSE events emitted on `/automations/events`. The backend multiplexes
 *  all automations onto this single stream (one channel for the whole
 *  system, not per-task). `status` is a short human-readable string the
 *  backend assembles from the latest tool call, e.g. "bash_exec..." or
 *  "read_file: tasks.md". `automation_finished` carries the final result
 *  string and signals that the row should drop out of the running list. */
type AutomationEvent =
  | { type: "automation_progress"; task_id: string; status: string; seq?: number }
  | { type: "automation_finished"; task_id: string; result: string | null; seq?: number }
  | { type: "stream_keepalive"; latest_seq: number; seq?: number }
  | { type: "stream_reset"; reason: string; seq?: number };

function headersFor(config: AppConfig): HeadersInit {
  return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
}

export function automationEventsUrl(serverUrl: string, afterSeq: number | undefined): string {
  const url = new URL(`${serverUrl}/automations/events`);
  if (afterSeq !== undefined) {
    url.searchParams.set("after_seq", String(afterSeq));
  }
  return url.toString();
}

export function reduceAutomationStreamCursor(
  current: number | undefined,
  event: Pick<AutomationEvent, "seq" | "type"> & { latest_seq?: number },
): number | undefined {
  const next = typeof event.latest_seq === "number" ? event.latest_seq : event.seq;
  if (typeof next !== "number") return current;
  return Math.max(current ?? 0, next);
}

/** Subscribe to `/automations/events` for the lifetime of the app. The
 *  hook owns transport only; automation stream status and per-task
 *  projections live in the automation domain. */
export function useAutomationEvents(): void {
  const config = useStore((s) => s.config);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let afterSeq: number | undefined;

    const store = () => useStore.getState();

    // Long-running SSE loop with reconnect on drop. Mirrors the chat
    // events fallback in useEvents (the desktop preload's
    // event-bridge is keyed to chat session_ids so we can't reuse it
    // here — automations have their own URL).
    void (async () => {
      while (!disposed && !controller.signal.aborted) {
        try {
          store().automationStreamConnecting();
          const response = await fetch(automationEventsUrl(config.serverUrl, afterSeq), {
            headers: { ...headersFor(config), Accept: "text/event-stream" },
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            throw new Error(`automation event stream failed: ${response.status}`);
          }
          store().automationStreamConnected();

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
                afterSeq = reduceAutomationStreamCursor(afterSeq, event);
                if (event.type === "automation_progress") {
                  store().automationProgress(event.task_id, event.status);
                  // The "starting..." status is the scheduler's fire signal —
                  // server has just bumped next_run_at to the next slot.
                  // Pull loops for the current session so the countdown chip
                  // resets immediately instead of pinning at 0s until the
                  // next 3s poll.
                  if (event.status === "starting...") {
                    const sid = useStore.getState().currentSessionId;
                    if (sid) void refreshLoops(sid);
                  }
                } else if (event.type === "automation_finished") {
                  store().automationFinished(event.task_id);
                  // Refresh the automations list so the row leaves the
                  // sidebar card immediately rather than after the next
                  // 20s poll catches up to running_since going null.
                  void fetchAutomations();
                } else if (event.type === "stream_reset") {
                  void fetchAutomations();
                  const sid = useStore.getState().currentSessionId;
                  if (sid) void refreshLoops(sid);
                }
              } catch {
                /* keep-alive / non-data line */
              }
            }
          }
          if (!disposed && !controller.signal.aborted) {
            store().automationStreamStale();
            await new Promise((resolve) => setTimeout(resolve, 1500));
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          store().automationStreamFailed(
            error instanceof Error ? error.message : String(error),
          );
          // Backoff briefly before reconnecting so a server flap
          // doesn't turn into a tight reconnect loop.
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    })();

    return () => {
      disposed = true;
      controller.abort();
      store().automationStreamIdle();
    };
  }, [config]);
}
