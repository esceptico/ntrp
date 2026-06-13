export type RuntimeRunStatus =
  | "pending"
  | "running"
  | "backgrounded"
  | "interrupted"
  | "error"
  | "failed"
  | "cancelled"
  | "completed";

export interface RuntimeApprovalSnapshot {
  tool_id: string;
  tool_name: string;
  preview?: string | null;
  diff?: string | null;
  status: "pending";
  requested_at?: string | null;
  run_id?: string | null;
}

export interface RuntimeQueuedMessageSnapshot {
  client_id: string;
  text: string;
  images?: HistoryImage[];
  status: "pending" | "failed";
  server_status?: string | null;
  enqueued_at?: string | null;
  run_id?: string | null;
}

export interface ActiveRunSnapshot {
  run_id: string;
  status: RuntimeRunStatus;
  started_at?: string | null;
  updated_at?: string | null;
  ended_at?: string | null;
  stop_reason?: string | null;
  checkpoint_seq: number;
  latest_event_seq: number;
  error_code?: string | null;
  error_message?: string | null;
  pending_approvals: RuntimeApprovalSnapshot[];
  queued_messages: RuntimeQueuedMessageSnapshot[];
}

export interface SessionRuntimeSnapshot {
  session_id: string;
  latest_event_seq: number;
  checkpoint_seq: number;
  active_run: ActiveRunSnapshot | null;
  pending_approvals: RuntimeApprovalSnapshot[];
  queued_messages: RuntimeQueuedMessageSnapshot[];
}

export interface AppConfig {
  serverUrl: string;
  apiKey: string;
}

export type SessionType = "chat" | "channel" | "agent";

