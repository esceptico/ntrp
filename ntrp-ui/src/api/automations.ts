import type { Config } from "../types.js";
import { api, getApiKey } from "./fetch.js";

export interface TimeTrigger {
  type: "time";
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
}

export interface EventTrigger {
  type: "event";
  event_type: string;
  lead_minutes?: number;
}

export interface IdleTrigger {
  type: "idle";
  idle_minutes: number;
}

export interface CountTrigger {
  type: "count";
  every_n: number;
}

export type Trigger = TimeTrigger | EventTrigger | IdleTrigger | CountTrigger;

export interface Automation {
  task_id: string;
  name: string;
  description: string;
  model: string | null;
  triggers: Trigger[];
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
  last_result: string | null;
  writable: boolean;
  running_since: string | null;
  handler: string | null;
  builtin: boolean;
  cooldown_minutes: number | null;
}

export interface CreateAutomationData {
  name: string;
  description: string;
  model?: string;
  trigger_type?: "time" | "event";
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
  event_type?: string;
  lead_minutes?: number;
  writable: boolean;
  triggers?: Trigger[];
  cooldown_minutes?: number;
}

export interface UpdateAutomationData {
  name?: string;
  description?: string;
  model?: string;
  trigger_type?: "time" | "event";
  at?: string;
  days?: string;
  every?: string;
  start?: string;
  end?: string;
  event_type?: string;
  lead_minutes?: number;
  writable?: boolean;
  triggers?: Trigger[];
  cooldown_minutes?: number;
}

export async function createAutomation(config: Config, data: CreateAutomationData): Promise<Automation> {
  return api.post<Automation>(`${config.serverUrl}/automations`, data);
}

export async function getAutomations(config: Config): Promise<{ automations: Automation[] }> {
  return api.get<{ automations: Automation[] }>(`${config.serverUrl}/automations`);
}

export async function toggleAutomation(config: Config, taskId: string): Promise<{ enabled: boolean }> {
  return api.post<{ enabled: boolean }>(`${config.serverUrl}/automations/${taskId}/toggle`);
}

export async function updateAutomation(config: Config, taskId: string, data: UpdateAutomationData): Promise<Automation> {
  return api.patch<Automation>(`${config.serverUrl}/automations/${taskId}`, data);
}

export async function deleteAutomation(config: Config, taskId: string): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/automations/${taskId}`);
}

export async function getAutomationDetail(config: Config, taskId: string): Promise<Automation> {
  return api.get<Automation>(`${config.serverUrl}/automations/${taskId}`);
}

export async function toggleWritable(config: Config, taskId: string): Promise<{ writable: boolean }> {
  return api.post<{ writable: boolean }>(`${config.serverUrl}/automations/${taskId}/writable`);
}

export async function runAutomation(config: Config, taskId: string): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/automations/${taskId}/run`);
}

export interface AutomationEvent {
  type: string;
  name?: string;
  display_name?: string;
  description?: string;
  preview?: string;
  content?: string;
}

export function connectAutomationEvents(
  taskId: string,
  config: Config,
  onEvent: (event: AutomationEvent) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    const headers: Record<string, string> = {};
    const apiKey = getApiKey();
    if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    try {
      const response = await fetch(`${config.serverUrl}/automations/${taskId}/events`, {
        headers,
        signal: controller.signal,
      });
      if (!response.ok) return;

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const parsed = JSON.parse(line.slice(6));
              if (parsed?.type) onEvent(parsed);
            } catch { /* keepalive */ }
          }
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
    }
  })();

  return () => controller.abort();
}

