/**
 * API client for communicating with the ntrp server.
 *
 * Tool execution is now handled locally (see ./tools/),
 * so we only need server communication for:
 * - Streaming chat (SSE)
 * - Submitting tool results back to server
 * - Session management
 */

import type { ServerEvent, Config } from "../types.js";
import { api } from "./fetch.js";

/**
 * Stream chat messages from the server via SSE.
 */
export async function* streamChat(
  message: string,
  sessionId: string | null,
  config: Config,
  yolo: boolean = false
): AsyncGenerator<ServerEvent, void, unknown> {
  const response = await fetch(`${config.serverUrl}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, yolo }),
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

      // Parse SSE events
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const event = JSON.parse(line.slice(6)) as ServerEvent;
            yield event;
          } catch {
            // Ignore parse errors (e.g., ping messages)
          }
        }
      }
    }
  } catch (error) {
    // Handle connection termination gracefully
    if (error instanceof TypeError && (error.message === "terminated" || error.message.includes("terminated"))) {
      // Connection was terminated - yield an error event for the UI
      yield { type: "error", message: "Connection to server was terminated unexpectedly" } as ServerEvent;
      return;
    }
    throw error;
  }
}

/**
 * Cancel an active run.
 */
export async function cancelRun(runId: string, config: Config): Promise<void> {
  const response = await fetch(`${config.serverUrl}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  });

  if (!response.ok) {
    throw new Error(`Failed to cancel run: ${response.status}`);
  }
}

/**
 * Submit a tool execution result back to the server.
 */
export async function submitToolResult(
  runId: string,
  toolId: string,
  result: string,
  approved: boolean,
  config: Config
): Promise<void> {
  const response = await fetch(`${config.serverUrl}/tools/result`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, tool_id: toolId, result, approved }),
  });

  if (!response.ok) {
    throw new Error(`Failed to submit tool result: ${response.status}`);
  }
}

/**
 * Get or create a session.
 */
export async function getSession(config: Config): Promise<{
  session_id: string;
  sources: string[];
  source_errors: Record<string, string>;
  yolo: boolean;
}> {
  const response = await fetch(`${config.serverUrl}/session`);
  if (!response.ok) {
    throw new Error(`Failed to get session: ${response.status}`);
  }
  return response.json();
}

/**
 * Check if server is healthy.
 */
