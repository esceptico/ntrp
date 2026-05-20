import type { Config } from "../types.js";
import { api } from "./fetch.js";

export type KnowledgeObjectType =
  | "source"
  | "evidence_ref"
  | "episode"
  | "fact"
  | "pattern"
  | "lesson"
  | "procedure"
  | "procedure_candidate"
  | "artifact"
  | "action_candidate"
  | "sink_receipt"
  | "outcome_feedback";

export type KnowledgeObjectStatus = "draft" | "active" | "approved" | "rejected" | "archived" | "superseded";

export interface KnowledgeObject {
  id: number;
  object_type: KnowledgeObjectType;
  title: string;
  text: string;
  status: KnowledgeObjectStatus;
  scope: string | null;
  activation: string;
  proactiveness_level: string;
  score: number;
  source_ids: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
}

export interface KnowledgeSurface {
  name: string;
  object_type: KnowledgeObjectType;
  count: number;
  description: string;
}

export interface KnowledgeSummary {
  surfaces: KnowledgeSurface[];
  next_actions: Array<{
    title: string;
    detail: string;
    activation: string;
    proactiveness_level: string;
  }>;
  policy_version: string;
}

export interface Stats {
  fact_count: number;
  observation_count: number;
}

export interface ActivationSignal {
  name: string;
  value: number | string | boolean | null;
  reason: string;
}

export interface ActivationCandidate {
  object_type: KnowledgeObjectType;
  object_id: string;
  title: string;
  text: string;
  score: number;
  reasons: string[];
  signals: ActivationSignal[];
  source_ids: string[];
  activation: string;
  proactiveness_level: string;
}

export interface ActivationBundle {
  query: string;
  scope: string | null;
  task: string | null;
  budget_chars: number;
  used_chars: number;
  candidates: ActivationCandidate[];
  omitted: ActivationCandidate[];
  policy_version: string;
  prompt_context: string | null;
}

export async function getKnowledgeSummary(config: Config): Promise<KnowledgeSummary> {
  return api.get<KnowledgeSummary>(`${config.serverUrl}/knowledge/summary`);
}

export async function getStats(config: Config): Promise<Stats> {
  const summary = await getKnowledgeSummary(config);
  const count = (type: KnowledgeObjectType) => summary.surfaces.find((surface) => surface.object_type === type)?.count ?? 0;
  return {
    fact_count: count("fact"),
    observation_count: count("pattern"),
  };
}

export async function listKnowledgeObjects(
  config: Config,
  filters: { object_type?: KnowledgeObjectType; status?: KnowledgeObjectStatus; limit?: number; offset?: number } = {},
): Promise<{ objects: KnowledgeObject[] }> {
  const params = new URLSearchParams();
  if (filters.object_type) params.set("object_type", filters.object_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return api.get<{ objects: KnowledgeObject[] }>(`${config.serverUrl}/knowledge/objects${suffix}`);
}

export async function inspectKnowledgeActivation(
  config: Config,
  query: string,
  limit = 5,
): Promise<ActivationBundle> {
  return api.post<ActivationBundle>(`${config.serverUrl}/knowledge/activation/inspect`, { query, limit });
}
