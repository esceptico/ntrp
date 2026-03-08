import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface SourceInfo {
  enabled?: boolean;
  connected: boolean;
  error?: string;
  accounts?: string[];
  path?: string;
  type?: string;
  mode?: "auto" | "exa" | "ddgs" | "none";
  provider?: "exa" | "ddgs" | "none" | "unknown";
  dreams?: boolean;
}

export interface ServerConfig {
  chat_model: string;
  explore_model: string;
  memory_model: string;
  embedding_model: string;
  web_search: "auto" | "exa" | "ddgs" | "none";
  web_search_provider: "exa" | "ddgs" | "none" | "unknown";
  vault_path: string;
  browser: string | null;
  google_enabled: boolean;
  has_browser: boolean;
  has_notes: boolean;
  max_depth: number;
  compression_threshold: number;
  max_messages: number;
  compression_keep_ratio: number;
  summary_max_tokens: number;
  consolidation_interval: number;
  memory_enabled: boolean;
  sources?: Record<string, SourceInfo>;
}

export interface ModelGroup {
  provider: string;
  models: string[];
}

export async function getServerConfig(config: Config): Promise<ServerConfig> {
  return api.get<ServerConfig>(`${config.serverUrl}/config`);
}

export async function updateConfig(
  config: Config,
  patch: Partial<Pick<ServerConfig, "chat_model" | "explore_model" | "memory_model" | "max_depth" | "web_search" | "compression_threshold" | "max_messages" | "compression_keep_ratio" | "summary_max_tokens" | "consolidation_interval">> & {
    sources?: Record<string, boolean>;
  }
): Promise<Record<string, unknown>> {
  return api.patch(`${config.serverUrl}/config`, patch);
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

export async function checkHealth(config: Config): Promise<{ ok: boolean; version: string | null; hasProviders: boolean }> {
  try {
    const res = await api.get<{ status: string; version?: string; auth?: boolean; has_providers?: boolean }>(`${config.serverUrl}/health`);
    const ok = res.auth !== false;
    return { ok, version: res.version ?? null, hasProviders: res.has_providers ?? true };
  } catch {
    return { ok: false, version: null, hasProviders: true };
  }
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

export async function getDirectives(config: Config): Promise<{ content: string }> {
  return api.get<{ content: string }>(`${config.serverUrl}/directives`);
}

export async function updateDirectives(config: Config, content: string): Promise<{ content: string }> {
  return api.put<{ content: string }>(`${config.serverUrl}/directives`, { content });
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
