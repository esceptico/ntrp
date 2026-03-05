import type { ServerEvent, Config } from "../types.js";
import { api, getApiKey } from "./fetch.js";

export async function* streamChat(
  message: string,
  sessionId: string | null,
  config: Config,
  skipApprovals: boolean = false,
  signal?: AbortSignal,
): AsyncGenerator<ServerEvent, void, unknown> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const apiKey = getApiKey();
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const response = await fetch(`${config.serverUrl}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, session_id: sessionId, skip_approvals: skipApprovals }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Server error: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
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
              yield parsed as ServerEvent;
            }
          } catch {
            // Ignore parse errors (e.g., ping messages)
          }
        }
      }
    }

    // Flush remaining decoder bytes and process any trailing event
    buffer += decoder.decode();
    const remaining = buffer.trim();
    if (remaining.startsWith("data: ")) {
      try {
        const parsed = JSON.parse(remaining.slice(6));
        if (parsed && typeof parsed.type === "string") {
          yield parsed as ServerEvent;
        }
      } catch {}
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    if (error instanceof TypeError && (error.message === "terminated" || error.message.includes("terminated"))) {
      const errorEvent: ServerEvent = { type: "error", message: "Connection to server was terminated unexpectedly", recoverable: false };
      yield errorEvent;
      return;
    }
    throw error;
  }
}

export async function cancelRun(runId: string, config: Config): Promise<void> {
  await api.post(`${config.serverUrl}/cancel`, { run_id: runId });
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
