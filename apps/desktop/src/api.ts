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
  /** Stable durable transcript id. */
  message_id?: string;
  /** Durable transcript order within the session. */
  seq?: number;
  /** ISO-8601 UTC timestamp stamped at first save. */
  created_at?: string;
}

export interface HistoryPage {
  has_more_before: boolean;
  has_more_after: boolean;
  before?: string | null;
  after?: string | null;
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
type CommonServerEventFields = { timestamp?: number; seq?: number; session_id?: string };

export type ServerEvent = CommonServerEventFields & (
  // ─── Run lifecycle ──────────────────────────────────────────────────
  | { type: "RUN_STARTED"; run_id: string; session_id: string; session_name?: string | null; skip_approvals?: boolean }
  | { type: "RUN_FINISHED"; run_id: string; usage?: { prompt: number; completion: number; cache_read: number; cost: number } }
  | { type: "run_cancelled"; run_id: string }
  | { type: "RUN_ERROR"; run_id: string; message: string }

  // ─── Text messages (Start / Content / End) ─────────────────────────
  | { type: "TEXT_MESSAGE_START"; message_id: string; role?: string; depth?: number }
  | { type: "TEXT_MESSAGE_CONTENT"; message_id: string; delta: string; depth?: number }
  | { type: "TEXT_MESSAGE_END"; message_id: string; content?: string; depth?: number }

  // ─── Tool calls (Start / Args / End / Result) ──────────────────────
  | { type: "TOOL_CALL_START"; tool_call_id: string; tool_call_name: string; description?: string; display_name?: string; parent_message_id?: string | null; depth?: number; parent_id?: string | null; kind?: string }
  | { type: "TOOL_CALL_ARGS"; tool_call_id: string; delta: string; depth?: number; parent_id?: string | null }
  | { type: "TOOL_CALL_END"; tool_call_id: string; depth?: number; parent_id?: string | null }
  | { type: "TOOL_CALL_RESULT"; tool_call_id: string; name: string; content?: string; preview?: string; display_name?: string; depth?: number; parent_id?: string | null; kind?: string; is_error?: boolean; duration_ms?: number }

  // ─── Reasoning ─────────────────────────────────────────────────────
  | { type: "REASONING_START"; message_id: string; depth?: number }
  | { type: "REASONING_MESSAGE_START"; message_id: string; role?: string; depth?: number }
  | { type: "REASONING_MESSAGE_CONTENT"; message_id: string; delta: string; depth?: number }
  | { type: "REASONING_MESSAGE_END"; message_id: string; depth?: number }
  | { type: "REASONING_END"; message_id: string; depth?: number }

  // ─── ntrp-specific (non-AG-UI canonical) ───────────────────────────
  | { type: "approval_needed"; tool_id: string; name: string; path?: string | null; diff?: string | null; content_preview?: string | null }
  | { type: "background_task"; command: string; status: string; detail?: string }
  | { type: "stream_reset"; reason: "replay_gap" | string }
  | { type: "task_started"; run_id: string; task_id: string; parent_task_id?: string | null; parent_tool_call_id?: string | null; name?: string; summary?: string; depth?: number }
  | { type: "task_progress"; run_id: string; task_id: string; parent_task_id?: string | null; parent_tool_call_id?: string | null; status?: string; summary?: string; depth?: number }
  | { type: "task_finished"; run_id: string; task_id: string; parent_task_id?: string | null; parent_tool_call_id?: string | null; status: "completed" | "failed" | "cancelled"; summary?: string; depth?: number }
  | { type: "compaction_started"; run_id: string }
  | { type: "compaction_finished"; run_id: string; messages_before: number; messages_after: number }
  | { type: "message_ingested"; client_id: string; run_id: string }
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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
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

export type CancelQueuedResult = "cancelled" | "already_ingested" | "no_run";

/** Cancel a message we queued via /chat/message while a run was active.
 *  Status codes from the server:
 *    200 — removed from inject_queue
 *    409 — already pulled into the agent loop, can't cancel
 *    404 — no active run for that session, nothing to cancel */
export async function cancelQueuedMessageApi(
  config: AppConfig,
  sessionId: string,
  clientId: string,
): Promise<CancelQueuedResult> {
  const path = `/chat/inject/${encodeURIComponent(clientId)}?session_id=${encodeURIComponent(sessionId)}`;
  const desktopApi = window.ntrpDesktop?.api;
  let status: number;
  if (desktopApi) {
    const response = await desktopApi.request(config, { path, method: "DELETE" });
    status = response.status;
  } else {
    const response = await fetch(`${config.serverUrl}${path}`, {
      method: "DELETE",
      headers: headersForConfig(config, false),
    });
    status = response.status;
  }
  if (status === 200) return "cancelled";
  if (status === 409) return "already_ingested";
  if (status === 404) return "no_run";
  throw new Error(`cancelQueuedMessage: unexpected status ${status}`);
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
export type FactTrustStatus = Exclude<FactStatus, "all">;

export interface Fact {
  id: number;
  text: string;
  source_type: string;
  source_ref: string | null;
  source_ref_parts: FactSourceRefParts | null;
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
  valid_from: string | null;
  valid_until: string | null;
  superseded_by_fact_id: number | null;
  status: FactTrustStatus;
}

export type FactSourceRefParts =
  | {
      kind: "chat_segment";
      session_id: string;
      message_start: number;
      message_end: number;
    }
  | {
      kind: string;
      [key: string]: unknown;
    };

export interface FactEntityRef {
  name: string;
  entity_id: number | null;
}

export type FactLinkType = "superseded_by" | "supersedes";

export interface LinkedFact {
  id: number;
  text: string;
  link_type: FactLinkType;
  weight: number;
}

export interface FactDetail {
  fact: Fact;
  entities: FactEntityRef[];
  linked_facts: LinkedFact[];
}

export type ObservationEvidenceLevel = "unsupported" | "single_fact_seed" | "multi_fact" | "temporal_pattern";

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
  policy_version: string | null;
  evidence_level: ObservationEvidenceLevel;
}

export interface FactListFilters {
  limit?: number;
  offset?: number;
  kind?: FactKind;
  status?: FactStatus;
  accessed?: "never" | "used";
  entity?: string;
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
  if (filters.accessed) qs.set("accessed", filters.accessed);
  if (filters.entity?.trim()) qs.set("entity", filters.entity.trim());
  return apiWithConfig(config, `/facts?${qs.toString()}`, { timeout: 5000 } as RequestInit & { timeout: number });
}

export async function updateFactTextApi(config: AppConfig, id: number, text: string): Promise<{ fact: Fact }> {
  return apiWithConfig(config, `/facts/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ text }),
  });
}

export async function getFactApi(config: AppConfig, id: number): Promise<FactDetail> {
  return apiWithConfig(config, `/facts/${id}`);
}

export async function supersedeFactApi(
  config: AppConfig,
  id: number,
  text: string,
): Promise<{ old_fact: Fact; new_fact: Fact; entity_refs: FactEntityRef[] }> {
  return apiWithConfig(config, `/facts/${id}/supersede`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export interface FactMetadataUpdate {
  kind?: FactKind;
  lifetime?: FactLifetime;
  salience?: number;
  confidence?: number;
  expires_at?: string | null;
  pinned?: boolean;
  superseded_by_fact_id?: number | null;
  archived?: boolean;
}

export async function updateFactMetadataApi(
  config: AppConfig,
  id: number,
  payload: FactMetadataUpdate,
): Promise<{ fact: Fact }> {
  return apiWithConfig(config, `/facts/${id}/metadata`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteFactApi(config: AppConfig, id: number): Promise<void> {
  await apiWithConfig(config, `/facts/${id}`, { method: "DELETE" });
}

export interface ObservationListFilters {
  limit?: number;
  offset?: number;
  status?: "active" | "archived" | "all";
  accessed?: "never" | "used";
  minSources?: number;
  maxSources?: number;
}

export async function listObservationsApi(
  config: AppConfig,
  filters: ObservationListFilters = {},
): Promise<{ observations: Observation[]; total: number }> {
  const qs = new URLSearchParams();
  qs.set("limit", String(filters.limit ?? 100));
  if (filters.offset) qs.set("offset", String(filters.offset));
  if (filters.status) qs.set("status", filters.status);
  if (filters.accessed) qs.set("accessed", filters.accessed);
  if (filters.minSources !== undefined) qs.set("min_sources", String(filters.minSources));
  if (filters.maxSources !== undefined) qs.set("max_sources", String(filters.maxSources));
  return apiWithConfig(config, `/observations?${qs.toString()}`, { timeout: 5000 } as RequestInit & { timeout: number });
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

// ─── Memory observability / review ───────────────────────────────────

export interface MemoryStats {
  fact_count: number;
  observation_count: number;
}

export interface MemoryStorageHealth {
  vec_rows: number;
  missing_vec_rows: number;
  stale_vec_rows: number;
  fts_rows: number;
  missing_fts_rows: number;
  stale_fts_rows: number;
}

export interface MemoryAudit {
  facts: { no_embedding: number };
  observations: { no_embedding: number };
  storage: {
    facts: MemoryStorageHealth;
    observations: MemoryStorageHealth;
  };
  relations: Record<string, number>;
}

export interface MemoryEvent {
  id: number;
  created_at: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: number | null;
  source_type: string | null;
  source_ref: string | null;
  reason: string | null;
  policy_version: string;
  details: Record<string, unknown>;
}

export interface MemoryAccessEvent {
  id: number;
  created_at: string;
  source: string;
  query: string | null;
  retrieved_fact_ids: number[];
  retrieved_observation_ids: number[];
  injected_fact_ids: number[];
  injected_observation_ids: number[];
  omitted_fact_ids: number[];
  omitted_observation_ids: number[];
  bundled_fact_ids: number[];
  formatted_chars: number;
  policy_version: string;
  details: Record<string, unknown>;
}

export interface MemoryPruneCriteria {
  older_than_days: number;
  max_sources: number;
  limit: number;
  cutoff: string;
}

export interface MemoryPruneSummary {
  total: number;
  over_1000_chars: number;
  empty_sources: number;
}

export interface MemoryPruneCandidate {
  id: number;
  summary: string;
  created_at: string;
  updated_at: string;
  access_count: number;
  evidence_count: number;
  chars: number;
  reason: string;
}

export interface MemoryPruneDryRun {
  criteria: MemoryPruneCriteria;
  summary: MemoryPruneSummary;
  candidates: MemoryPruneCandidate[];
}

export interface MemoryPruneApplyResult {
  status: "archived" | "unchanged";
  archived: number;
  archived_ids: number[];
  skipped_ids: number[];
  candidates: MemoryPruneCandidate[];
}

export interface MemoryRecallInspectResult {
  query: string;
  limit: number;
  formatted_recall: string | null;
  facts: Fact[];
  observations: Observation[];
  bundled_sources: Record<string, Fact[]>;
  fact_reasons: Record<string, string[]>;
  observation_reasons: Record<string, string[]>;
}

export async function getMemoryStatsApi(config: AppConfig): Promise<MemoryStats> {
  return apiWithConfig(config, "/stats");
}

export async function getMemoryAuditApi(config: AppConfig): Promise<MemoryAudit> {
  return apiWithConfig(config, "/memory/audit");
}

export async function listMemoryEventsApi(
  config: AppConfig,
  limit = 100,
  filters: { action?: string } = {},
): Promise<{ events: MemoryEvent[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters.action) params.set("action", filters.action);
  return apiWithConfig(config, `/memory/events?${params.toString()}`);
}

export async function listMemoryAccessEventsApi(
  config: AppConfig,
  limit = 100,
): Promise<{ events: MemoryAccessEvent[]; facts?: Fact[]; observations?: Observation[] }> {
  return apiWithConfig(config, `/memory/access/events?limit=${limit}&include_records=true`);
}

export async function inspectMemoryRecallApi(
  config: AppConfig,
  query: string,
  limit = 5,
): Promise<MemoryRecallInspectResult> {
  return apiWithConfig(config, "/memory/recall/inspect", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });
}

export async function getMemoryPruneDryRunApi(config: AppConfig): Promise<MemoryPruneDryRun> {
  return apiWithConfig(config, "/memory/prune/dry-run", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function applyMemoryPruneApi(
  config: AppConfig,
  payload: {
    observation_ids?: number[];
    all_matching?: boolean;
    older_than_days: number;
    max_sources: number;
  },
): Promise<MemoryPruneApplyResult> {
  return apiWithConfig(config, "/memory/prune/apply", {
    method: "POST",
    body: JSON.stringify(payload),
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

export interface CustomModelSummary {
  id: string;
  base_url: string | null;
  context_window: number;
}

export interface ModelProvider {
  id: string;
  name: string;
  connected: boolean;
  key_hint: string | null;
  from_env: boolean;
  auth_type?: "api_key" | "oauth";
  model_count?: number;
  models: string[] | CustomModelSummary[];
  embedding_models: string[];
}

export interface OpenAICodexOAuthStart {
  status: string;
  url: string;
  opened: boolean;
  expires_at: number;
  instructions?: string;
}

export interface OpenAICodexOAuthStatus {
  connected: boolean;
  status: string;
  account_id?: string | null;
  expires?: number;
  error?: string | null;
  url?: string;
  opened?: boolean;
  expires_at?: number;
}

export async function listModelProvidersApi(config: AppConfig): Promise<ModelProvider[]> {
  const r = await apiWithConfig<{ providers: ModelProvider[] }>(config, "/providers");
  return r.providers;
}

export async function connectModelProviderApi(
  config: AppConfig,
  providerId: string,
  apiKey: string,
  chatModel?: string | null,
): Promise<void> {
  await apiWithConfig(config, `/providers/${encodeURIComponent(providerId)}/connect`, {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey, chat_model: chatModel || undefined }),
  });
}

export async function disconnectModelProviderApi(config: AppConfig, providerId: string): Promise<void> {
  await apiWithConfig(config, `/providers/${encodeURIComponent(providerId)}`, { method: "DELETE" });
}

export async function startOpenAICodexOAuthApi(config: AppConfig): Promise<OpenAICodexOAuthStart> {
  return apiWithConfig<OpenAICodexOAuthStart>(config, "/providers/openai-codex/oauth/browser/start", {
    method: "POST",
  });
}

export async function getOpenAICodexOAuthStatusApi(config: AppConfig): Promise<OpenAICodexOAuthStatus> {
  return apiWithConfig<OpenAICodexOAuthStatus>(config, "/providers/openai-codex/oauth/status");
}

export interface ServiceConnection {
  id: string;
  name: string;
  connected: boolean;
  key_hint: string | null;
  from_env: boolean;
}

export interface GmailAccount {
  email: string | null;
  token_file: string;
  has_send_scope?: boolean;
  error?: string;
}

export interface CreateCustomModelPayload {
  model_id: string;
  base_url: string;
  context_window: number;
  max_output_tokens: number;
  api_key?: string | null;
}

export async function listServicesApi(config: AppConfig): Promise<ServiceConnection[]> {
  const r = await apiWithConfig<{ services: ServiceConnection[] }>(config, "/services");
  return r.services;
}

export async function connectServiceApi(config: AppConfig, serviceId: string, apiKey: string): Promise<void> {
  await apiWithConfig(config, `/services/${encodeURIComponent(serviceId)}/connect`, {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function disconnectServiceApi(config: AppConfig, serviceId: string): Promise<void> {
  await apiWithConfig(config, `/services/${encodeURIComponent(serviceId)}`, { method: "DELETE" });
}

export async function listGmailAccountsApi(config: AppConfig): Promise<GmailAccount[]> {
  const r = await apiWithConfig<{ accounts: GmailAccount[] }>(config, "/gmail/accounts");
  return r.accounts;
}

export async function addGmailAccountApi(config: AppConfig): Promise<{ email: string; status: string }> {
  return apiWithConfig<{ email: string; status: string }>(config, "/gmail/add", { method: "POST" });
}

export async function removeGmailAccountApi(
  config: AppConfig,
  tokenFile: string,
): Promise<{ email: string | null; status: string }> {
  return apiWithConfig<{ email: string | null; status: string }>(
    config,
    `/gmail/${encodeURIComponent(tokenFile)}`,
    { method: "DELETE" },
  );
}

export async function createCustomModelApi(
  config: AppConfig,
  payload: CreateCustomModelPayload,
): Promise<{ status: string; model_id: string }> {
  return apiWithConfig<{ status: string; model_id: string }>(config, "/models/custom", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteCustomModelApi(
  config: AppConfig,
  modelId: string,
): Promise<{ status: string; model_id: string }> {
  return apiWithConfig<{ status: string; model_id: string }>(
    config,
    `/models/custom/${encodeURIComponent(modelId)}`,
    { method: "DELETE" },
  );
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
  model_reasoning_efforts: Record<string, string>;
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
  reasoning_efforts: Record<string, string[]>;
  chat_model: string;
  research_model: string;
  memory_model: string;
}

export async function getServerConfig(config: AppConfig): Promise<ServerConfig> {
  return parseServerConfig(await apiWithConfig<unknown>(config, "/config"));
}

export async function getServerModels(config: AppConfig): Promise<ModelsResponse> {
  return parseModelsResponse(await apiWithConfig<unknown>(config, "/models"));
}

export type ServerConfigPatch = Partial<{
  chat_model: string;
  research_model: string;
  memory_model: string;
  max_depth: number;
  reasoning_model: string;
  reasoning_effort: string | null;
  compression_threshold: number;
  max_messages: number;
  compression_keep_ratio: number;
  summary_max_tokens: number;
  consolidation_interval: number;
  web_search: "auto" | "exa" | "ddgs" | "none";
  integrations: { google?: boolean | null; memory?: boolean | null };
}>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return isRecord(value) && Object.values(value).every((item) => typeof item === "string");
}

function isStringArrayRecord(value: unknown): value is Record<string, string[]> {
  return isRecord(value) && Object.values(value).every(isStringArray);
}

function assertServerContract(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

export function parseServerConfig(data: unknown): ServerConfig {
  assertServerContract(isRecord(data), "Invalid /config response: expected an object");
  assertServerContract(typeof data.chat_model === "string", "Invalid /config response: missing chat_model");
  assertServerContract(typeof data.research_model === "string", "Invalid /config response: missing research_model");
  assertServerContract(typeof data.memory_model === "string", "Invalid /config response: missing memory_model");
  assertServerContract(isStringArray(data.reasoning_efforts), "Invalid /config response: missing reasoning_efforts");
  assertServerContract(
    isStringRecord(data.model_reasoning_efforts),
    "Invalid /config response: missing model_reasoning_efforts",
  );
  return data as unknown as ServerConfig;
}

export function parseModelsResponse(data: unknown): ModelsResponse {
  assertServerContract(isRecord(data), "Invalid /models response: expected an object");
  assertServerContract(isStringArray(data.models), "Invalid /models response: missing models");
  assertServerContract(Array.isArray(data.groups), "Invalid /models response: missing groups");
  assertServerContract(
    isStringArrayRecord(data.reasoning_efforts),
    "Invalid /models response: missing reasoning_efforts",
  );
  return data as unknown as ModelsResponse;
}

export async function patchServerConfig(
  config: AppConfig,
  patch: ServerConfigPatch,
): Promise<ServerConfig> {
  const data = await apiWithConfig<unknown>(config, "/config", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  return parseServerConfig(data);
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
