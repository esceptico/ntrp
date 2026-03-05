import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface MCPToolInfo {
  name: string;
  description: string;
  enabled: boolean;
}

export interface MCPServerInfo {
  name: string;
  transport: string;
  connected: boolean;
  tool_count: number;
  error?: string | null;
  command?: string | null;
  args?: string[] | null;
  url?: string | null;
  tools?: MCPToolInfo[];
  enabled: boolean;
  auth?: string | null;
}

export async function getMCPServers(config: Config): Promise<{ servers: MCPServerInfo[] }> {
  return api.get<{ servers: MCPServerInfo[] }>(`${config.serverUrl}/mcp/servers`);
}

export async function addMCPServer(
  config: Config,
  name: string,
  serverConfig: Record<string, unknown>,
): Promise<{ status: string; name: string; connected: boolean; tool_count: number; error?: string | null }> {
  return api.post(`${config.serverUrl}/mcp/servers`, { name, config: serverConfig });
}

export async function updateMCPTools(
  config: Config,
  name: string,
  tools: string[] | null,
): Promise<{ status: string }> {
  return api.put(`${config.serverUrl}/mcp/servers/${encodeURIComponent(name)}/tools`, { tools });
}

export async function toggleMCPServer(
  config: Config,
  name: string,
  enabled: boolean,
): Promise<{ status: string; name: string; enabled: boolean }> {
  return api.put(`${config.serverUrl}/mcp/servers/${encodeURIComponent(name)}/enabled`, { enabled });
}

export async function triggerMCPOAuth(
  config: Config,
  name: string,
): Promise<{ status: string; name: string; connected: boolean; tool_count: number; error?: string | null }> {
  return api.post(`${config.serverUrl}/mcp/servers/${encodeURIComponent(name)}/oauth`, undefined, { timeout: 120_000 });
}

export async function removeMCPServer(
  config: Config,
  name: string,
): Promise<{ status: string; name: string }> {
  return api.delete(`${config.serverUrl}/mcp/servers/${encodeURIComponent(name)}`);
}
