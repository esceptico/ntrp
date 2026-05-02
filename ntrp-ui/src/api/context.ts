import type { Config } from "../types.js";
import { api } from "./fetch.js";

export async function compactContext(config: Config, sessionId?: string): Promise<{ status: string; message: string }> {
  const body = sessionId ? { session_id: sessionId } : {};
  return api.post<{ status: string; message: string }>(`${config.serverUrl}/compact`, body, { timeout: 0 });
}

export async function getContextUsage(config: Config, sessionId?: string): Promise<{
  model: string;
  limit: number;
  total: number | null;
  message_count: number;
  tool_count: number;
  visible_tool_count: number;
  deferred_tool_count: number;
  loaded_tool_count: number;
}> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  return api.get(`${config.serverUrl}/context${params}`);
}
