import type { MCPServerConfigPayload, MCPTransport } from "../../../api";
import { type KeyVal, kvToRecord } from "./editors";

export type MCPAuthMode = "auto" | "headers";

export interface MCPServerPayloadInput {
  transport: MCPTransport;
  command: string;
  argsList: string[];
  envEntries: KeyVal[];
  url: string;
  headerEntries: KeyVal[];
  auth: MCPAuthMode;
}

export function buildMCPServerPayload(input: MCPServerPayloadInput): MCPServerConfigPayload {
  if (input.transport === "stdio") {
    const env = kvToRecord(input.envEntries);
    return {
      transport: "stdio",
      command: input.command.trim(),
      args: input.argsList.map((a) => a.trim()).filter(Boolean),
      ...(env ? { env } : {}),
    };
  }

  const payload: MCPServerConfigPayload = {
    transport: "http",
    url: input.url.trim(),
  };

  if (input.auth === "headers") {
    const headers = kvToRecord(input.headerEntries);
    if (headers) payload.headers = headers;
  }
  return payload;
}
