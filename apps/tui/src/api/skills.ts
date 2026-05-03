import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface Skill {
  name: string;
  description: string;
  location: string;
}

export async function getSkills(config: Config): Promise<{ skills: Skill[] }> {
  return api.get(`${config.serverUrl}/skills`);
}

export async function installSkill(config: Config, source: string): Promise<{ name: string; description: string; status: string }> {
  return api.post(`${config.serverUrl}/skills/install`, { source }, { timeout: 60000 });
}

export async function removeSkill(config: Config, name: string): Promise<{ status: string }> {
  return api.delete(`${config.serverUrl}/skills/${name}`);
}
