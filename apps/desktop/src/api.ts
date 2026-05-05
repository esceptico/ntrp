export interface AppConfig {
  serverUrl: string;
  apiKey: string;
}

export interface SessionListItem {
  session_id: string;
  started_at: string;
  last_activity: string;
  name: string | null;
  message_count: number;
}

export interface HistoryToolCall {
  id: string;
  name: string;
  arguments: string;
  /** Semantic kind ("tool" | "agent") for the row renderer. Server fills
   *  this from the tool registry at history-read time. */
  kind?: string;
}

export interface HistoryImage {
  media_type: string;
  data: string;
}

export interface HistoryMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning_content?: string;
  tool_calls?: HistoryToolCall[];
  tool_call_id?: string;
  images?: HistoryImage[];
  /** Stable client-side id (the same one we streamed for assistant turns).
   *  Available for messages saved after id-based persistence landed; older
   *  sessions may not have it. */
  id?: string;
  /** ISO-8601 UTC timestamp stamped at first save. */
  created_at?: string;
}

export interface HealthCheck {
  ok: boolean;
  version: string | null;
  hasProviders: boolean;
}

export interface ApiBridgeResponse {
  ok: boolean;
  status: number;
  statusText: string;
  contentType: string;
  data: unknown;
  text: string;
}

/** AG-UI-shaped event protocol. Every event carries a `timestamp` (Unix ms). */
type WithTs = { timestamp?: number };

export type ServerEvent = WithTs & (
  // ─── Run lifecycle ──────────────────────────────────────────────────
  | { type: "RUN_STARTED"; run_id: string; session_id: string; session_name?: string | null; skip_approvals?: boolean }
  | { type: "RUN_FINISHED"; run_id: string; usage?: { prompt: number; completion: number; cache_read: number; cost: number } }
  | { type: "RUN_ERROR"; message: string }

  // ─── Text messages (Start / Content / End) ─────────────────────────
  | { type: "TEXT_MESSAGE_START"; message_id: string; role?: string; depth?: number }
  | { type: "TEXT_MESSAGE_CONTENT"; message_id: string; delta: string; depth?: number }
  | { type: "TEXT_MESSAGE_END"; message_id: string; content?: string; depth?: number }

  // ─── Tool calls (Start / Args / End / Result) ──────────────────────
  | { type: "TOOL_CALL_START"; tool_call_id: string; tool_call_name: string; description?: string; display_name?: string; parent_message_id?: string | null; depth?: number; parent_id?: string | null; kind?: string }
  | { type: "TOOL_CALL_ARGS"; tool_call_id: string; delta: string; depth?: number; parent_id?: string | null }
  | { type: "TOOL_CALL_END"; tool_call_id: string; depth?: number; parent_id?: string | null }
  | { type: "TOOL_CALL_RESULT"; tool_call_id: string; name: string; content?: string; preview?: string; display_name?: string; depth?: number; parent_id?: string | null; kind?: string }

  // ─── Reasoning ─────────────────────────────────────────────────────
  | { type: "REASONING_START"; message_id: string; depth?: number }
  | { type: "REASONING_MESSAGE_START"; message_id: string; role?: string; depth?: number }
  | { type: "REASONING_MESSAGE_CONTENT"; message_id: string; delta: string; depth?: number }
  | { type: "REASONING_MESSAGE_END"; message_id: string; depth?: number }
  | { type: "REASONING_END"; message_id: string; depth?: number }

  // ─── ntrp-specific (non-AG-UI canonical) ───────────────────────────
  | { type: "approval_needed"; tool_id: string; name: string; path?: string | null; diff?: string | null; content_preview?: string | null }
  | { type: "background_task"; command: string; status: string; detail?: string }
  | { type: "compaction_started"; run_id: string }
  | { type: "compaction_finished"; run_id: string; messages_before: number; messages_after: number }
);

export const STORAGE_KEY = "ntrp.desktop.config";

export const DEFAULT_CONFIG: AppConfig = {
  serverUrl: "http://localhost:6877",
  apiKey: "",
};

