import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface ProviderInfo {
  id: string;
  name: string;
  connected: boolean;
  key_hint?: string | null;
  from_env?: boolean;
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

