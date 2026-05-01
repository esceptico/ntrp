import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface Fact {
  id: number;
  text: string;
  source_type: string;
  source_ref: string | null;
  created_at: string;
  happened_at: string | null;
  last_accessed_at: string;
  access_count: number;
  consolidated_at: string | null;
  archived_at: string | null;
  kind: FactKind;
  salience: number;
  confidence: number;
  expires_at: string | null;
  pinned_at: string | null;
  superseded_by_fact_id: number | null;
}

export type FactKind =
  | "identity"
  | "preference"
  | "relationship"
  | "decision"
  | "project"
  | "event"
  | "artifact"
  | "procedure"
  | "constraint"
  | "temporary"
  | "note";

export type SourceType = "chat" | "explicit";
export type FactStatus = "active" | "archived" | "superseded" | "expired" | "temporary" | "pinned" | "all";
export type FactAccessed = "never" | "used";

export interface FactFilters {
  kind?: FactKind;
  sourceType?: SourceType;
  status?: FactStatus;
  accessed?: FactAccessed;
  entity?: string;
}

export interface FactDetails {
  fact: Fact;
  entities: Array<{ name: string; entity_id: number }>;
  linked_facts: Array<{
    id: number;
    text: string;
    link_type: string;
    weight: number;
  }>;
}

export interface FactMetadataUpdate {
  kind?: FactKind;
  salience?: number;
  confidence?: number;
  expires_at?: string | null;
  pinned?: boolean;
  superseded_by_fact_id?: number | null;
}

export interface FactMetadataSuggestion {
  kind: FactKind;
  salience: number;
  confidence: number;
  expires_at: string | null;
  reason: string;
}

export interface FactKindReviewSuggestion {
  fact: Fact;
  suggestion: FactMetadataSuggestion;
}

export interface Stats {
  fact_count: number;
  observation_count: number;
  dream_count: number;
}

export interface Observation {
  id: number;
  summary: string;
  evidence_count: number;
  access_count: number;
  created_at: string;
  updated_at: string;
  last_accessed_at: string;
  archived_at: string | null;
  created_by: string;
  policy_version: string;
}

export type ObservationStatus = "active" | "archived" | "all";
export type ObservationAccessed = "never" | "used";

export interface ObservationFilters {
  status?: ObservationStatus;
  accessed?: ObservationAccessed;
  minSources?: number;
  maxSources?: number;
}

export interface ObservationDetails {
  observation: Observation;
  supporting_facts: Fact[];
}

export interface Dream {
  id: number;
  bridge: string;
  insight: string;
  created_at: string;
}

export interface DreamDetails {
  dream: Dream;
  source_facts: Array<{ id: number; text: string }>;
}

export interface MemoryPruneCriteria {
  older_than_days: number;
  max_sources: number;
  limit: number;
  cutoff: string;
}

export interface MemoryPruneSummary {
  total: number;
  over_1000_chars: number;
  empty_sources: number;
}

export interface MemoryPruneCandidate {
  id: number;
  summary: string;
  created_at: string;
  updated_at: string;
  access_count: number;
  evidence_count: number;
  chars: number;
  reason: string;
}

export interface MemoryPruneDryRun {
  criteria: MemoryPruneCriteria;
  summary: MemoryPruneSummary;
  candidates: MemoryPruneCandidate[];
}

export interface MemoryPruneApplyResult {
  status: "archived" | "unchanged";
  archived: number;
  archived_ids: number[];
  skipped_ids: number[];
  candidates: MemoryPruneCandidate[];
}

export interface MemoryEvent {
  id: number;
  created_at: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: number | null;
  source_type: string | null;
  source_ref: string | null;
  reason: string | null;
  policy_version: string;
  details: Record<string, unknown>;
}

function factQuery(limit: number, filters?: FactFilters): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters?.kind) params.set("kind", filters.kind);
  if (filters?.sourceType) params.set("source_type", filters.sourceType);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.accessed) params.set("accessed", filters.accessed);
  if (filters?.entity?.trim()) params.set("entity", filters.entity.trim());
  return params.toString();
}

function observationQuery(limit: number, filters?: ObservationFilters): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters?.status) params.set("status", filters.status);
  if (filters?.accessed) params.set("accessed", filters.accessed);
  if (filters?.minSources !== undefined) params.set("min_sources", String(filters.minSources));
  if (filters?.maxSources !== undefined) params.set("max_sources", String(filters.maxSources));
  return params.toString();
}

export async function getFacts(config: Config, limit = 50, filters?: FactFilters): Promise<{
  facts: Fact[];
  total: number;
}> {
  return api.get<{ facts: Fact[]; total: number }>(`${config.serverUrl}/facts?${factQuery(limit, filters)}`);
}