export interface Project {
  project_id: string;
  name: string;
  default_cwd: string | null;
  instructions: string | null;
  knowledge_scope: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface SessionListItem {
  session_id: string;
  started_at: string;
  last_activity: string;
  name: string | null;
  message_count: number;
  project_id?: string | null;
  /** Per-chat model override. null/undefined → falls back to the global
   *  default (config.chat_model), which is also what new chats inherit. */
  chat_model?: string | null;
  /** "chat" for normal user conversations; "channel" for agent-spawned
   *  feed sessions (post-mode loop output, push-style updates). */
  session_type?: SessionType;
  /** When set, the channel session was spawned by this automation. */
  origin_automation_id?: string | null;
  parent_session_id?: string | null;
  parent_tool_call_id?: string | null;
  agent_type?: string | null;
  agent_status?: string | null;
  active_run_id?: string | null;
  run_status?: RuntimeRunStatus | null;
  checkpoint_seq?: number;
  latest_event_seq?: number;
  is_active?: boolean;
  pending_approvals_count?: number;
  queued_messages_count?: number;
  run_error_code?: string | null;
  run_stop_reason?: string | null;
}

export interface SessionGoal {
  session_id: string;
  goal_id: string;
  objective: string;
  status: "active" | "paused" | "blocked" | "budget_limited" | "complete";
  evidence: { text: string; created_at: string }[];
  blocked_reason?: string | null;
  token_budget?: number | null;
  tokens_used: number;
  time_used_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface HistoryToolCall {
  id: string;
  name: string;
  arguments: string;
  display_name?: string;
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
  data?: unknown;
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
  /** True for system-generated user messages that should stay in the
   *  model's conversation history but be hidden from the transcript UI
   *  (e.g. loop tick prompts). */
  is_meta?: boolean;
}

export type TodoStatus = "pending" | "in_progress" | "completed";

export interface TodoListItem {
  content: string;
  status: TodoStatus;
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

export type ToolOverrideDecision = "approve" | "ask" | "deny";

export interface ToolPolicyMetadata {
  action: "read" | "draft" | "write" | "execute";
  scope: "internal" | "external";
  requires_approval: boolean;
  permissions: string[];
  timeout_seconds: number | null;
  audit: boolean;
  max_result_chars: number | null;
  offload: boolean;
}

export interface ToolMetadata {
  name: string;
  display_name: string;
  description: string;
  kind: string;
  source?: string | null;
  policy: ToolPolicyMetadata;
  override?: ToolOverrideDecision;
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
type CommonServerEventFields = { timestamp?: number; seq?: number; session_id?: string; replay?: boolean };
type CompactionOwner =
  | { scope?: "run"; parent_tool_call_id?: null }
  | { scope: "agent"; parent_tool_call_id: string };

export type ServerEvent = CommonServerEventFields & (
  // ─── Run lifecycle ──────────────────────────────────────────────────
  | { type: "RUN_STARTED"; run_id: string; session_id: string; session_name?: string | null; skip_approvals?: boolean; is_meta_run?: boolean; meta_client_id?: string | null }
  | { type: "session_updated"; session_id: string; name?: string | null }
  | { type: "RUN_FINISHED"; run_id: string; usage?: { prompt: number; completion: number; total?: number; cache_read?: number; cache_write?: number; cost: number }; context_input_tokens?: number | null; message_count?: number }
  | { type: "run_cancelled"; run_id: string }
  | { type: "run_backgrounded"; run_id: string; session_id?: string }
  | { type: "RUN_ERROR"; run_id: string; message: string; code?: string; debug_id?: string | null; recoverable?: boolean }
  | { type: "token_usage"; run_id: string; usage: { prompt: number; completion: number; total?: number; cache_read?: number; cache_write?: number }; cost?: number; message_count?: number | null; scope?: "run" | "tool"; task_id?: string | null; child_run_id?: string | null; workflow_id?: string | null; phase?: string | null }
  | { type: "thinking"; status: string; run_id?: string | null }

  // ─── Text messages (Start / Content / End) ─────────────────────────
  | { type: "TEXT_MESSAGE_START"; message_id: string; role?: string; depth?: number }
  | { type: "TEXT_MESSAGE_CONTENT"; message_id: string; delta: string; depth?: number }
  | { type: "TEXT_MESSAGE_END"; message_id: string; content?: string; depth?: number }

  // ─── Tool calls (Start / Args / End / Result) ──────────────────────
  | { type: "TOOL_CALL_START"; tool_call_id: string; tool_call_name: string; description?: string; display_name?: string; parent_message_id?: string | null; depth?: number; parent_id?: string | null; kind?: string }
  | { type: "TOOL_CALL_ARGS"; tool_call_id: string; delta: string; depth?: number; parent_id?: string | null }
  | { type: "TOOL_CALL_END"; tool_call_id: string; depth?: number; parent_id?: string | null }
  | { type: "TOOL_CALL_RESULT"; tool_call_id: string; name: string; content?: string; preview?: string; display_name?: string; depth?: number; parent_id?: string | null; kind?: string; is_error?: boolean; duration_ms?: number; data?: Record<string, unknown> | null }

  // ─── Reasoning ─────────────────────────────────────────────────────
  | { type: "REASONING_START"; message_id: string; depth?: number }
  | { type: "REASONING_MESSAGE_START"; message_id: string; role?: string; depth?: number }
  | { type: "REASONING_MESSAGE_CONTENT"; message_id: string; delta: string; depth?: number }
  | { type: "REASONING_MESSAGE_END"; message_id: string; depth?: number }
  | { type: "REASONING_END"; message_id: string; depth?: number }

  // ─── ntrp-specific (non-AG-UI canonical) ───────────────────────────
  | { type: "approval_needed"; tool_id: string; name: string; path?: string | null; diff?: string | null; content_preview?: string | null }
  | { type: "input_needed"; tool_id: string; name: string; title: string; html: string }
  | {
      type: "background_task";
      event_id?: string | null;
      task_id: string;
      session_id?: string;
      run_id?: string | null;
      child_run_id?: string | null;
      child_session_id?: string | null;
      parent_tool_call_id?: string | null;
      agent_type?: string | null;
      wait?: boolean | null;
      command: string;
      status: "started" | "activity" | "completed" | "failed" | "cancelled" | "interrupted" | "cancel_requested" | string;
      detail?: string | null;
      result_ref?: string | null;
      model_visible?: boolean;
      ui_visible?: boolean;
      terminal?: boolean;
    }
  | { type: "stream_reset"; reason: "replay_gap" | string }
  | { type: "stream_keepalive"; latest_seq: number }
  | { type: "task_started"; session_id?: string | null; run_id: string; task_id: string; parent_task_id?: string | null; parent_tool_call_id?: string | null; child_run_id?: string | null; child_session_id?: string | null; agent_type?: string | null; wait?: boolean | null; name?: string; summary?: string; depth?: number; workflow_id?: string | null; phase?: string | null }
  | { type: "task_progress"; session_id?: string | null; run_id: string; task_id: string; parent_task_id?: string | null; parent_tool_call_id?: string | null; child_run_id?: string | null; child_session_id?: string | null; agent_type?: string | null; wait?: boolean | null; name?: string; status?: string; summary?: string; depth?: number; workflow_id?: string | null; phase?: string | null }
  | { type: "task_finished"; session_id?: string | null; run_id: string; task_id: string; parent_task_id?: string | null; parent_tool_call_id?: string | null; child_run_id?: string | null; child_session_id?: string | null; agent_type?: string | null; wait?: boolean | null; name?: string; status: "completed" | "failed" | "cancelled"; summary?: string; depth?: number; workflow_id?: string | null; phase?: string | null; tool_count?: number | null }
  | { type: "workflow_started"; session_id?: string | null; run_id: string; workflow_id: string; parent_tool_call_id?: string | null; name?: string; description?: string; phases?: string[] }
  | { type: "workflow_finished"; session_id?: string | null; run_id: string; workflow_id: string; status: "completed" | "failed" | "cancelled"; summary?: string; agent_count?: number }
  | ({ type: "compaction_started"; run_id: string } & CompactionOwner)
  | ({ type: "compaction_finished"; run_id: string; messages_before: number; messages_after: number } & CompactionOwner)
  | { type: "message_ingested"; client_id: string; run_id: string }
  | { type: "goal_updated"; session_id: string; goal: SessionGoal }
  | { type: "goal_cleared"; session_id: string }
  | { type: "todo_updated"; run_id: string; tool_call_id?: string | null; explanation?: string | null; items: TodoListItem[] }
);

export const STORAGE_KEY = "ntrp.desktop.config";
export const DEFAULT_API_TIMEOUT_MS = 60_000;

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
  const effectiveTimeout = timeout ?? DEFAULT_API_TIMEOUT_MS;
  const body = typeof requestInit.body === "string" ? requestInit.body : undefined;
  const desktopApi = window.ntrpDesktop?.api;

