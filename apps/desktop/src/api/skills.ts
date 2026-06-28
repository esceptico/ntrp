import { apiWithConfig, type AppConfig } from "@/api/core";
import type { SkillDescriptor } from "@/api/types";

export async function listSkills(config: AppConfig): Promise<SkillDescriptor[]> {
  const { skills } = await apiWithConfig<{ skills: SkillDescriptor[] }>(config, "/skills");
  return skills ?? [];
}

export interface SkillContent {
  name: string;
  description: string;
  path: string;
  content: string;
}

export async function fetchSkillContent(config: AppConfig, name: string): Promise<SkillContent> {
  return apiWithConfig<SkillContent>(config, `/skills/${encodeURIComponent(name)}/content`);
}