export function normalizeConfig(config: Partial<AppConfig> | null | undefined): AppConfig {
  return {
    serverUrl: config?.serverUrl?.trim().replace(/\/$/, "") || DEFAULT_CONFIG.serverUrl,
    apiKey: config?.apiKey?.trim() ?? "",
  };
}

export function hostFromUrl(value: string): string {
  try {
    return new URL(value).host || value;
  } catch {
    return value;
  }
}

function headersForConfig(config: AppConfig, json = false): HeadersInit {
  const out: Record<string, string> = {};
  if (json) out["Content-Type"] = "application/json";
  if (config.apiKey) out.Authorization = `Bearer ${config.apiKey}`;
  return out;
}

function errorMessageFromResponse(response: { status: number; data?: unknown; text?: string }): string {
  let message = `HTTP ${response.status}`;
  if (response.data && typeof response.data === "object") {
    const body = response.data as { detail?: unknown; message?: unknown };
    if (typeof body.detail === "string") message = body.detail;
    if (typeof body.message === "string") message = body.message;
  } else if (response.text) {
    message = response.text;
  }
  return message;
}

export async function apiWithConfig<T>(config: AppConfig, path: string, init: RequestInit = {}): Promise<T> {
  const { timeout, ...requestInit } = init as RequestInit & { timeout?: number };
  const body = typeof requestInit.body === "string" ? requestInit.body : undefined;
  const desktopApi = window.ntrpDesktop?.api;

  if (desktopApi) {
    const response: ApiBridgeResponse = await desktopApi.request(config, {
      path,
      method: requestInit.method ?? "GET",
      body,
      timeout,
    });
    if (!response.ok) throw new Error(errorMessageFromResponse(response));
    return response.contentType.includes("application/json") ? (response.data as T) : (undefined as T);
  }

  const controller = new AbortController();
  const timeoutId = timeout && timeout > 0 ? window.setTimeout(() => controller.abort(), timeout) : null;
  const signal = requestInit.signal ? AbortSignal.any([controller.signal, requestInit.signal]) : controller.signal;

  try {
    const response = await fetch(`${config.serverUrl}${path}`, {
      ...requestInit,
      headers: {
        ...headersForConfig(config, Boolean(requestInit.body)),
        ...(requestInit.headers ?? {}),
      },
      signal,
    });

    if (!response.ok) {
      let data: unknown = null;
      let text = "";
      try {
        data = await response.json();
      } catch {
        text = await response.text();
      }
      throw new Error(errorMessageFromResponse({ status: response.status, data, text }));
    }

    if (!response.headers.get("content-type")?.includes("application/json")) {
      return undefined as T;
    }
    return (await response.json()) as T;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

export async function checkHealth(config: AppConfig): Promise<HealthCheck> {
  try {
    const health = await apiWithConfig<{
      auth?: boolean;
      version?: string;
      has_providers?: boolean;
    }>(config, "/health", { timeout: 5000 } as RequestInit & { timeout: number });
    return {
      ok: health.auth !== false,
      version: health.version ?? null,
      hasProviders: health.has_providers ?? true,
    };
  } catch {
    return { ok: false, version: null, hasProviders: true };
  }
}

export async function validateConnection(config: AppConfig): Promise<HealthCheck> {
  const normalized = normalizeConfig(config);
  if (!normalized.apiKey) throw new Error("API key is required");
  const health = await checkHealth(normalized);
  if (!health.ok) {
    throw new Error(health.version ? "Invalid API key" : "Could not reach ntrp server");
  }
  return health;
}

function loadLegacyConfig(): AppConfig {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return { ...DEFAULT_CONFIG };
  try {
    return normalizeConfig(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

export async function loadInitialConfig(): Promise<AppConfig> {
  const desktopConfig = window.ntrpDesktop?.config;
  if (!desktopConfig) return loadLegacyConfig();

  const config = await desktopConfig.get();
  if (config.apiKey || localStorage.getItem(STORAGE_KEY) === null) return normalizeConfig(config);

  const legacy = loadLegacyConfig();
  if (legacy.apiKey || legacy.serverUrl !== DEFAULT_CONFIG.serverUrl) {
    localStorage.removeItem(STORAGE_KEY);
    return desktopConfig.set(legacy);
  }
  return normalizeConfig(config);
}

export async function saveConfig(config: AppConfig): Promise<AppConfig> {
  const normalized = normalizeConfig(config);
  const desktopConfig = window.ntrpDesktop?.config;
  if (desktopConfig) {
    const saved = await desktopConfig.set(normalized);
    localStorage.removeItem(STORAGE_KEY);
    return saved;
  }
  return normalized;
}

export async function submitToolResult(
  config: AppConfig,
  payload: { run_id: string; tool_id: string; result: string; approved: boolean },
): Promise<void> {
  await apiWithConfig(config, "/tools/result", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function cancelRun(config: AppConfig, runId: string): Promise<void> {
  await apiWithConfig(config, "/cancel", {
    method: "POST",
    body: JSON.stringify({ run_id: runId }),
  });
}

export async function renameSessionApi(
  config: AppConfig,
  sessionId: string,
  name: string,
): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function archiveSessionApi(config: AppConfig, sessionId: string): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export interface ArchivedSession {
  session_id: string;
  started_at: string;
  last_activity: string;
  name: string | null;
  archived_at: string;
  message_count: number;
}

export async function listArchivedSessionsApi(config: AppConfig): Promise<ArchivedSession[]> {
  const r = await apiWithConfig<{ sessions: ArchivedSession[] }>(config, "/sessions/archived");
  return r.sessions;
}

export async function restoreSessionApi(config: AppConfig, sessionId: string): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/restore`, {
    method: "POST",
  });
}

export async function permanentlyDeleteSessionApi(config: AppConfig, sessionId: string): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/permanent`, {
    method: "DELETE",
  });
}

// ─── Memory ──────────────────────────────────────────────────────────

export type FactKind =
  | "identity"
  | "preference"
  | "relationship"
  | "decision"
  | "project"
  | "event"
  | "artifact"
  | "procedure"
  | "constraint"
  | "note";

export type FactLifetime = "durable" | "temporary";
export type FactStatus = "active" | "archived" | "superseded" | "expired" | "temporary" | "pinned" | "all";

export interface Fact {
  id: number;
  text: string;
  source_type: string;
  source_ref: string | null;
  created_at: string;
  happened_at: string | null;
  last_accessed_at: string;
  access_count: number;
  consolidated_at: string | null;
  archived_at: string | null;
  kind: FactKind;
  lifetime: FactLifetime;
  salience: number;
  confidence: number;
  expires_at: string | null;
  pinned_at: string | null;
  superseded_by_fact_id: number | null;
}

export interface Observation {
  id: number;
  summary: string;
  evidence_count: number;
  access_count: number;
  created_at: string;
  updated_at: string;
  last_accessed_at: string;
  archived_at: string | null;
  created_by: string | null;
  policy_version: number | null;
}

export interface FactListFilters {
  limit?: number;
  offset?: number;
  kind?: FactKind;
  status?: FactStatus;
}

export async function listFactsApi(
  config: AppConfig,
  filters: FactListFilters = {},
): Promise<{ facts: Fact[]; total: number }> {
  const qs = new URLSearchParams();
  qs.set("limit", String(filters.limit ?? 100));
  if (filters.offset) qs.set("offset", String(filters.offset));
  if (filters.kind) qs.set("kind", filters.kind);
  if (filters.status) qs.set("status", filters.status);
  return apiWithConfig(config, `/facts?${qs.toString()}`);
}

export async function updateFactTextApi(config: AppConfig, id: number, text: string): Promise<{ fact: Fact }> {
  return apiWithConfig(config, `/facts/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ text }),
  });
}

export async function deleteFactApi(config: AppConfig, id: number): Promise<void> {
  await apiWithConfig(config, `/facts/${id}`, { method: "DELETE" });
}

export interface ObservationListFilters {
  limit?: number;
  offset?: number;
  status?: "active" | "archived" | "all";
}

export async function listObservationsApi(
  config: AppConfig,
  filters: ObservationListFilters = {},
): Promise<{ observations: Observation[]; total: number }> {
  const qs = new URLSearchParams();
  qs.set("limit", String(filters.limit ?? 100));
  if (filters.offset) qs.set("offset", String(filters.offset));
  if (filters.status) qs.set("status", filters.status);
  return apiWithConfig(config, `/observations?${qs.toString()}`);
}

export async function updateObservationSummaryApi(
  config: AppConfig,
  id: number,
  summary: string,
): Promise<{ observation: Observation }> {
  return apiWithConfig(config, `/observations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ summary }),
  });
}

export async function deleteObservationApi(config: AppConfig, id: number): Promise<void> {
  await apiWithConfig(config, `/observations/${id}`, { method: "DELETE" });
}

export interface ObservationDetail {
  observation: Observation;
  supporting_facts: Fact[];
  source_fact_ids: number[];
  missing_source_fact_ids: number[];
}

export async function getObservationApi(config: AppConfig, id: number): Promise<ObservationDetail> {
  return apiWithConfig(config, `/observations/${id}`);
}

// ─── Dreams ───────────────────────────────────────────────────────────

export interface Dream {
  id: number;
  bridge: string;
  insight: string;
  created_at: string;
}

export interface DreamDetail {
  dream: Dream;
  source_facts: { id: number; text: string }[];
}

export async function listDreamsApi(config: AppConfig): Promise<{ dreams: Dream[] }> {
  return apiWithConfig(config, "/dreams?limit=200");
}

export async function getDreamApi(config: AppConfig, id: number): Promise<DreamDetail> {
  return apiWithConfig(config, `/dreams/${id}`);
}

export async function deleteDreamApi(config: AppConfig, id: number): Promise<void> {
  await apiWithConfig(config, `/dreams/${id}`, { method: "DELETE" });
}

// ─── Profile ──────────────────────────────────────────────────────────

export interface ProfileEntry {
  id: number;
  kind: FactKind;
  summary: string;
  source_fact_ids: number[];
  source_observation_ids: number[];
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  created_by: string | null;
  policy_version: number | null;
  confidence: number;
}

export interface ProfileEntryDetail {
  entry: ProfileEntry;
  source_facts: Fact[];
  source_observations: Observation[];
}

export async function listProfileApi(config: AppConfig): Promise<{ entries: ProfileEntry[] }> {
  return apiWithConfig(config, "/memory/profile?limit=50");
}

export async function getProfileEntryApi(config: AppConfig, id: number): Promise<ProfileEntryDetail> {
  return apiWithConfig(config, `/memory/profile/${id}`);
}

export interface UpdateProfileEntryPayload {
  kind?: FactKind;
  summary?: string;
  confidence?: number;
}

export async function updateProfileEntryApi(
  config: AppConfig,
  id: number,
  payload: UpdateProfileEntryPayload,
): Promise<{ entry: ProfileEntry }> {
  return apiWithConfig(config, `/memory/profile/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteProfileEntryApi(config: AppConfig, id: number): Promise<void> {
  await apiWithConfig(config, `/memory/profile/${id}`, { method: "DELETE" });
}

// ─── Supersession (merge candidates) ──────────────────────────────────

export interface SupersessionCandidate {
  kind: string;
  entity: string;
  older_fact: Fact;
  newer_fact: Fact;
  reason: string;
}

export async function listSupersessionCandidatesApi(
  config: AppConfig,
): Promise<{ candidates: SupersessionCandidate[]; total: number }> {
  return apiWithConfig(config, "/memory/supersession/candidates?limit=200");
}

export async function applySupersessionApi(
  config: AppConfig,
  olderFactId: number,
  newerFactId: number,
): Promise<void> {
  await apiWithConfig(config, `/facts/${olderFactId}/metadata`, {
    method: "PATCH",
    body: JSON.stringify({ superseded_by_fact_id: newerFactId }),
  });
}

// ─── MCP servers ──────────────────────────────────────────────────────

export type MCPTransport = "stdio" | "http";

export interface MCPTool {
  name: string;
  description: string;
  enabled: boolean;
}

export interface MCPServer {
  name: string;
  transport: MCPTransport | "unknown";
  connected: boolean;
  tool_count: number;
  error: string | null;
  command: string | null;
  args: string[] | null;
  url: string | null;
  tools: MCPTool[];
  enabled: boolean;
  auth: string | null;
  has_client_credentials: boolean;
}

/** Raw payload shape persisted on the server. The desktop reads/writes this
 *  dict directly via add/update; the server validates it through
 *  parse_server_config. */
export interface MCPServerConfigPayload {
  transport: MCPTransport;
  enabled?: boolean;
  // stdio
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  // http
  url?: string;
  headers?: Record<string, string>;
  auth?: string;
  client_id?: string;
  client_secret?: string;
  redirect_port?: number;
  scope?: string;
  client_name?: string;
  // common
  tools?: string[] | null;
}

export async function listMCPServersApi(config: AppConfig): Promise<{ servers: MCPServer[] }> {
  return apiWithConfig(config, "/mcp/servers");
}

export async function addMCPServerApi(
  config: AppConfig,
  name: string,
  serverConfig: MCPServerConfigPayload,
): Promise<void> {
  await apiWithConfig(config, "/mcp/servers", {
    method: "POST",
    body: JSON.stringify({ name, config: serverConfig }),
  });
}

export async function updateMCPServerApi(
  config: AppConfig,
  name: string,
  serverConfig: MCPServerConfigPayload,
): Promise<void> {
  await apiWithConfig(config, `/mcp/servers/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify({ config: serverConfig }),
  });
}

export async function updateMCPToolsApi(
  config: AppConfig,
  name: string,
  tools: string[] | null,
): Promise<void> {
  await apiWithConfig(config, `/mcp/servers/${encodeURIComponent(name)}/tools`, {
    method: "PUT",
    body: JSON.stringify({ tools }),
  });
}

export async function toggleMCPServerApi(
  config: AppConfig,
  name: string,
  enabled: boolean,
): Promise<void> {
  await apiWithConfig(config, `/mcp/servers/${encodeURIComponent(name)}/enabled`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
}

export async function startMCPOAuthApi(config: AppConfig, name: string): Promise<void> {
  await apiWithConfig(config, `/mcp/servers/${encodeURIComponent(name)}/oauth`, {
    method: "POST",
  });
}

export async function removeMCPServerApi(config: AppConfig, name: string): Promise<void> {
  await apiWithConfig(config, `/mcp/servers/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export async function branchSessionApi(
  config: AppConfig,
  sessionId: string,
  payload: { name?: string; up_to_message_id?: string; from_end_index?: number },
): Promise<{ session_id: string; name: string | null; started_at: string; last_activity: string }> {
  return apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/branch`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface SkillDescriptor {
  name: string;
  description: string;
  /** Where the skill came from: "builtin", "user", "global", "project". */
  location?: string;
  /** Absolute filesystem path to the SKILL.md file (when available). */
  path?: string;
}

export async function listSkills(config: AppConfig): Promise<SkillDescriptor[]> {
  const { skills } = await apiWithConfig<{ skills: SkillDescriptor[] }>(config, "/skills");
  return skills ?? [];
}

export interface SkillContent {
  name: string;
  description: string;
  path: string;
  content: string;
}

export async function fetchSkillContent(config: AppConfig, name: string): Promise<SkillContent> {
  return apiWithConfig<SkillContent>(config, `/skills/${encodeURIComponent(name)}/content`);
}

export interface ServerConfig {
  chat_model: string;
  research_model: string;
  memory_model: string;
  embedding_model: string;
  web_search: "auto" | "exa" | "ddgs" | "none";
  web_search_provider: string;
  google_enabled: boolean;
  max_depth: number;
  reasoning_effort: string | null;
  reasoning_efforts: string[];
  compression_threshold: number;
  max_messages: number;
  compression_keep_ratio: number;
  summary_max_tokens: number;
  consolidation_interval: number;
  memory_enabled: boolean;
  integrations: Record<string, Record<string, unknown>>;
}

export interface ModelGroup {
  provider: string;
  models: string[];
}

export interface ModelsResponse {
  models: string[];
  groups: ModelGroup[];
  chat_model: string;
  research_model: string;
  memory_model: string;
}

export async function getServerConfig(config: AppConfig): Promise<ServerConfig> {
  return apiWithConfig<ServerConfig>(config, "/config");
}

export async function getServerModels(config: AppConfig): Promise<ModelsResponse> {
  return apiWithConfig<ModelsResponse>(config, "/models");
}

export type ServerConfigPatch = Partial<{
  chat_model: string;
  research_model: string;
  memory_model: string;
  max_depth: number;
  reasoning_effort: string | null;
  compression_threshold: number;
  max_messages: number;
  compression_keep_ratio: number;
  summary_max_tokens: number;
  consolidation_interval: number;
  web_search: "auto" | "exa" | "ddgs" | "none";
  integrations: { google?: boolean | null; memory?: boolean | null; dreams?: boolean | null };
}>;

export async function patchServerConfig(
  config: AppConfig,
  patch: ServerConfigPatch,
): Promise<ServerConfig> {
  return apiWithConfig<ServerConfig>(config, "/config", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

// ─── Automations ───────────────────────────────────────────────────

export type AutomationTriggerType = "time" | "event" | "idle" | "count";

export interface AutomationTrigger {
  type: AutomationTriggerType;
  // Time
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
  // Event
  event_type?: string;
  lead_minutes?: number;
  // Idle
  idle_minutes?: number;
  // Count
  threshold?: number;
  scope?: string;
}

export interface Automation {
  task_id: string;
  name: string;
  description: string;
  model: string | null;
  triggers: AutomationTrigger[];
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
  /** Textual output from the most recent run (markdown). Null until the
   *  automation has actually run once. */
  last_result: string | null;
  writable: boolean;
  running_since: string | null;
  handler: string | null;
  builtin: boolean;
  cooldown_minutes: number | null;
}

export interface CreateAutomationPayload {
  name: string;
  description: string;
  model?: string | null;
  trigger_type?: AutomationTriggerType;
  at?: string;
  days?: string;
  every?: string;
  event_type?: string;
  lead_minutes?: number | string;
  writable?: boolean;
  start?: string;
  end?: string;
  triggers?: AutomationTrigger[];
  cooldown_minutes?: number | null;
}

export type UpdateAutomationPayload = Partial<
  CreateAutomationPayload & { enabled?: boolean }
>;

export async function listAutomationsApi(config: AppConfig): Promise<Automation[]> {
  const r = await apiWithConfig<{ automations: Automation[] }>(config, "/automations");
  return r.automations;
}

export async function createAutomationApi(
  config: AppConfig,
  payload: CreateAutomationPayload,
): Promise<Automation> {
  return apiWithConfig<Automation>(config, "/automations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAutomationApi(
  config: AppConfig,
  taskId: string,
  patch: UpdateAutomationPayload,
): Promise<Automation> {
  return apiWithConfig<Automation>(config, `/automations/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function toggleAutomationApi(
  config: AppConfig,
  taskId: string,
): Promise<Automation> {
  return apiWithConfig<Automation>(config, `/automations/${encodeURIComponent(taskId)}/toggle`, {
    method: "POST",
  });
}

export async function runAutomationApi(config: AppConfig, taskId: string): Promise<void> {
  await apiWithConfig(config, `/automations/${encodeURIComponent(taskId)}/run`, { method: "POST" });
}

export async function deleteAutomationApi(config: AppConfig, taskId: string): Promise<void> {
  await apiWithConfig(config, `/automations/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}
