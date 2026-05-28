import type { AppConfig } from "../api";
import { apiWithConfig } from "../api";

export type MemoryItemKind = "episode" | "observation" | "claim" | "skill" | "proposal" | "artifact_ref";
export type MemoryItemStatus = "active" | "superseded" | "archived";
export type MemoryParentRole = "step" | "evidence" | "contradicts" | "supersedes" | "similar_to";

export interface MemoryItemSummary {
  id: string;
  kind: MemoryItemKind;
  content: string;
  provenance: string;
  source_refs: unknown[];
  confidence: number;
  status: MemoryItemStatus;
  valid_from: string | null;
  invalid_at: string | null;
  scope: string;
  tags: string[];
  artifact_ref: unknown | null;
  usage: unknown | null;
  feedback: unknown | null;
  created_at: string | null;
  updated_at: string | null;
  has_embedding: boolean;
}

export interface MemoryItemParentLink {
  parent_id: string;
  role: MemoryParentRole;
  order: number | null;
  created_at: string | null;
  parent: MemoryItemSummary | null;
}

export interface MemoryItemDetail {
  item: MemoryItemSummary;
  parents: MemoryItemParentLink[];
}

export interface MemoryItemsPage {
  items: MemoryItemSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface MemoryStats {
  counts: Record<MemoryItemKind, Record<MemoryItemStatus, number>>;
}

export interface MemoryToday {
  new_skills: MemoryItemSummary[];
  pending_proposals: MemoryItemSummary[];
  low_confidence_claims: MemoryItemSummary[];
  recent_corrections: MemoryItemSummary[];
}

export interface MemoryGraphEdge {
  child_id: string;
  parent_id: string;
  role: MemoryParentRole;
  order: number | null;
  created_at: string | null;
}

export interface MemoryGraph {
  root_id: string;
  nodes: MemoryItemSummary[];
  edges: MemoryGraphEdge[];
  depth: number;
  direction: "parents" | "children" | "both";
}

export type MemoryValidityFilter = "all" | "current" | "future" | "expired";

export interface ListMemoryItemsParams {
  kinds?: MemoryItemKind[];
  statuses?: MemoryItemStatus[];
  scope?: string;
  query?: string;
  validity?: MemoryValidityFilter;
  limit?: number;
  offset?: number;
}

function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, String(value));
  }
  const raw = qs.toString();
  return raw ? `?${raw}` : "";
}

export function listMemoryItems(config: AppConfig, params: ListMemoryItemsParams = {}) {
  return apiWithConfig<MemoryItemsPage>(
    config,
    `/admin/memory/items${queryString({
      kinds: params.kinds?.join(","),
      statuses: params.statuses?.join(","),
      scope: params.scope,
      query: params.query,
      validity: params.validity,
      limit: params.limit,
      offset: params.offset,
    })}`,
  );
}

export function getMemoryItem(config: AppConfig, itemId: string) {
  return apiWithConfig<MemoryItemDetail>(config, `/admin/memory/items/${encodeURIComponent(itemId)}`);
}

export function getMemoryStats(config: AppConfig) {
  return apiWithConfig<MemoryStats>(config, "/admin/memory/stats");
}

export function getMemoryToday(config: AppConfig, scope?: string) {
  return apiWithConfig<MemoryToday>(config, `/admin/memory/today${queryString({ scope })}`);
}

export function getMemoryGraph(config: AppConfig, itemId: string, depth = 3, direction: "parents" | "children" | "both" = "both") {
  return apiWithConfig<MemoryGraph>(
    config,
    `/admin/memory/items/${encodeURIComponent(itemId)}/graph${queryString({ depth, direction })}`,
  );
}

export function listMemorySkills(config: AppConfig, includeDisabled = true, scope?: string) {
  return apiWithConfig<{ skills: MemoryItemSummary[] }>(
    config,
    `/admin/memory/skills${queryString({ include_disabled: includeDisabled, scope })}`,
  );
}

export function setMemorySkillEnabled(config: AppConfig, skillId: string, enabled: boolean) {
  return apiWithConfig<{ skill: MemoryItemSummary }>(config, `/admin/memory/skills/${encodeURIComponent(skillId)}/enabled`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}
