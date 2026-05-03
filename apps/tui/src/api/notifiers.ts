import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface NotifierSummary {
  name: string;
  type: string;
}

export interface NotifierConfigData {
  name: string;
  type: string;
  config: Record<string, string>;
  created_at: string;
}

export interface NotifierTypeInfo {
  fields: string[];
  accounts?: string[];
}

export async function getNotifiers(config: Config): Promise<{ notifiers: NotifierSummary[] }> {
  return api.get<{ notifiers: NotifierSummary[] }>(`${config.serverUrl}/notifiers`);
}

export async function getNotifierConfigs(config: Config): Promise<{ configs: NotifierConfigData[] }> {
  return api.get<{ configs: NotifierConfigData[] }>(`${config.serverUrl}/notifiers/configs`);
}

export async function getNotifierTypes(config: Config): Promise<{ types: Record<string, NotifierTypeInfo> }> {
  return api.get<{ types: Record<string, NotifierTypeInfo> }>(`${config.serverUrl}/notifiers/types`);
}

export async function createNotifierConfig(
  config: Config,
  data: { name: string; type: string; config: Record<string, string> }
): Promise<NotifierConfigData> {
  return api.post<NotifierConfigData>(`${config.serverUrl}/notifiers/configs`, data);
}

export async function updateNotifierConfig(
  config: Config,
  name: string,
  cfg: Record<string, string>,
  newName?: string,
): Promise<NotifierConfigData> {
  const body: { config: Record<string, string>; name?: string } = { config: cfg };
  if (newName && newName !== name) body.name = newName;
  return api.put<NotifierConfigData>(`${config.serverUrl}/notifiers/configs/${name}`, body);
}

export async function deleteNotifierConfig(config: Config, name: string): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/notifiers/configs/${name}`);
}

export async function testNotifier(config: Config, name: string): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/notifiers/configs/${name}/test`);
}
