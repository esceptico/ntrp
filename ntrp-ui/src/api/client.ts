import type { ServerEvent, Config } from "../types.js";
import { api, getApiKey } from "./fetch.js";

export async function* streamChat(
  message: string,
  sessionId: string | null,
  config: Config,
  skipApprovals: boolean = false
): AsyncGenerator<ServerEvent, void, unknown> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const apiKey = getApiKey();
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const response = await fetch(`${config.serverUrl}/chat/stream`, {
    method: "POST",
    headers,
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
  } catch (error) {
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

export async function getSession(config: Config, sessionId?: string): Promise<{
  session_id: string;
  sources: string[];
  source_errors: Record<string, string>;
  skip_approvals: boolean;
  name?: string | null;
}> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  return api.get(`${config.serverUrl}/session${params}`);
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export async function getHistory(config: Config, sessionId?: string): Promise<{ messages: HistoryMessage[] }> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  return api.get(`${config.serverUrl}/session/history${params}`);
}

export async function checkHealth(config: Config): Promise<{ ok: boolean; version: string | null; hasProviders: boolean }> {
  try {
    const res = await api.get<{ status: string; version?: string; auth?: boolean; has_providers?: boolean }>(`${config.serverUrl}/health`);
    const ok = res.auth !== false;
    return { ok, version: res.version ?? null, hasProviders: res.has_providers ?? true };
  } catch {
    return { ok: false, version: null, hasProviders: true };
  }
}


// --- Providers ---


export interface ProviderInfo {
  id: string;
  name: string;
  connected: boolean;
  key_hint?: string | null;
  from_env?: boolean;
  auth_method?: "oauth" | "api_key" | null;
  models: string[] | Array<{ id: string; base_url: string; context_window: number }>;
  embedding_models?: string[];
  model_count?: number;
}

export async function getProviders(config: Config): Promise<{ providers: ProviderInfo[] }> {
  return api.get<{ providers: ProviderInfo[] }>(`${config.serverUrl}/providers`);
}

export async function connectProvider(
  config: Config,
  providerId: string,
  apiKey: string,
  chatModel?: string,
): Promise<{ status: string; provider: string }> {
  return api.post(`${config.serverUrl}/providers/${providerId}/connect`, {
    api_key: apiKey,
    chat_model: chatModel ?? null,
  });
}

export async function disconnectProvider(
  config: Config,
  providerId: string,
): Promise<{ status: string; provider: string }> {
  return api.delete(`${config.serverUrl}/providers/${providerId}`);
}

export async function connectProviderOAuth(
  config: Config,
  providerId: string,
): Promise<{ status: string; provider: string; auth_method: string }> {
  return api.post(`${config.serverUrl}/providers/${providerId}/oauth`, {});
}

export async function disconnectProviderOAuth(
  config: Config,
  providerId: string,
): Promise<{ status: string; provider: string }> {
  return api.delete(`${config.serverUrl}/providers/${providerId}/oauth`);
}

// --- Services ---


export interface ServiceInfo {
  id: string;
  name: string;
  connected: boolean;
  key_hint?: string | null;
  from_env?: boolean;
}

export async function getServices(config: Config): Promise<{ services: ServiceInfo[] }> {
  return api.get<{ services: ServiceInfo[] }>(`${config.serverUrl}/services`);
}

export async function connectService(
  config: Config,
  serviceId: string,
  apiKey: string,
): Promise<{ status: string; service: string }> {
  return api.post(`${config.serverUrl}/services/${serviceId}/connect`, { api_key: apiKey });
}

export async function disconnectService(
  config: Config,
  serviceId: string,
): Promise<{ status: string; service: string }> {
  return api.delete(`${config.serverUrl}/services/${serviceId}`);
}


export async function addCustomModel(
  config: Config,
  data: { model_id: string; base_url: string; context_window: number; max_output_tokens?: number; api_key?: string },
): Promise<{ status: string; model_id: string }> {
  return api.post(`${config.serverUrl}/models/custom`, data);
}

export async function removeCustomModel(
  config: Config,
  modelId: string,
): Promise<{ status: string; model_id: string }> {
  return api.delete(`${config.serverUrl}/models/custom/${modelId}`);
}


export interface Fact {
  id: number;
  text: string;
  source_type: string;
  created_at: string;
}

export interface FactDetails {
  fact: {
    id: number;
    text: string;
    source_type: string;
    source_ref: string | null;
    created_at: string;
    access_count: number;
  };
  entities: Array<{ name: string; entity_id: number }>;
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
  explore_model: string;
  memory_model: string;
  embedding_model: string;
  anthropic_auth?: "oauth" | "api_key" | null;
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
  patch: Partial<Pick<ServerConfig, "chat_model" | "explore_model" | "memory_model" | "max_depth">> & {
    sources?: Record<string, boolean>;
  }
): Promise<Record<string, unknown>> {
  return api.patch(`${config.serverUrl}/config`, patch);
}

export interface ModelGroup {
  provider: string;
  models: string[];
}

export async function getSupportedModels(config: Config): Promise<{
  models: string[];
  groups: ModelGroup[];
  chat_model: string;
  explore_model: string;
  memory_model: string;
}> {
  return api.get(`${config.serverUrl}/models`);
}

export async function getEmbeddingModels(config: Config): Promise<{
  models: string[];
  groups: ModelGroup[];
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

export async function compactContext(config: Config, sessionId?: string): Promise<{ status: string; message: string }> {
  const body = sessionId ? { session_id: sessionId } : {};
  return api.post<{ status: string; message: string }>(`${config.serverUrl}/compact`, body);
}

export async function getContextUsage(config: Config, sessionId?: string): Promise<{
  model: string;
  limit: number;
  total: number | null;
  message_count: number;
  tool_count: number;
}> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  return api.get(`${config.serverUrl}/context${params}`);
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

export async function clearSession(config: Config, sessionId?: string): Promise<{ status: string; session_id: string }> {
  const body = sessionId ? { session_id: sessionId } : {};
  return api.post<{ status: string; session_id: string }>(`${config.serverUrl}/session/clear`, body);
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

export async function purgeMemory(config: Config): Promise<{ status: string; deleted: Record<string, number> }> {
  return api.post<{ status: string; deleted: Record<string, number> }>(`${config.serverUrl}/memory/clear`);
}

interface IndexStatus {
  indexing: boolean;
  progress: {
    total: number;
    done: number;
    status: string;
    updated?: number;
    deleted?: number;
  };
  reembedding?: boolean;
  reembed_progress?: { total: number; done: number } | null;
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

export interface TimeTrigger {
  type: "time";
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
}

export interface EventTrigger {
  type: "event";
  event_type: string;
  lead_minutes?: number;
}

export type Trigger = TimeTrigger | EventTrigger;

export interface Automation {
  task_id: string;
  name: string;
  description: string;
  model: string | null;
  trigger: Trigger;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
  notifiers: string[];
  last_result: string | null;
  writable: boolean;
  running_since: string | null;
}

export interface CreateAutomationData {
  name: string;
  description: string;
  model?: string;
  trigger_type: "time" | "event";
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
  event_type?: string;
  lead_minutes?: number;
  notifiers: string[];
  writable: boolean;
}

export interface UpdateAutomationData {
  name?: string;
  description?: string;
  model?: string;
  trigger_type?: "time" | "event";
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
  event_type?: string;
  lead_minutes?: number;
  notifiers?: string[];
  writable?: boolean;
}

export async function createAutomation(config: Config, data: CreateAutomationData): Promise<Automation> {
  return api.post<Automation>(`${config.serverUrl}/automations`, data);
}

export async function getAutomations(config: Config): Promise<{ automations: Automation[] }> {
  return api.get<{ automations: Automation[] }>(`${config.serverUrl}/automations`);
}

export async function toggleAutomation(config: Config, taskId: string): Promise<{ enabled: boolean }> {
  return api.post<{ enabled: boolean }>(`${config.serverUrl}/automations/${taskId}/toggle`);
}

export async function updateAutomation(config: Config, taskId: string, data: UpdateAutomationData): Promise<Automation> {
  return api.patch<Automation>(`${config.serverUrl}/automations/${taskId}`, data);
}

export async function deleteAutomation(config: Config, taskId: string): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/automations/${taskId}`);
}

export async function getAutomationDetail(config: Config, taskId: string): Promise<Automation> {
  return api.get<Automation>(`${config.serverUrl}/automations/${taskId}`);
}

export async function toggleWritable(config: Config, taskId: string): Promise<{ writable: boolean }> {
  return api.post<{ writable: boolean }>(`${config.serverUrl}/automations/${taskId}/writable`);
}

export async function runAutomation(config: Config, taskId: string): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/automations/${taskId}/run`);
}

export interface NotifierSummary {
  name: string;
  type: string;
}

export async function getNotifiers(config: Config): Promise<{ notifiers: NotifierSummary[] }> {
  return api.get<{ notifiers: NotifierSummary[] }>(`${config.serverUrl}/notifiers`);
}

export async function setAutomationNotifiers(
  config: Config,
  taskId: string,
  notifiers: string[]
): Promise<{ notifiers: string[] }> {
  return api.put<{ notifiers: string[] }>(`${config.serverUrl}/automations/${taskId}/notifiers`, { notifiers });
}

export interface NotifierConfigData {
  name: string;
  type: string;
  config: Record<string, string>;
  created_at: string;
}

export interface NotifierTypeInfo {
  fields: string[];
  accounts?: string[];
}

export async function getNotifierConfigs(config: Config): Promise<{ configs: NotifierConfigData[] }> {
  return api.get<{ configs: NotifierConfigData[] }>(`${config.serverUrl}/notifiers/configs`);
}

export async function getNotifierTypes(config: Config): Promise<{ types: Record<string, NotifierTypeInfo> }> {
  return api.get<{ types: Record<string, NotifierTypeInfo> }>(`${config.serverUrl}/notifiers/types`);
}

export async function createNotifierConfig(
  config: Config,
  data: { name: string; type: string; config: Record<string, string> }
): Promise<NotifierConfigData> {
  return api.post<NotifierConfigData>(`${config.serverUrl}/notifiers/configs`, data);
}

export async function updateNotifierConfig(
  config: Config,
  name: string,
  cfg: Record<string, string>,
  newName?: string,
): Promise<NotifierConfigData> {
  const body: { config: Record<string, string>; name?: string } = { config: cfg };
  if (newName && newName !== name) body.name = newName;
  return api.put<NotifierConfigData>(`${config.serverUrl}/notifiers/configs/${name}`, body);
}

export async function deleteNotifierConfig(config: Config, name: string): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/notifiers/configs/${name}`);
}

export async function testNotifier(config: Config, name: string): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/notifiers/configs/${name}/test`);
}

