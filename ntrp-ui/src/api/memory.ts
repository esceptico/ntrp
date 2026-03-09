import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface Fact {
  id: number;
  text: string;
  source_type: string;
  created_at: string;
}

export interface FactDetails {
  fact: {
    id: number;
    text: string;
    source_type: string;
    source_ref: string | null;
    created_at: string;
    access_count: number;
  };
  entities: Array<{ name: string; entity_id: number }>;
  linked_facts: Array<{
    id: number;
    text: string;
    link_type: string;
    weight: number;
  }>;
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
}

export interface ObservationDetails {
  observation: Observation;
  supporting_facts: Array<{ id: number; text: string }>;
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

export async function getFacts(config: Config, limit = 50): Promise<{
  facts: Fact[];
  total: number;
}> {
  return api.get<{ facts: Fact[]; total: number }>(`${config.serverUrl}/facts?limit=${limit}`);
}

export async function getFactDetails(config: Config, factId: number, signal?: AbortSignal): Promise<FactDetails> {
  return api.get<FactDetails>(`${config.serverUrl}/facts/${factId}`, { signal });
}

export async function updateFact(
  config: Config,
  factId: number,
  text: string
): Promise<{
  fact: {
    id: number;
    text: string;
    source_type: string;
    source_ref: string | null;
    created_at: string;
    access_count: number;
  };
  entity_refs: Array<{ name: string; entity_id: number }>;
}> {
  return api.patch(`${config.serverUrl}/facts/${factId}`, { text });
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

export async function getObservations(config: Config, limit = 50): Promise<{
  observations: Observation[];
}> {
  return api.get<{ observations: Observation[] }>(`${config.serverUrl}/observations?limit=${limit}`);
}

export async function getObservationDetails(config: Config, observationId: number, signal?: AbortSignal): Promise<ObservationDetails> {
  return api.get<ObservationDetails>(`${config.serverUrl}/observations/${observationId}`, { signal });
}

export async function updateObservation(
  config: Config,
  observationId: number,
  summary: string
): Promise<{
  id: number;
  summary: string;
  evidence_count: number;
  access_count: number;
  created_at: string;
  updated_at: string;
}> {
  return api.patch(`${config.serverUrl}/observations/${observationId}`, { summary });
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

export async function purgeMemory(config: Config): Promise<{ status: string; deleted: Record<string, number> }> {
  return api.post<{ status: string; deleted: Record<string, number> }>(`${config.serverUrl}/memory/clear`);
}
