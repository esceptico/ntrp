import type { Config } from "../types.js";
import { api } from "./fetch.js";

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