export interface Dream {
  id: number;
  bridge: string;
  insight: string;
  created_at: string;
}

export interface DreamDetails {
  dream: Dream;
  source_facts: Array<{ id: number; text: string }>;
}

export async function getDreams(config: Config, limit = 50): Promise<{
  dreams: Dream[];
}> {
  return api.get<{ dreams: Dream[] }>(`${config.serverUrl}/dreams?limit=${limit}`);
}

export async function getDreamDetails(config: Config, dreamId: number): Promise<DreamDetails> {
  return api.get<DreamDetails>(`${config.serverUrl}/dreams/${dreamId}`);
}

export async function deleteDream(config: Config, dreamId: number): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/dreams/${dreamId}`);
}

export async function updateFact(
  config: Config,
  factId: number,
  text: string
): Promise<{
  fact: {
    id: number;
    text: string;
    source_type: string;
    source_ref: string | null;
    created_at: string;
    access_count: number;
  };
  entity_refs: Array<{ name: string; entity_id: number }>;
}> {
  return api.patch(`${config.serverUrl}/facts/${factId}`, { text });
}

export async function deleteFact(
  config: Config,
  factId: number
): Promise<{
  status: string;
  fact_id: number;
  cascaded: { entity_refs: number };
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

export interface Skill {
  name: string;
  description: string;
  location: string;
}

export async function getSkills(config: Config): Promise<{ skills: Skill[] }> {
  return api.get(`${config.serverUrl}/skills`);
}

export async function installSkill(config: Config, source: string): Promise<{ name: string; description: string; status: string }> {
  return api.post(`${config.serverUrl}/skills/install`, { source }, { timeout: 60000 });
}

export async function removeSkill(config: Config, name: string): Promise<{ status: string }> {
  return api.delete(`${config.serverUrl}/skills/${name}`);
}

export async function getDirectives(config: Config): Promise<{ content: string }> {
  return api.get<{ content: string }>(`${config.serverUrl}/directives`);
}

export async function updateDirectives(config: Config, content: string): Promise<{ content: string }> {
  return api.put<{ content: string }>(`${config.serverUrl}/directives`, { content });
}
