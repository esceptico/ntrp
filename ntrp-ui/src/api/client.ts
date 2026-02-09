import type { ServerEvent, Config } from "../types.js";
import { api } from "./fetch.js";

export async function* streamChat(
  message: string,
  sessionId: string | null,
  config: Config,
  skipApprovals: boolean = false
): AsyncGenerator<ServerEvent, void, unknown> {
  const response = await fetch(`${config.serverUrl}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, skip_approvals: skipApprovals }),
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
  } catch (error) {
    // Handle connection termination gracefully
    if (error instanceof TypeError && (error.message === "terminated" || error.message.includes("terminated"))) {
      // Connection was terminated - yield an error event for the UI
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

export async function submitChoiceResult(
  runId: string,
  toolId: string,
  selected: string[],
  config: Config
): Promise<void> {
  await api.post(`${config.serverUrl}/tools/choice`, { run_id: runId, tool_id: toolId, selected });
}

export async function getSession(config: Config): Promise<{
  session_id: string;
  sources: string[];
  source_errors: Record<string, string>;
  skip_approvals: boolean;
}> {
  return api.get(`${config.serverUrl}/session`);
}

export async function checkHealth(config: Config): Promise<boolean> {
  try {
    await api.get(`${config.serverUrl}/health`);
    return true;
  } catch {
    return false;
  }
}

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

export interface SourceInfo {
  enabled?: boolean;
  connected: boolean;
  accounts?: string[];
  path?: string;
  type?: string;
}

export interface ServerConfig {
  chat_model: string;
  memory_model: string;
  embedding_model: string;
  vault_path: string;
  browser: string | null;
  gmail_enabled: boolean;
  has_browser: boolean;
  has_notes: boolean;
  max_depth: number;
  memory_enabled: boolean;
  sources?: Record<string, SourceInfo>;
}

export interface Stats {
  fact_count: number;
  link_count: number;
  observation_count: number;
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
  patch: Partial<Pick<ServerConfig, "chat_model" | "memory_model" | "max_depth">> & {
    sources?: Record<string, boolean>;
  }
): Promise<Record<string, unknown>> {
  return api.patch(`${config.serverUrl}/config`, patch);
}

export async function getSupportedModels(config: Config): Promise<{
  models: string[];
  chat_model: string;
  memory_model: string;
}> {
  return api.get(`${config.serverUrl}/models`);
}

export async function getEmbeddingModels(config: Config): Promise<{
  models: string[];
  current: string;
}> {
  return api.get(`${config.serverUrl}/models/embedding`);
}

export async function updateEmbeddingModel(
  config: Config,
  embeddingModel: string
): Promise<{ status: string; embedding_model?: string; embedding_dim?: number; message?: string }> {
  return api.post(`${config.serverUrl}/config/embedding`, { embedding_model: embeddingModel });
}

export async function compactContext(config: Config): Promise<{ status: string; message: string }> {
  return api.post<{ status: string; message: string }>(`${config.serverUrl}/compact`, {});
}

export async function getContextUsage(config: Config): Promise<{
  model: string;
  limit: number;
  total: number | null;
  message_count: number;
  tool_count: number;
}> {
  return api.get(`${config.serverUrl}/context`);
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

export interface GoogleAccount {
  email: string | null;
  token_file: string;
  has_send_scope?: boolean;
  error?: string;
}

export async function getGoogleAccounts(config: Config): Promise<{ accounts: GoogleAccount[] }> {
  return api.get(`${config.serverUrl}/gmail/accounts`);
}

export async function addGoogleAccount(config: Config): Promise<{ email: string; status: string }> {
  return api.post(`${config.serverUrl}/gmail/add`);
}

export async function removeGoogleAccount(config: Config, tokenFile: string): Promise<{ email: string | null; status: string }> {
  return api.delete(`${config.serverUrl}/gmail/${tokenFile}`);
}

export async function updateVaultPath(
  config: Config,
  vaultPath: string
): Promise<{ vault_path: string }> {
  return api.patch(`${config.serverUrl}/config`, { vault_path: vaultPath });
}

export async function updateBrowser(
  config: Config,
  browser: string | null,
  browserDays?: number
): Promise<{ browser: string | null; browser_days?: number }> {
  const body: { browser: string | null; browser_days?: number } = { browser };
  if (browserDays !== undefined) body.browser_days = browserDays;
  return api.patch(`${config.serverUrl}/config`, body);
}

export interface Schedule {
  task_id: string;
  description: string;
  time_of_day: string;
  recurrence: string;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
  notify_email: string | null;
  last_result: string | null;
  writable: boolean;
  running_since: string | null;
}

export async function getSchedules(config: Config): Promise<{ schedules: Schedule[] }> {
  return api.get<{ schedules: Schedule[] }>(`${config.serverUrl}/schedules`);
}

export async function toggleSchedule(config: Config, taskId: string): Promise<{ enabled: boolean }> {
  return api.post<{ enabled: boolean }>(`${config.serverUrl}/schedules/${taskId}/toggle`);
}

export async function updateSchedule(config: Config, taskId: string, description: string): Promise<{ description: string }> {
  return api.patch<{ description: string }>(`${config.serverUrl}/schedules/${taskId}`, { description });
}

export async function deleteSchedule(config: Config, taskId: string): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/schedules/${taskId}`);
}