export async function getFactDetails(config: Config, factId: number, signal?: AbortSignal): Promise<FactDetails> {
  return api.get<FactDetails>(`${config.serverUrl}/facts/${factId}`, { signal });
}

export async function updateFact(
  config: Config,
  factId: number,
  text: string
): Promise<{ fact: Fact; entity_refs: Array<{ name: string; entity_id: number }> }> {
  return api.patch(`${config.serverUrl}/facts/${factId}`, { text });
}

export async function updateFactMetadata(
  config: Config,
  factId: number,
  update: FactMetadataUpdate
): Promise<{ fact: Fact }> {
  return api.patch<{ fact: Fact }>(`${config.serverUrl}/facts/${factId}/metadata`, update);
}

export async function suggestFactMetadata(
  config: Config,
  factId: number
): Promise<{ suggestions: FactKindReviewSuggestion[]; total_reviewable: number }> {
  return api.post<{ suggestions: FactKindReviewSuggestion[]; total_reviewable: number }>(
    `${config.serverUrl}/memory/facts/kind-review/suggestions`,
    { fact_ids: [factId] }
  );
}

export async function deleteFact(
  config: Config,
  factId: number
): Promise<{
  status: string;
  fact_id: number;
  cascaded: { entity_refs: number };
}> {
  return api.delete(`${config.serverUrl}/facts/${factId}`);
}

export async function getStats(config: Config): Promise<Stats> {
  return api.get<Stats>(`${config.serverUrl}/stats`);
}

export async function getMemoryProfile(config: Config, limit = 20): Promise<{ facts: Fact[] }> {
  return api.get<{ facts: Fact[] }>(`${config.serverUrl}/memory/profile?limit=${limit}`);
}

export async function getObservations(config: Config, limit = 50, filters?: ObservationFilters): Promise<{
  observations: Observation[];
  total: number;
}> {
  return api.get<{ observations: Observation[]; total: number }>(
    `${config.serverUrl}/observations?${observationQuery(limit, filters)}`
  );
}

export async function getObservationDetails(config: Config, observationId: number, signal?: AbortSignal): Promise<ObservationDetails> {
  return api.get<ObservationDetails>(`${config.serverUrl}/observations/${observationId}`, { signal });
}

export async function updateObservation(
  config: Config,
  observationId: number,
  summary: string
): Promise<{
  observation: Observation;
}> {
  return api.patch<{ observation: Observation }>(`${config.serverUrl}/observations/${observationId}`, { summary });
}

export async function deleteObservation(
  config: Config,
  observationId: number
): Promise<{ status: string }> {
  return api.delete(`${config.serverUrl}/observations/${observationId}`);
}

export async function getDreams(config: Config, limit = 50): Promise<{
  dreams: Dream[];
}> {
  return api.get<{ dreams: Dream[] }>(`${config.serverUrl}/dreams?limit=${limit}`);
}

export async function getDreamDetails(config: Config, dreamId: number, signal?: AbortSignal): Promise<DreamDetails> {
  return api.get<DreamDetails>(`${config.serverUrl}/dreams/${dreamId}`, { signal });
}

export async function deleteDream(config: Config, dreamId: number): Promise<{ status: string }> {
  return api.delete<{ status: string }>(`${config.serverUrl}/dreams/${dreamId}`);
}

export async function getMemoryPruneDryRun(config: Config): Promise<MemoryPruneDryRun> {
  return api.post<MemoryPruneDryRun>(`${config.serverUrl}/memory/prune/dry-run`, {});
}

export async function applyMemoryPrune(
  config: Config,
  observationIds: number[],
  criteria: Pick<MemoryPruneCriteria, "older_than_days" | "max_sources">,
  allMatching = false
): Promise<MemoryPruneApplyResult> {
  return api.post<MemoryPruneApplyResult>(`${config.serverUrl}/memory/prune/apply`, {
    observation_ids: observationIds,
    all_matching: allMatching,
    older_than_days: criteria.older_than_days,
    max_sources: criteria.max_sources,
  });
}

export async function getMemoryEvents(config: Config, limit = 100): Promise<{ events: MemoryEvent[] }> {
  return api.get<{ events: MemoryEvent[] }>(`${config.serverUrl}/memory/events?limit=${limit}`);
}

export async function purgeMemory(config: Config): Promise<{ status: string; deleted: Record<string, number> }> {
  return api.post<{ status: string; deleted: Record<string, number> }>(`${config.serverUrl}/memory/clear`);
}
