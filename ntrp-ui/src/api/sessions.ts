import type { Config } from "../types.js";
import { api } from "./fetch.js";

export async function getSession(config: Config, sessionId?: string): Promise<{
  session_id: string;
  integrations: string[];
  integration_errors: Record<string, string>;
  skip_approvals: boolean;
  name?: string | null;
}> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  return api.get(`${config.serverUrl}/session${params}`);
}

export interface HistoryToolCall {
  id: string;
  name: string;
  arguments?: string;
}

export interface HistoryMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls?: HistoryToolCall[];
  tool_call_id?: string;
  images?: Array<{ media_type: string; data: string }>;
}

export async function getHistory(config: Config, sessionId?: string): Promise<{ messages: HistoryMessage[] }> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  return api.get(`${config.serverUrl}/session/history${params}`);
}

export interface SessionListItem {
  session_id: string;
  started_at: string;
  last_activity: string;
  name: string | null;
  message_count: number;
  archived_at?: string | null;
}

export async function listSessions(config: Config): Promise<{ sessions: SessionListItem[] }> {
  return api.get<{ sessions: SessionListItem[] }>(`${config.serverUrl}/sessions`);
}

export async function createSession(config: Config, name?: string): Promise<SessionListItem> {
  const body = name ? { name } : {};
  return api.post<SessionListItem>(`${config.serverUrl}/sessions`, body);
}

export async function renameSession(config: Config, sessionId: string, name: string): Promise<{ session_id: string; name: string }> {
  return api.patch<{ session_id: string; name: string }>(`${config.serverUrl}/sessions/${sessionId}`, { name });
}

export async function deleteSession(config: Config, sessionId: string): Promise<{ status: string; session_id: string }> {
  return api.delete<{ status: string; session_id: string }>(`${config.serverUrl}/sessions/${sessionId}`);
}

export async function listArchivedSessions(config: Config): Promise<{ sessions: SessionListItem[] }> {
  return api.get<{ sessions: SessionListItem[] }>(`${config.serverUrl}/sessions/archived`);
}

export async function restoreSession(config: Config, sessionId: string): Promise<{ status: string; session_id: string }> {
  return api.post<{ status: string; session_id: string }>(`${config.serverUrl}/sessions/${sessionId}/restore`);
}

export async function permanentlyDeleteSession(config: Config, sessionId: string): Promise<{ status: string; session_id: string }> {
  return api.delete<{ status: string; session_id: string }>(`${config.serverUrl}/sessions/${sessionId}/permanent`);
}

export async function revertSession(config: Config, sessionId?: string, turns = 1): Promise<{ user_message: string; reverted_count: number }> {
  const body: Record<string, unknown> = {};
  if (sessionId) body.session_id = sessionId;
  if (turns > 1) body.turns = turns;
  return api.post<{ user_message: string; reverted_count: number }>(`${config.serverUrl}/session/revert`, body);
}

export async function clearSession(config: Config, sessionId?: string): Promise<{ status: string; session_id: string }> {
  const body = sessionId ? { session_id: sessionId } : {};
  return api.post<{ status: string; session_id: string }>(`${config.serverUrl}/session/clear`, body);
}
