import type { ServerEvent, Config } from "../types.js";
import { api, getApiKey } from "./fetch.js";

const SSE_RECONNECT_BASE_MS = 1000;
const SSE_RECONNECT_MAX_MS = 10000;

export function connectEvents(
  sessionId: string,
  config: Config,
  onEvent: (event: ServerEvent) => void | Promise<void>,
  options?: { stream?: boolean },
  onError?: (error: Error) => void,
): () => void {
  const controller = new AbortController();
  const streamParam = options?.stream ? "?stream=true" : "";

  (async () => {
    let retries = 0;

    while (!controller.signal.aborted) {
      const headers: Record<string, string> = {};
      const apiKey = getApiKey();
      if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

      try {
        const response = await fetch(`${config.serverUrl}/chat/events/${sessionId}${streamParam}`, {
          headers,
          signal: controller.signal,
        });

        if (!response.ok) throw new Error(`SSE connect failed: ${response.status}`);

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        retries = 0; // Connected successfully
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const parsed = JSON.parse(line.slice(6));
                if (parsed && typeof parsed.type === "string") {
                  await onEvent(parsed as ServerEvent);
                }
              } catch {
                // Ignore parse errors (keepalive comments, etc.)
              }
            }
          }
        }
        // Stream ended normally — reconnect
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        onError?.(error as Error);
      }

      // Reconnect with exponential backoff, respecting abort
      const delay = Math.min(SSE_RECONNECT_BASE_MS * 2 ** retries, SSE_RECONNECT_MAX_MS);
      retries++;
      await new Promise<void>(resolve => {
        const timer = setTimeout(resolve, delay);
        controller.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
      });
    }
  })();

  return () => controller.abort();
}

export async function sendChatMessage(
  message: string,
  sessionId: string,
  config: Config,
  skipApprovals: boolean = false,
): Promise<{ run_id: string; session_id: string }> {
  return api.post(`${config.serverUrl}/chat/message`, {
    message,
    session_id: sessionId,
    skip_approvals: skipApprovals,
  }) as Promise<{ run_id: string; session_id: string }>;
}

export async function cancelRun(runId: string, config: Config): Promise<void> {
  await api.post(`${config.serverUrl}/cancel`, { run_id: runId });
}

export async function backgroundRun(runId: string, config: Config): Promise<void> {
  await api.post(`${config.serverUrl}/chat/background`, { run_id: runId });
}

export async function submitToolResult(
  runId: string,
  toolId: string,
  result: string,
  approved: boolean,
  config: Config
): Promise<void> {
  await api.post(`${config.serverUrl}/tools/result`, { run_id: runId, tool_id: toolId, result, approved });
}
