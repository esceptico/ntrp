import type { GoogleServiceChoice, MCPServerConfigPayload, MCPTransport } from "@/api";

export const GOOGLE_SERVICE_OPTIONS: Array<{ value: GoogleServiceChoice; label: string; detail: string }> = [
  { value: "email", label: "Email only", detail: "requests Gmail read/send scopes." },
  { value: "email_calendar", label: "Email + Calendar", detail: "requests Gmail read/send and Calendar scopes." },
  { value: "calendar", label: "Calendar only", detail: "requests Calendar scope; Gmail tools will not be ready." },
  { value: "all", label: "All current Google services", detail: "is the legacy ntrp scope set and includes Pub/Sub." },
];

export function googleChoiceLabel(choice: GoogleServiceChoice): string {
  return GOOGLE_SERVICE_OPTIONS.find((option) => option.value === choice)?.label ?? choice;
}

export type SlackSetupServiceId = "slack_bot_token" | "slack_user_token";

export function slackTokenPrefixValid(serviceId: SlackSetupServiceId, token: string): boolean {
  const value = token.trim();
  return serviceId === "slack_bot_token" ? value.startsWith("xoxb-") : value.startsWith("xoxp-");
}

export interface ParsedMCPImport {
  name: string;
  config: MCPServerConfigPayload;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readNamedServerMap(value: unknown, label: string): ParsedMCPImport | null {
  if (!isRecord(value)) return null;
  const entries = Object.entries(value);
  if (entries.length > 1) {
    throw new Error(`${label} contains multiple servers. Paste one server at a time.`);
  }
  if (entries.length === 0) throw new Error(`${label} does not contain a server.`);
  const [name, config] = entries[0]!;
  if (!isRecord(config)) throw new Error(`${name} config must be an object.`);
  return normalizeMCPImport(name, config);
}

function normalizeMCPImport(nameValue: unknown, configValue: unknown): ParsedMCPImport {
  const name = typeof nameValue === "string" ? nameValue.trim() : "";
  if (!name) throw new Error("MCP server import requires a name.");
  if (!isRecord(configValue)) throw new Error("MCP server config must be an object.");
  const transport = configValue.transport;
  if (transport !== "stdio" && transport !== "http") {
    throw new Error("MCP server config requires transport \"stdio\" or \"http\".");
  }
  const config: MCPServerConfigPayload = { ...(configValue as Record<string, unknown>), transport: transport as MCPTransport } as MCPServerConfigPayload;
  delete (config as unknown as Record<string, unknown>).name;
  return { name, config };
}

export function parseMCPServerImport(text: string): ParsedMCPImport {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new Error(`Invalid JSON: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!isRecord(data)) throw new Error("MCP import must be a JSON object.");

  if ("mcpServers" in data) return readNamedServerMap(data.mcpServers, "mcpServers")!;
  if ("servers" in data) return readNamedServerMap(data.servers, "servers")!;
  if ("name" in data && "config" in data) return normalizeMCPImport(data.name, data.config);
  if ("name" in data && "transport" in data) return normalizeMCPImport(data.name, data);

  throw new Error("MCP import requires { name, config }, mcpServers, servers, or a direct config with name.");
}

export function splitLines(value: string): string[] {
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

export function parseKeyValueLines(value: string): Record<string, string> | undefined {
  const out: Record<string, string> = {};
  for (const line of splitLines(value)) {
    const index = line.indexOf("=");
    if (index <= 0) throw new Error(`Expected KEY=value line: ${line}`);
    const key = line.slice(0, index).trim();
    const val = line.slice(index + 1).trim();
    if (key) out[key] = val;
  }
  return Object.keys(out).length ? out : undefined;
}