export async function getScheduleDetail(config: Config, taskId: string): Promise<Schedule> {
  return api.get<Schedule>(`${config.serverUrl}/schedules/${taskId}`);
}

export async function toggleWritable(config: Config, taskId: string): Promise<{ writable: boolean }> {
  return api.post<{ writable: boolean }>(`${config.serverUrl}/schedules/${taskId}/writable`);
}

export async function runSchedule(config: Config, taskId: string): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/schedules/${taskId}/run`);
}

export async function updateFact(
  config: Config,
  factId: number,
  text: string
): Promise<{
  fact: {
    id: number;
    text: string;
    fact_type: string;
    source_type: string;
    source_ref: string | null;
    created_at: string;
    access_count: number;
  };
  entity_refs: Array<{ name: string; type: string }>;
  links_created: number;
}> {
  return api.patch(`${config.serverUrl}/facts/${factId}`, { text });
}

export async function deleteFact(
  config: Config,
  factId: number
): Promise<{
  fact_id: number;
  deleted_entities: number;
  deleted_links: number;
  deleted_fact_observations: number;
}> {
  return api.delete(`${config.serverUrl}/facts/${factId}`);
}

export async function updateObservation(
  config: Config,
  observationId: number,
  summary: string
): Promise<{
  id: number;
  summary: string;
  evidence_count: number;
  access_count: number;
  created_at: string;
  updated_at: string;
}> {
  return api.patch(`${config.serverUrl}/observations/${observationId}`, { summary });
}

export async function deleteObservation(
  config: Config,
  observationId: number
): Promise<{ status: string }> {
  return api.delete(`${config.serverUrl}/observations/${observationId}`);
}

// --- Dashboard ---

export interface DashboardSystem {
  uptime_seconds: number;
  model: string;
  memory_model: string;
  sources: string[];
  source_errors: Record<string, string>;
}

export interface TokenDataPoint {
  prompt: number;
  completion: number;
  ts: number;
}

export interface DashboardTokens {
  total_prompt: number;
  total_completion: number;
  history: TokenDataPoint[];
}

export interface RecentToolCall {
  name: string;
  duration_ms: number;
  depth: number;
  ts: number;
  error: boolean;
}

export interface ToolStats {
  count: number;
  avg_ms: number;
  error_count: number;
}

export interface DashboardAgent {
  active_runs: number;
  total_runs: number;
  recent_tools: RecentToolCall[];
  tool_stats: Record<string, ToolStats>;
}

export interface DashboardMemory {
  enabled: boolean;
  fact_count: number;
  link_count: number;
  observation_count: number;
  unconsolidated: number;
  consolidation_running: boolean;
  last_consolidation_at: number | null;
  recent_facts: Array<{ id: number; text: string; ts: number }>;
}

export interface DashboardIndexer {
  status: string;
  progress_done: number;
  progress_total: number;
  error: string | null;
}

export interface DashboardScheduler {
  running: boolean;
  active_task: string | null;
  total_scheduled: number;
  enabled_count: number;
  next_run_at: number | null;
}

export interface DashboardBackground {
  indexer: DashboardIndexer;
  scheduler: DashboardScheduler;
  consolidation: { running: boolean; interval_seconds: number };
}

export interface DashboardOverview {
  system: DashboardSystem;
  tokens: DashboardTokens;
  agent: DashboardAgent;
  memory: DashboardMemory;
  background: DashboardBackground;
}

export async function getDashboardOverview(config: Config): Promise<DashboardOverview> {
  return api.get<DashboardOverview>(`${config.serverUrl}/dashboard/overview`);
}
