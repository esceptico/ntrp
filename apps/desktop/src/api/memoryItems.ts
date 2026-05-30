import type { AppConfig } from "../api";
import { apiWithConfig } from "../api";

export type MemoryItemKind =
  | "episode"
  | "observation"
  | "claim"
  | "skill"
  | "proposal"
  | "artifact_ref"
  | "entity"
  | "directory";
export type MemoryItemStatus = "active" | "superseded" | "archived";
export type MemoryParentRole = "step" | "evidence" | "contradicts" | "supersedes" | "similar_to" | "member_of";

export interface MemoryItemSummary {
  id: string;
  kind: MemoryItemKind;
  content: string;
  title: string | null;
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

export interface MemoryGlobalGraph {
  nodes: MemoryItemSummary[];
  edges: MemoryGraphEdge[];
  include_unlinked: boolean;
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

export interface UpdateMemoryItemParams {
  content?: string;
  title?: string | null;
  confidence?: number;
  tags?: string[];
  scope?: string;
  status?: MemoryItemStatus;
  invalid_at?: string | null;
}

export function updateMemoryItem(config: AppConfig, itemId: string, params: UpdateMemoryItemParams) {
  return apiWithConfig<{ item: MemoryItemSummary }>(config, `/admin/memory/items/${encodeURIComponent(itemId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export function deleteMemoryItem(config: AppConfig, itemId: string) {
  return apiWithConfig<{ deleted: boolean }>(config, `/admin/memory/items/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
  });
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

export function getMemoryGlobalGraph(config: AppConfig, includeUnlinked = false, scope?: string) {
  return apiWithConfig<MemoryGlobalGraph>(
    config,
    `/admin/memory/graph${queryString({ include_unlinked: includeUnlinked, scope })}`,
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

export function approveMemoryProposal(config: AppConfig, proposalId: string, slug?: string) {
  return apiWithConfig<{ skill_id: string; skill_path: string }>(
    config,
    `/admin/memory/proposals/${encodeURIComponent(proposalId)}/approve${queryString({ slug })}`,
    { method: "POST" },
  );
}

export function rejectMemoryProposal(config: AppConfig, proposalId: string, reason?: string) {
  return apiWithConfig<{ rejected_at: string }>(
    config,
    `/admin/memory/proposals/${encodeURIComponent(proposalId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
}

export interface MemoryDirectory {
  directory: MemoryItemSummary;
  slug: string | null;
  entity_type: string | null;
  markdown: string | null;
  members: MemoryItemSummary[];
}

export interface MemoryLens {
  slug: string;
  directory: string;
  entity_type: string;
  path: string;
}

export interface LensPassRunResult {
  lenses: number;
  directories: number;
  entities_written: number;
  edges_written: number;
  elapsed_ms: number;
}

export function listMemoryDirectories(config: AppConfig, scope?: string) {
  return apiWithConfig<{ directories: MemoryDirectory[] }>(
    config,
    `/admin/memory/directories${queryString({ scope })}`,
  );
}

export function listMemoryLenses(config: AppConfig) {
  return apiWithConfig<{ lenses: MemoryLens[] }>(config, "/admin/memory/lenses");
}

export function runLensPass(config: AppConfig, scope = "user") {
  return apiWithConfig<LensPassRunResult>(config, `/admin/memory/lenses/run${queryString({ scope })}`, {
    method: "POST",
  });
}

export function updateLens(config: AppConfig, slug: string, markdown: string, scope = "user") {
  return apiWithConfig<{ slug: string; run: LensPassRunResult }>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(slug)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown, scope }),
    },
  );
}

export function deleteLens(config: AppConfig, slug: string) {
  return apiWithConfig<{ slug: string; file_removed: boolean; directory_removed: boolean; entities_removed: number }>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(slug)}`,
    { method: "DELETE" },
  );
}

export interface LensProposal {
  proposal_id: string;
  slug: string;
  directory: string;
  entity_type: string;
  markdown: string;
  created_at?: string | null;
}

export function generateLens(config: AppConfig, query: string, scope = "user") {
  return apiWithConfig<Omit<LensProposal, "created_at">>(config, "/admin/memory/lenses/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, scope }),
  });
}

export function listLensProposals(config: AppConfig, scope?: string) {
  return apiWithConfig<{ proposals: LensProposal[] }>(
    config,
    `/admin/memory/lenses/proposals${queryString({ scope })}`,
  );
}

export function approveLensProposal(config: AppConfig, proposalId: string, slug?: string, scope = "user") {
  return apiWithConfig<{ slug: string; directory: string; run: LensPassRunResult }>(
    config,
    `/admin/memory/lenses/proposals/${encodeURIComponent(proposalId)}/approve${queryString({ slug, scope })}`,
    { method: "POST" },
  );
}

export function rejectLensProposal(config: AppConfig, proposalId: string) {
  return apiWithConfig<{ rejected: boolean }>(
    config,
    `/admin/memory/lenses/proposals/${encodeURIComponent(proposalId)}/reject`,
    { method: "POST" },
  );
}

export function undoMemoryContradiction(config: AppConfig, childId: string, parentId: string) {
  return apiWithConfig<{ already_undone: boolean; restored: boolean; cross_scope: boolean }>(
    config,
    `/admin/memory/contradictions/${encodeURIComponent(childId)}/${encodeURIComponent(parentId)}/undo`,
    { method: "POST" },
  );
}
