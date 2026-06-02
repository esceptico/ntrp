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
// Memory is claims only. Lenses are a separate registry of views (see `Lens`).
export type MemoryStatus = "active" | "superseded" | "archived";
export type MemoryProvenance = "user_authored" | "recorded" | "inferred" | "external";
export type MemoryFeedback = "none" | "confirmed" | "corrected";
export type LensDetailLevel = "gist" | "structured" | "dossier";
export type LensRenderMode = "flat" | "grouped_by_subject";
export type LensProvenance = "user_authored" | "induced";
export type LensStatus = "active" | "archived";

export interface MemorySourceRef {
  kind: string;
  ref: string;
  captured_at: string;
}

export interface MemoryItem {
  id: string;
  content: string;
  canonical_subject: string;
  scope: MemoryScope;
  provenance: MemoryProvenance;
  status: MemoryStatus;
  valid_from: string | null;
  invalid_at: string | null;
  source_refs: MemorySourceRef[];
  corroboration: number;
  last_relevant_at: string | null;
  feedback: MemoryFeedback;
  created_at: string;
  updated_at: string;
}

// A lens DEFINITION — a view over claims, never a memory item, never a graph node.
// The definition lives as an editable markdown file at NTRP_DIR/memory/lenses/<slug>.md:
// `id` is the file slug, `name` is the frontmatter directory, `criterion` is the file
// body (## Belongs + optional ## Profile shape). The JSON shape is unchanged here; the
// server reads/writes the file behind these same fields.
export interface Lens {
  id: string;
  name: string;
  criterion: string;
  entity_type?: string;
  scope: MemoryScope;
  detail_level: LensDetailLevel;
  render_mode: LensRenderMode;
  provenance: LensProvenance;
  status: LensStatus;
  created_at: string;
  updated_at: string;
}

export type MemoryEdgeRole = "evidence" | "supersedes" | "contradicts";
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
  subject?: string;
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
      subject: params.subject,
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
  lens: Lens;
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

export interface DraftLensBody extends ScopeParams {
  name: string;
}
export interface DraftLensResponse {
  markdown: string;
}

export function draftLens(config: AppConfig, body: DraftLensBody) {
  return apiWithConfig<DraftLensResponse>(config, "/admin/memory/lenses/draft", jsonBody(body));
}

// ── 4 — Get a lens page ─────────────────────────────────────────────────────
export interface ProjectedGroup {
  subject: string;
  markdown: string;
  synthesized: boolean;
  blocks: RenderedClaim[];
}
export interface ProjectedPage {
  lens_id: string;
  detail: LensDetailLevel;
  markdown: string;
  blocks: RenderedClaim[];
  synthesized: boolean;
  coverage: CoverageAdvisory | null;
  groups: ProjectedGroup[] | null;
}
export interface LensPageParams {
  detail?: LensDetailLevel;
  refresh?: boolean;
}

// Lens page generation is async (timeout fix): the GET returns either a
// materialized page (clean cache hit) or a generation status (miss/dirty/refresh,
// HTTP 202). The two JSON shapes are disjoint — the status object carries a
// top-level `status`/`stage`; the page never does. Discriminate on that.
export type LensGenStage = "creating" | "scoring" | "synthesizing" | "ready" | "error";
export interface LensGenStatus {
  lens_id: string;
  status: "idle" | LensGenStage;
  stage?: LensGenStage;
  detail?: LensDetailLevel;
  subject: string | null;
  progress: string | null; // "2/5" while synthesizing grouped buckets
  error: string | null;
  updated_at?: string;
}

export type LensPageResult = ProjectedPage | LensGenStatus;

export function isLensGenStatus(r: LensPageResult): r is LensGenStatus {
  return "status" in r;
}

export function getLensPage(config: AppConfig, lensId: string, params: LensPageParams = {}) {
  return apiWithConfig<LensPageResult>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(lensId)}/page${queryString({
      detail: params.detail,
      refresh: params.refresh,
    })}`,
  );
}

export function getLensPageStatus(config: AppConfig, lensId: string) {
  return apiWithConfig<LensGenStatus>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(lensId)}/page/status`,
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

// ── 5a — Whole claim-graph (default view) ────────────────────────────────────
export interface WholeGraph {
  nodes: MemoryItem[];
  edges: MemoryEdge[];
  scope: MemoryScope;
}
export interface WholeGraphParams extends ScopeParams {
  subject?: string;
  roles?: MemoryEdgeRole[];
  limit?: number;
}

export function getWholeGraph(config: AppConfig, params: WholeGraphParams = {}) {
  return apiWithConfig<WholeGraph>(
    config,
    `/admin/memory/graph${queryString({
      scope_kind: params.scope_kind,
      scope_key: params.scope_key,
      subject: params.subject,
      roles: params.roles?.join(","),
      limit: params.limit,
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
  timeout?: number;
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
    { timeout: params.timeout } as RequestInit & { timeout?: number },
  );
}

// ── 7 — Lens page write-back ────────────────────────────────────────────────
export type PageEditKind = "edit" | "reject" | "accept" | "edit_criterion";
export interface PageEditOp {
  kind: PageEditKind;
  claim_id?: string; // required for edit|reject|accept
  new_text?: string; // required for edit (successor) | edit_criterion
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
  name?: string;
  criterion?: string; // optional — synthesized server-side from the name when omitted
  definition_markdown?: string;
  render_mode?: LensRenderMode;
}

export function createLens(config: AppConfig, body: CreateLensBody) {
  return apiWithConfig<{ lens: Lens }>(config, "/admin/memory/lenses", jsonBody(body));
}

export function setLensRenderMode(config: AppConfig, lensId: string, render_mode: LensRenderMode) {
  return apiWithConfig<{ lens: Lens }>(
    config,
    `/admin/memory/lenses/${encodeURIComponent(lensId)}/render_mode`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ render_mode }) },
  );
}

export function editLensCriterion(config: AppConfig, lensId: string, criterion: string) {
  return apiWithConfig<{ lens: Lens }>(config, `/admin/memory/lenses/${encodeURIComponent(lensId)}/criterion`, {
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
  return apiWithConfig<{ children: Lens[] }>(
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
  return apiWithConfig<{ lens: Lens }>(config, "/admin/memory/lenses/merge", jsonBody(body));
}

export function deleteLens(config: AppConfig, lensId: string) {
  return apiWithConfig<{ deleted: boolean }>(config, `/admin/memory/lenses/${encodeURIComponent(lensId)}`, {
    method: "DELETE",
  });
}
