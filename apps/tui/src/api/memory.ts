import type { Config } from "../types.js";
import { api } from "./fetch.js";

export type MemoryItemKind = "episode" | "observation" | "claim" | "skill" | "proposal" | "artifact_ref";
export type MemoryItemStatus = "active" | "superseded" | "archived";

export interface MemoryItem {
  id: string;
  kind: MemoryItemKind;
  content: string;
  provenance: string;
  source_refs: Array<Record<string, unknown>>;
  confidence: number;
  status: MemoryItemStatus;
  valid_from: string | null;
  invalid_at: string | null;
  scope: string;
  tags: string[];
  artifact_ref: string | null;
  usage: Record<string, unknown>;
  feedback: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  has_embedding: boolean;
}

export interface MemoryItemsResponse {
  items: MemoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface MemoryStats {
  counts: Record<MemoryItemKind, Record<MemoryItemStatus, number>>;
}

export interface Stats {
  fact_count: number;
  observation_count: number;
}

export async function listMemoryItems(
  config: Config,
  filters: {
    kinds?: MemoryItemKind[];
    statuses?: MemoryItemStatus[];
    scope?: string;
    query?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<MemoryItemsResponse> {
  const params = new URLSearchParams();
  if (filters.kinds?.length) params.set("kinds", filters.kinds.join(","));
  if (filters.statuses?.length) params.set("statuses", filters.statuses.join(","));
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.query) params.set("query", filters.query);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return api.get<MemoryItemsResponse>(`${config.serverUrl}/admin/memory/items${suffix}`);
}

export async function getMemoryStats(config: Config): Promise<MemoryStats> {
  return api.get<MemoryStats>(`${config.serverUrl}/admin/memory/stats`);
}

export async function getStats(config: Config): Promise<Stats> {
  const stats = await getMemoryStats(config);
  return {
    fact_count: stats.counts.claim?.active ?? 0,
    observation_count: stats.counts.observation?.active ?? 0,
  };
}
