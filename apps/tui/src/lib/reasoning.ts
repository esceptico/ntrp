import type { ServerConfig } from "../api/client.js";

const FALLBACK_REASONING_EFFORTS: Record<string, string[]> = {
  "claude-opus-4-7": ["low", "medium", "high", "xhigh", "max"],
};

export function reasoningEfforts(config: ServerConfig | null | undefined): string[] {
  const fromServer = config?.reasoning_efforts;
  if (Array.isArray(fromServer) && fromServer.length > 0) return fromServer;
  return config?.chat_model ? FALLBACK_REASONING_EFFORTS[config.chat_model] ?? [] : [];
}

export function currentReasoningEffort(config: ServerConfig): string | null {
  const current = config.reasoning_effort;
  const efforts = reasoningEfforts(config);
  return current && efforts.includes(current) ? current : null;
}

export function nextReasoningEffort(config: ServerConfig): string | null {
  const efforts = reasoningEfforts(config);
  if (efforts.length === 0) return null;

  const current = currentReasoningEffort(config);
  if (current === null) return efforts[0];

  const index = efforts.indexOf(current);
  return index >= 0 && index < efforts.length - 1 ? efforts[index + 1] : null;
}

export function parseReasoningEffortArg(config: ServerConfig, raw: string | undefined): string | null | undefined {
  const arg = raw?.trim();
  if (!arg || arg === "cycle") return nextReasoningEffort(config);

  const lower = arg.toLowerCase();
  if (lower === "default" || lower === "none" || lower === "off") return null;

  return reasoningEfforts(config).find((effort) => effort.toLowerCase() === lower);
}

export function formatReasoningEffort(effort: string | null | undefined): string {
  return effort ?? "default";
}

export function reasoningUsage(config: ServerConfig): string {
  const options = ["default", ...reasoningEfforts(config)].join("|");
  return `/reasoning [show|hide|${options}]`;
}
