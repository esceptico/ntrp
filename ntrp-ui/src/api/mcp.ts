import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface MCPServerInfo {
  name: string;
  transport: string;
  connected: boolean;
  tool_count: number;
  error?: string | null;
  command?: string | null;
  args?: string[] | null;
  url?: string | null;
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

export async function removeMCPServer(
  config: Config,
  name: string,
): Promise<{ status: string; name: string }> {
  return api.delete(`${config.serverUrl}/mcp/servers/${encodeURIComponent(name)}`);
}