export async function checkHealth(config: Config): Promise<boolean> {
  try {
    const response = await fetch(`${config.serverUrl}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

// --- Data fetching for UI views ---

export interface Fact {
  id: number;
  text: string;
  fact_type: string;
  source_type: string;
  created_at: string;
}

export interface FactDetails {
  fact: {
    id: number;
    text: string;
    fact_type: string;
    source_type: string;
    source_ref: string | null;
    created_at: string;
    access_count: number;
  };
  entities: Array<{ name: string; type: string }>;
  linked_facts: Array<{
    id: number;
    text: string;
    link_type: string;
    weight: number;
  }>;
}

export interface ServerConfig {
  chat_model: string;
  memory_model: string;
  embedding_model: string;
  vault_path: string;
  browser: string | null;
  gmail_enabled: boolean;
  gmail_accounts: string[];
  has_browser: boolean;
  has_gmail: boolean;
  max_depth: number;
  max_iterations: number;
  memory_enabled: boolean;
}

export interface Stats {
  fact_count: number;
  link_count: number;
  observation_count: number;
  sources: string[];
}

export interface Observation {
  id: number;
  summary: string;
  evidence_count: number;
  access_count: number;
  created_at: string;
  updated_at: string;
}

export interface ObservationDetails {
  observation: Observation;
  supporting_facts: Array<{ id: number; text: string }>;
}

export async function getFacts(config: Config, limit = 50): Promise<{
  facts: Fact[];
  total: number;
}> {
  return api.get<{ facts: Fact[]; total: number }>(`${config.serverUrl}/facts?limit=${limit}`);
}

export async function getFactDetails(config: Config, factId: number): Promise<FactDetails> {
  return api.get<FactDetails>(`${config.serverUrl}/facts/${factId}`);
}

export async function getServerConfig(config: Config): Promise<ServerConfig> {
  return api.get<ServerConfig>(`${config.serverUrl}/config`);
}

export async function updateConfig(
  config: Config,
  patch: { chat_model?: string; max_depth?: number; max_iterations?: number }
): Promise<{ chat_model: string; max_depth: number; max_iterations: number }> {
  const response = await fetch(`${config.serverUrl}/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(`Failed: ${response.status}`);
  return response.json();
}

export async function updateModels(
  config: Config,
  models: { chat_model?: string; memory_model?: string }
): Promise<{ chat_model: string; memory_model: string }> {
  const response = await fetch(`${config.serverUrl}/config/models`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(models),
  });
  if (!response.ok) throw new Error(`Failed: ${response.status}`);
  return response.json();
}

export async function getSupportedModels(config: Config): Promise<{
  models: string[];
  chat_model: string;
  memory_model: string;
}> {
  const response = await fetch(`${config.serverUrl}/models`);
  if (!response.ok) throw new Error(`Failed: ${response.status}`);
  return response.json();
}

export async function compactContext(config: Config): Promise<{ status: string; message: string }> {
  return api.post<{ status: string; message: string }>(`${config.serverUrl}/compact`, {});
}

export interface ContextUsage {
  model: string;
  limit: number;
  total: number;
  system_prompt: number;
  tools: number;
  messages: number;
  message_count: number;
  tool_count: number;
}

export async function getContextUsage(config: Config): Promise<ContextUsage> {
  return api.get<ContextUsage>(`${config.serverUrl}/context`);
}

export async function getStats(config: Config): Promise<Stats> {
  return api.get<Stats>(`${config.serverUrl}/stats`);
}

export async function getObservations(config: Config, limit = 50): Promise<{
  observations: Observation[];
}> {
  return api.get<{ observations: Observation[] }>(`${config.serverUrl}/observations?limit=${limit}`);
}

export async function getObservationDetails(config: Config, observationId: number): Promise<ObservationDetails> {
  return api.get<ObservationDetails>(`${config.serverUrl}/observations/${observationId}`);
}

export async function clearSession(config: Config): Promise<{ status: string; session_id: string }> {
  return api.post<{ status: string; session_id: string }>(`${config.serverUrl}/session/clear`);
}

export async function purgeMemory(config: Config): Promise<{ status: string; deleted: Record<string, number> }> {
  return api.post<{ status: string; deleted: Record<string, number> }>(`${config.serverUrl}/memory/clear`);
}

// --- Index Status API ---

export interface IndexStatus {
  indexing: boolean;
  progress: {
    total: number;
    done: number;
    status: string;
    updated?: number;
    deleted?: number;
  };
  error?: string;
  stats: Record<string, number>;
}

export async function getIndexStatus(config: Config): Promise<IndexStatus> {
  return api.get<IndexStatus>(`${config.serverUrl}/index/status`);
}

export async function startIndexing(config: Config): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/index/start`);
}

// --- Gmail Management API ---

export interface GmailAccount {
  email: string | null;
  token_file: string;
  has_send_scope?: boolean;
  error?: string;
}

export async function getGmailAccounts(config: Config): Promise<{ accounts: GmailAccount[] }> {
  const response = await fetch(`${config.serverUrl}/gmail/accounts`);
  if (!response.ok) throw new Error(`Failed: ${response.status}`);
  return response.json();
}

export async function addGmailAccount(config: Config): Promise<{ email: string; status: string }> {
  const response = await fetch(`${config.serverUrl}/gmail/add`, {
    method: "POST",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `Failed: ${response.status}`);
  }
  return response.json();
}

export async function removeGmailAccount(config: Config, tokenFile: string): Promise<{ email: string | null; status: string }> {
  const response = await fetch(`${config.serverUrl}/gmail/${tokenFile}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `Failed: ${response.status}`);
  }
  return response.json();
}


