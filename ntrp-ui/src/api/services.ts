import type { Config } from "../types.js";
import { api } from "./fetch.js";

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
