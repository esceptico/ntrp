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
}

export interface HistoryMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning_content?: string;
  tool_calls?: HistoryToolCall[];
  tool_call_id?: string;
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
  | { type: "TEXT_MESSAGE_START"; message_id: string; role?: string }
  | { type: "TEXT_MESSAGE_CONTENT"; message_id: string; delta: string }
  | { type: "TEXT_MESSAGE_END"; message_id: string; content?: string }

  // ─── Tool calls (Start / Args / End / Result) ──────────────────────
  | { type: "TOOL_CALL_START"; tool_call_id: string; tool_call_name: string; description?: string; display_name?: string; parent_message_id?: string | null }
  | { type: "TOOL_CALL_ARGS"; tool_call_id: string; delta: string }
  | { type: "TOOL_CALL_END"; tool_call_id: string }
  | { type: "TOOL_CALL_RESULT"; tool_call_id: string; name: string; content?: string; preview?: string; display_name?: string }

  // ─── Reasoning ─────────────────────────────────────────────────────
  | { type: "REASONING_START"; message_id: string }
  | { type: "REASONING_MESSAGE_START"; message_id: string; role?: string }
  | { type: "REASONING_MESSAGE_CONTENT"; message_id: string; delta: string }
  | { type: "REASONING_MESSAGE_END"; message_id: string }
  | { type: "REASONING_END"; message_id: string }

  // ─── ntrp-specific (non-AG-UI canonical) ───────────────────────────
  | { type: "approval_needed"; tool_id: string; name: string; path?: string | null; diff?: string | null; content_preview?: string | null }
  | { type: "background_task"; command: string; status: string; detail?: string }
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