  if (desktopApi) {
    const request = {
      path,
      method: requestInit.method ?? "GET",
      body,
      timeout: effectiveTimeout,
    };
    const response: ApiBridgeResponse = await desktopRequestWithTimeout(desktopApi, config, request, effectiveTimeout);
    if (!response.ok) throw new Error(errorMessageFromResponse(response));
    return response.contentType.includes("application/json") ? (response.data as T) : (undefined as T);
  }

  const controller = new AbortController();
  const timeoutId = effectiveTimeout > 0 ? window.setTimeout(() => controller.abort(), effectiveTimeout) : null;
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

async function desktopRequestWithTimeout(
  desktopApi: NonNullable<NonNullable<Window["ntrpDesktop"]>["api"]>,
  config: AppConfig,
  request: Parameters<NonNullable<NonNullable<Window["ntrpDesktop"]>["api"]>["request"]>[1],
  timeoutMs: number,
): Promise<ApiBridgeResponse> {
  if (timeoutMs <= 0) return desktopApi.request(config, request);
  let timeoutId: ReturnType<typeof globalThis.setTimeout> | null = null;
  try {
    return await Promise.race([
      desktopApi.request(config, request),
      new Promise<never>((_, reject) => {
        timeoutId = globalThis.setTimeout(() => {
          reject(new Error(`Request timed out for ${request.method ?? "GET"} ${request.path}`));
        }, timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId) globalThis.clearTimeout(timeoutId);
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

export async function cancelRun(
  config: AppConfig,
  runId: string | null,
  sessionId?: string | null,
): Promise<void> {
  // Prefer run_id; fall back to session_id so the server resolves the active
  // run when the client has no reliable run_id (backgrounded/automation runs).
  const body = runId ? { run_id: runId } : { session_id: sessionId ?? null };
  await apiWithConfig(config, "/cancel", {
    method: "POST",
    body: JSON.stringify(body),
  });
}


/** Pin a fact to memory by writing it as an atomic, pinned record in the flat
 *  records pool. There is no scope/project partition — one pool. */
export async function pinToMemoryApi(
  config: AppConfig,
  fact: string,
): Promise<{ written: boolean }> {
  const text = fact.trim();
  if (!text) return { written: false };
  const r = await apiWithConfig<{ record: { id: string } }>(config, "/admin/memory/record", {
    method: "POST",
    body: JSON.stringify({ text, kind_tag: "note" }),
  });
  await apiWithConfig(config, `/admin/memory/record/${encodeURIComponent(r.record.id)}/pin`, {
    method: "POST",
    body: JSON.stringify({ pinned: true }),
  });
  return { written: true };
}

export async function cancelSubagentApi(
  config: AppConfig,
  runId: string,
  toolCallId: string,
): Promise<void> {
  await apiWithConfig(
    config,
    `/chat/subagents/${encodeURIComponent(toolCallId)}/cancel?run_id=${encodeURIComponent(runId)}`,
    { method: "POST" },
  );
}

const COMPACT_TIMEOUT_MS = 600_000;

export interface CompactResponse {
  status: string;
  message?: string;
  message_count?: number;
  before_messages?: number;
  after_messages?: number;
  messages_compressed?: number;
}

export async function compactSessionApi(config: AppConfig, sessionId: string): Promise<CompactResponse> {
  return apiWithConfig<CompactResponse>(config, "/compact", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
    timeout: COMPACT_TIMEOUT_MS,
  } as RequestInit & { timeout: number });
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

export async function listProjectsApi(config: AppConfig): Promise<Project[]> {
  const response = await apiWithConfig<{ projects: Project[] }>(config, "/projects");
  return response.projects;
}

export async function createProjectApi(
  config: AppConfig,
  payload: { name: string; default_cwd?: string | null; instructions?: string | null },
): Promise<Project> {
  return apiWithConfig<Project>(config, "/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateProjectApi(
  config: AppConfig,
  projectId: string,
  patch: Partial<Pick<Project, "name" | "default_cwd" | "instructions" | "knowledge_scope">>,
): Promise<Project> {
  return apiWithConfig<Project>(config, `/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function moveSessionToProjectApi(
  config: AppConfig,
  sessionId: string,
  projectId: string | null,
): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/project`, {
    method: "POST",
    body: JSON.stringify({ project_id: projectId }),
  });
}

export async function updateSessionModelApi(
  config: AppConfig,
  sessionId: string,
  chatModel: string | null,
): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/model`, {
    method: "PUT",
    body: JSON.stringify({ chat_model: chatModel }),
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
  project_id?: string | null;
  session_type?: SessionType;
  origin_automation_id?: string | null;
  parent_session_id?: string | null;
  parent_tool_call_id?: string | null;
  agent_type?: string | null;
  agent_status?: string | null;
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

// ─── MCP servers ──────────────────────────────────────────────────────

export type MCPTransport = "stdio" | "http";

export interface MCPTool {
  name: string;
  full_name: string;
  description: string;
  enabled: boolean;
  policy: ToolPolicyMetadata;
  override?: ToolOverrideDecision;
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
  header_keys?: string[];
  has_client_credentials: boolean;
  client_id?: string | null;
  redirect_port?: number | null;
  scope?: string | null;
  client_name?: string | null;
  has_client_secret?: boolean;
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
): Promise<{ session_id: string; name: string | null; started_at: string; last_activity: string; project_id?: string | null }> {
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

// ─── Setup assistant contracts ─────────────────────────────────────────

export type GoogleServiceChoice = "email" | "email_calendar" | "calendar" | "all";

export interface GoogleCredentialsStatus {
  path: string;
  exists: boolean;
  valid: boolean;
  client_id: string | null;
  client_type: string | null;
  error: string | null;
}

export interface ToolProviderConnection {
  id: string;
  label: string;
  kind: "native" | "mcp";
  status: "connected" | "error" | "not_configured";
  detail: string | null;
  tool_count: number;
}

export interface CalendarTokenStatus {
  token_file: string;
  has_calendar_scope: boolean;
  error?: string | null;
}

export interface SetupStatus {
  google: {
    enabled: boolean;
    credentials: GoogleCredentialsStatus;
    accounts: GmailAccount[];
    calendar_tokens: CalendarTokenStatus[];
    provider_statuses: ToolProviderConnection[];
  };
  slack: {
    services: ServiceConnection[];
    provider_status: ToolProviderConnection | null;
  };
  mcp: {
    servers: MCPServer[];
    provider_statuses: ToolProviderConnection[];
  };
}

export interface GooglePreflightResponse {
  ok: boolean;
  credentials: GoogleCredentialsStatus;
  scopes: string[];
  warnings: string[];
}

export interface SlackVerifyResponse {
  ok: boolean;
  token_kind: "bot" | "user";
  team?: string | null;
  team_id?: string | null;
  user?: string | null;
  bot_id?: string | null;
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

export async function getSetupStatusApi(config: AppConfig): Promise<SetupStatus> {
  return apiWithConfig<SetupStatus>(config, "/setup/status");
}

export async function saveGoogleCredentialsApi(
  config: AppConfig,
  payload: { path?: string; json?: unknown },
): Promise<{ status: string; credentials: GoogleCredentialsStatus }> {
  return apiWithConfig<{ status: string; credentials: GoogleCredentialsStatus }>(config, "/setup/google/credentials", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function preflightGoogleSetupApi(
  config: AppConfig,
  serviceChoice: GoogleServiceChoice,
): Promise<GooglePreflightResponse> {
  return apiWithConfig<GooglePreflightResponse>(config, "/setup/google/preflight", {
    method: "POST",
    body: JSON.stringify({ service_choice: serviceChoice }),
  });
}

export async function addGmailAccountApi(
  config: AppConfig,
  serviceChoice: GoogleServiceChoice = "all",
): Promise<{ email: string | null; status: string; token_file?: string; scopes?: string[] }> {
  return apiWithConfig<{ email: string | null; status: string; token_file?: string; scopes?: string[] }>(config, "/gmail/add", {
    method: "POST",
    body: JSON.stringify({ service_choice: serviceChoice }),
  });
}

export async function verifySlackTokenApi(
  config: AppConfig,
  serviceId: "slack_bot_token" | "slack_user_token",
  apiKey: string,
): Promise<SlackVerifyResponse> {
  return apiWithConfig<SlackVerifyResponse>(config, "/setup/slack/verify", {
    method: "POST",
    body: JSON.stringify({ service_id: serviceId, api_key: apiKey }),
  });
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
  /** Hard token ceiling of the active chat model. */
  chat_model_max_context: number;
  /** Configured compaction ceiling and actual trigger after server headroom. */
  compaction_token_limit: number;
  compaction_token_trigger: number;
  research_model: string;
  /** Default model for workflow agents; optional until the server ships the key. */
  workflow_model?: string;
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
  tool_overrides: Record<string, ToolOverrideDecision>;
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
  workflow_model: string;
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
  tool_overrides: Record<string, ToolOverrideDecision>;
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

function isToolOverrideRecord(value: unknown): value is Record<string, ToolOverrideDecision> {
  return (
    isRecord(value) &&
    Object.values(value).every((item) => item === "approve" || item === "ask" || item === "deny")
  );
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
  assertServerContract(
    typeof data.compaction_token_limit === "number",
    "Invalid /config response: missing compaction_token_limit",
  );
  assertServerContract(
    typeof data.compaction_token_trigger === "number",
    "Invalid /config response: missing compaction_token_trigger",
  );
  assertServerContract(
    data.tool_overrides === undefined || isToolOverrideRecord(data.tool_overrides),
    "Invalid /config response: invalid tool_overrides",
  );
  if (data.tool_overrides === undefined) data.tool_overrides = {};
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

export async function listToolsApi(config: AppConfig): Promise<{ tools: ToolMetadata[] }> {
  return apiWithConfig(config, "/tools");
}

// ─── Automations ───────────────────────────────────────────────────

export type AutomationTriggerType = "time" | "event" | "idle" | "count" | "message";

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
  every_n?: number;
  threshold?: number;
  scope?: string;
  // Message (slack watcher). The editor submits names (channel/from_user);
  // the server resolves them to ids at save time and echoes both the *_id and
  // *_name fields back on read.
  source?: string;
  // Channel names on the way in (editor → server); the server resolves them
  // and echoes back {id,name} objects on read. One or more channels.
  channels?: (string | { id: string; name: string })[];
  from_user?: string;
  from_user_id?: string | null;
  from_user_name?: string | null;
  contains?: string[];
}

export type AutomationKind = "automation" | "loop";

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
  /** Most recent run outcome ("completed" | "failed" | "running"), and the
   *  last few statuses newest-first for the card sparkline. Null/empty until
   *  the automation has fired since run-history landed. */
  last_status?: string | null;
  recent_statuses?: string[];
  /** Textual output from the most recent run (markdown). Null until the
   *  automation has actually run once. */
  last_result: string | null;
  auto_approve: boolean;
  running_since: string | null;
  handler: string | null;
  builtin: boolean;
  cooldown_minutes: number | null;
  /** "automation" for standard scheduled tasks; "loop" for self-paced /loop
   *  and post-mode tasks. The composer already surfaces loops in a chip, so
   *  the desktop hides kind=loop from the main automation list. */
  kind?: AutomationKind;
  /** Loops with read_history=false are "channels" (post-mode feeds) — their
   *  spawned sessions are channel-type rather than chat-type. */
  read_history?: boolean;
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
  idle_minutes?: number;
  every_n?: number;
  auto_approve?: boolean;
  start?: string;
  end?: string;
  triggers?: AutomationTrigger[];
  cooldown_minutes?: number | null;
  /** When set, the server marks the originating suggestion `accepted` on
   *  successful create (see suggestionToPayload / AutomationSuggestion). */
  from_suggestion_id?: string;
}

export type UpdateAutomationPayload = Partial<
  CreateAutomationPayload & { enabled?: boolean }
>;

export async function listAutomationsApi(config: AppConfig): Promise<Automation[]> {
  const r = await apiWithConfig<{ automations: Automation[] }>(config, "/automations");
  return r.automations;
}

export interface AutomationRun {
  id: number;
  task_id: string;
  started_at: string;
  ended_at: string | null;
  status: string;
  result: string | null;
  error: string | null;
}

export async function listAutomationRunsApi(
  config: AppConfig,
  taskId: string,
  limit = 30,
): Promise<AutomationRun[]> {
  const r = await apiWithConfig<{ runs: AutomationRun[] }>(
    config,
    `/automations/${encodeURIComponent(taskId)}/runs?limit=${limit}`,
  );
  return r.runs;
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

// ─── Automation suggestions ──────────────────────────────────────────

/** Contextual, server-synthesized automation the user can accept in one
 *  click. Mirrors the `GET /automations/suggestions` response shape. */
export interface AutomationSuggestion {
  id: string;
  name: string;
  description: string;
  triggers: AutomationTrigger[];
  rationale: string;
  evidence: string[];
  category: string;
  icon: string | null;
}

export async function listAutomationSuggestionsApi(config: AppConfig): Promise<AutomationSuggestion[]> {
  const r = await apiWithConfig<{ suggestions: AutomationSuggestion[] }>(config, "/automations/suggestions");
  return r.suggestions;
}

export async function dismissAutomationSuggestionApi(config: AppConfig, id: string): Promise<void> {
  await apiWithConfig(config, `/automations/suggestions/${encodeURIComponent(id)}/dismiss`, {
    method: "POST",
  });
}

export async function refreshAutomationSuggestionsApi(config: AppConfig): Promise<AutomationSuggestion[]> {
  const r = await apiWithConfig<{ suggestions: AutomationSuggestion[] }>(config, "/automations/suggestions/refresh", {
    method: "POST",
  });
  return r.suggestions;
}

/** Convert a suggestion into the editor's create payload. Flattens the
 *  first trigger into the schedule fields `formFromPreset` expects, so the
 *  existing automation editor hydrates unchanged. */
export function suggestionToPayload(s: AutomationSuggestion): CreateAutomationPayload {
  const trigger = s.triggers[0];
  const schedule =
    trigger.type === "event"
      ? { trigger_type: "event" as const, event_type: trigger.event_type, lead_minutes: trigger.lead_minutes }
      : { trigger_type: "time" as const, at: trigger.at, days: trigger.days, every: trigger.every };
  return {
    name: s.name,
    description: s.description,
    from_suggestion_id: s.id,
    ...schedule,
  };
}

export interface BackgroundTaskSummary {
  task_id: string;
  child_run_id?: string | null;
  child_session_id?: string | null;
  session_id?: string;
  parent_run_id?: string | null;
  parent_tool_call_id?: string | null;
  agent_type?: string | null;
  wait?: boolean | null;
  status?: "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cancel_requested" | string;
  command: string;
  detail?: string | null;
  result_ref?: string | null;
}

export interface ChildAgentResult {
  task_id: string;
  child_run_id: string;
  session_id: string;
  status: "running" | "activity" | "completed" | "failed" | "cancelled" | "interrupted" | "cancel_requested" | string;
  terminal: boolean;
  result?: string | null;
  result_ref?: string | null;
}

export async function listBackgroundTasksApi(
  config: AppConfig,
  sessionId: string,
): Promise<BackgroundTaskSummary[]> {
  const r = await apiWithConfig<{ tasks: BackgroundTaskSummary[] }>(
    config,
    `/chat/background-tasks?session_id=${encodeURIComponent(sessionId)}`,
  );
  return r.tasks;
}

export async function listChildAgentsApi(
  config: AppConfig,
  sessionId: string,
): Promise<BackgroundTaskSummary[]> {
  const r = await apiWithConfig<{ tasks: BackgroundTaskSummary[] }>(
    config,
    `/chat/child-agents?session_id=${encodeURIComponent(sessionId)}`,
  );
  return r.tasks;
}

export async function getChildAgentResultApi(
  config: AppConfig,
  sessionId: string,
  childRunId: string,
  options: { wait?: boolean; timeoutSeconds?: number } = {},
): Promise<ChildAgentResult> {
  const query = new URLSearchParams({ session_id: sessionId });
  if (options.wait) query.set("wait", "true");
  if (options.timeoutSeconds != null) query.set("timeout_seconds", String(options.timeoutSeconds));
  return apiWithConfig<ChildAgentResult>(
    config,
    `/chat/child-agents/${encodeURIComponent(childRunId)}/result?${query.toString()}`,
  );
}

export async function cancelBackgroundTaskApi(
  config: AppConfig,
  sessionId: string,
  taskId: string,
): Promise<void> {
  await apiWithConfig(
    config,
    `/chat/background-tasks/${encodeURIComponent(taskId)}/cancel?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST" },
  );
}

export async function cancelChildAgentApi(
  config: AppConfig,
  sessionId: string,
  childRunId: string,
): Promise<void> {
  await apiWithConfig(
    config,
    `/chat/child-agents/${encodeURIComponent(childRunId)}/cancel?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST" },
  );
}

export interface TodoOverride {
  items: TodoListItem[];
  explanation: string | null;
  updated_at: string;
}

// Manual todo edits, persisted server-side so the agent sees them on its next
// run. The agent's own update_todos clears the override (its list wins).
export async function getTodoOverrideApi(
  config: AppConfig,
  sessionId: string,
): Promise<TodoOverride | null> {
  return apiWithConfig<TodoOverride | null>(config, `/sessions/${encodeURIComponent(sessionId)}/todo`);
}

export async function setTodoOverrideApi(
  config: AppConfig,
  sessionId: string,
  items: TodoListItem[],
): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/todo`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export async function clearTodoOverrideApi(config: AppConfig, sessionId: string): Promise<void> {
  await apiWithConfig(config, `/sessions/${encodeURIComponent(sessionId)}/todo`, { method: "DELETE" });
}

// Steer a running background agent — deliver a message into its loop at its
// next step. sessionId is the PARENT session that owns the agent.
export async function sendToChildAgentApi(
  config: AppConfig,
  sessionId: string,
  childRunId: string,
  message: string,
): Promise<void> {
  await apiWithConfig(
    config,
    `/chat/child-agents/${encodeURIComponent(childRunId)}/inject?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST", body: JSON.stringify({ message }) },
  );
}
