import type { AppConfig } from "../api";
import { apiWithConfig } from "../api";

// ── Scope ─────────────────────────────────────────────────────────────────
export type ScopeKind = "user" | "project" | "session";
export interface ScopeParams {
  scope_kind?: ScopeKind;
  scope_key?: string;
}
export interface MemoryScope {
  kind: ScopeKind;
  key: string | null;
}

// ── Shared value objects ────────────────────────────────────────────────────
export type MemoryKind = "claim" | "lens";
export type MemoryStatus = "active" | "superseded" | "archived";
export type MemoryProvenance = "user_authored" | "recorded" | "inferred" | "external" | "induced";
export type MemoryFeedback = "none" | "confirmed" | "corrected";
export type LensDetailLevel = "gist" | "structured" | "dossier";

export interface MemorySourceRef {
  kind: string;
  ref: string;
  captured_at: string;
}

export interface MemoryItem {
  id: string;
  kind: MemoryKind;
  content: string;
  scope: MemoryScope;
  provenance: MemoryProvenance;
  status: MemoryStatus;
  valid_from: string | null;
  invalid_at: string | null;
  source_refs: MemorySourceRef[];
  corroboration: number;
  last_relevant_at: string | null;
  feedback: MemoryFeedback;
  lens_name: string | null;
  lens_criterion: string | null;
  lens_kind: string | null;
  lens_detail_level: LensDetailLevel | null;
  lens_exclusive: boolean;
  created_at: string;
  updated_at: string;
}

export type MemoryEdgeRole = "evidence" | "supersedes" | "contradicts" | "member_of";
export interface MemoryEdge {
  child_id: string;
  parent_id: string;
  role: MemoryEdgeRole;
  position: number;
  created_at: string;
}

export interface CoverageAdvisory {
  lens_id: string;
  scope_pool: number;
  member_count: number;
  ratio: number;
  generic: boolean;
  suggestion: string;
}

export interface RenderedClaim {
  claim_id: string;
  content: string;
  provenance: MemoryProvenance;
  corroboration: number;
  feedback: MemoryFeedback;
  source_refs: MemorySourceRef[];
}

// ── Query encoding ──────────────────────────────────────────────────────────
function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, String(value));
  }
  const raw = qs.toString();
  return raw ? `?${raw}` : "";
}

function jsonBody(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

// ── 1 — List claims/lenses ──────────────────────────────────────────────────
export interface MemoryItemsResponse {
  items: MemoryItem[];
  limit: number;
}
export interface ListMemoryItemsParams extends ScopeParams {
  kind?: MemoryKind;
  status?: MemoryStatus | ""; // "" => all statuses
  valid_at?: string;
  limit?: number;
}

export function listMemoryItems(config: AppConfig, params: ListMemoryItemsParams = {}) {
  return apiWithConfig<MemoryItemsResponse>(
    config,
    `/admin/memory/items${queryString({
      scope_kind: params.scope_kind,
      scope_key: params.scope_key,
      kind: params.kind,
      status: params.status,
      valid_at: params.valid_at,
      limit: params.limit,
    })}`,
  );
}

// ── 2 — Get one item + provenance edges ─────────────────────────────────────
export interface MemoryItemDetail {
  item: MemoryItem;
  parents: MemoryEdge[]; // direction=from: item -> parent
  children: MemoryEdge[]; // direction=to:   child -> item
}

export function getMemoryItem(config: AppConfig, itemId: string) {
  return apiWithConfig<MemoryItemDetail>(config, `/admin/memory/items/${encodeURIComponent(itemId)}`);
}

// ── 3 — List lenses (with coverage advisory) ────────────────────────────────
export interface LensWithCoverage {
  lens: MemoryItem;
  coverage: CoverageAdvisory;
}
export interface LensesResponse {
  lenses: LensWithCoverage[];
}

export function listMemoryLenses(config: AppConfig, params: ScopeParams = {}) {
  return apiWithConfig<LensesResponse>(
    config,
    `/admin/memory/lenses${queryString({ scope_kind: params.scope_kind, scope_key: params.scope_key })}`,
  );
}

// ── 4 — Get a lens page ─────────────────────────────────────────────────────
export interface ProjectedPage {
  lens_id: string;
  detail: LensDetailLevel;
  markdown: string;
  blocks: RenderedClaim[];
  synthesized: boolean;
  coverage: CoverageAdvisory | null;
}
export interface LensPageParams {
  detail?: LensDetailLevel;
  refresh?: boolean;
}

export function getLensPage(config: AppConfig, lensId: string, params: LensPageParams = {}) {
  return apiWithConfig<ProjectedPage>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(lensId)}/page${queryString({
      detail: params.detail,
      refresh: params.refresh,
    })}`,
  );
}

// ── 5 — Provenance graph ────────────────────────────────────────────────────
export interface MemoryGraph {
  root_id: string;
  nodes: MemoryItem[];
  edges: MemoryEdge[];
  depth: number;
  direction: "parents" | "children" | "both";
}
export interface MemoryGraphParams {
  direction?: "parents" | "children" | "both";
  depth?: number;
  roles?: MemoryEdgeRole[];
}

export function getMemoryGraph(config: AppConfig, itemId: string, params: MemoryGraphParams = {}) {
  return apiWithConfig<MemoryGraph>(
    config,
    `/admin/memory/items/${encodeURIComponent(itemId)}/graph${queryString({
      direction: params.direction,
      depth: params.depth,
      roles: params.roles?.join(","),
    })}`,
  );
}

// ── 6 — Search ──────────────────────────────────────────────────────────────
export interface MemorySearchFts {
  mode: "fts";
  items: MemoryItem[];
  degraded: boolean;
}
export interface RankedItem {
  item: MemoryItem;
  order_score: number;
  rrf: number;
  freshness: number;
  provenance_ord: number;
  corroboration: number;
}
export interface MemorySearchRetrieve {
  mode: "retrieve";
  rendered: string;
  items: RankedItem[];
  degraded: boolean;
  diagnostics: Record<string, unknown>;
}
export type MemorySearchResponse = MemorySearchFts | MemorySearchRetrieve;
export interface MemorySearchParams extends ScopeParams {
  q: string;
  limit?: number;
  include_inactive?: boolean;
  mode?: "fts" | "retrieve";
}

export function searchMemory(config: AppConfig, params: MemorySearchParams) {
  return apiWithConfig<MemorySearchResponse>(
    config,
    `/admin/memory/search${queryString({
      q: params.q,
      scope_kind: params.scope_kind,
      scope_key: params.scope_key,
      limit: params.limit,
      include_inactive: params.include_inactive,
      mode: params.mode,
    })}`,
  );
}

// ── 7 — Lens page write-back ────────────────────────────────────────────────
export type PageEditKind = "edit" | "reject" | "accept" | "add" | "edit_criterion";
export interface PageEditOp {
  kind: PageEditKind;
  claim_id?: string; // required for edit|reject|accept
  new_text?: string; // required for edit (successor) | add | edit_criterion
}
export interface WriteBackApplied {
  kind: PageEditKind;
  id: string;
}
export interface WriteBackRejected {
  op: PageEditOp;
  reason: string;
}
export interface WriteBackResult {
  applied: WriteBackApplied[];
  rejected: WriteBackRejected[];
  rederive_triggered: boolean;
}

export function writebackLens(config: AppConfig, lensId: string, ops: PageEditOp[]) {
  return apiWithConfig<WriteBackResult>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(lensId)}/writeback`,
    jsonBody({ ops }),
  );
}

// ── 8 — Lens lifecycle (admin) ──────────────────────────────────────────────
export interface CreateLensBody extends ScopeParams {
  name: string;
  criterion: string;
  lens_kind?: string; // default "topic"
}

export function createLens(config: AppConfig, body: CreateLensBody) {
  return apiWithConfig<{ lens: MemoryItem }>(config, "/admin/memory/lenses", jsonBody(body));
}

export function editLensCriterion(config: AppConfig, lensId: string, criterion: string) {
  return apiWithConfig<{ lens: MemoryItem }>(config, `/admin/memory/lenses/${encodeURIComponent(lensId)}/criterion`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ criterion }),
  });
}

export interface SplitChild {
  name: string;
  criterion: string;
}
export interface SplitLensBody {
  into: SplitChild[];
  archive_parent?: boolean; // default true
}

export function splitLens(config: AppConfig, lensId: string, body: SplitLensBody) {
  return apiWithConfig<{ children: MemoryItem[] }>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(lensId)}/split`,
    jsonBody(body),
  );
}

export interface MergeLensBody extends ScopeParams {
  lens_ids: string[];
  name: string;
  criterion: string;
}

export function mergeLenses(config: AppConfig, body: MergeLensBody) {
  return apiWithConfig<{ lens: MemoryItem }>(config, "/admin/memory/lenses/merge", jsonBody(body));
}

export function deleteLens(config: AppConfig, lensId: string) {
  return apiWithConfig<{ archived: boolean }>(config, `/admin/memory/lenses/${encodeURIComponent(lensId)}`, {
    method: "DELETE",
  });
}
