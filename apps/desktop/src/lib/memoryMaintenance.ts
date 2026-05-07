import type { MemoryEvent } from "../api";

export const MEMORY_MAINTENANCE_REVIEW_ACTION = "memory.maintenance.reviewed";

export interface DuplicateMemoryCandidate {
  ids: [number, number];
  score: number;
  left: string;
  right: string;
}

export interface MemoryMaintenanceReview {
  event: MemoryEvent;
  cleanupCandidateCount: number;
  cleanupCandidateIds: number[];
  duplicateFactCandidateCount: number;
  duplicateFactCandidates: DuplicateMemoryCandidate[];
  duplicateObservationCandidateCount: number;
  duplicateObservationCandidates: DuplicateMemoryCandidate[];
  storageIssues: number;
  provenanceIssues: number;
  relationIssues: number;
}

function numberDetail(details: Record<string, unknown>, key: string): number {
  const value = details[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function numberListDetail(details: Record<string, unknown>, key: string): number[] {
  const value = details[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is number => typeof item === "number" && Number.isFinite(item));
}

function duplicateCandidateListDetail(details: Record<string, unknown>, key: string): DuplicateMemoryCandidate[] {
  const value = details[key];
  if (!Array.isArray(value)) return [];
  const candidates: DuplicateMemoryCandidate[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const ids = record.ids;
    if (!Array.isArray(ids) || ids.length < 2) continue;
    const leftId = ids[0];
    const rightId = ids[1];
    if (typeof leftId !== "number" || !Number.isFinite(leftId)) continue;
    if (typeof rightId !== "number" || !Number.isFinite(rightId)) continue;
    if (typeof record.left !== "string" || typeof record.right !== "string") continue;
    const score = typeof record.score === "number" && Number.isFinite(record.score) ? record.score : 0;
    candidates.push({
      ids: [leftId, rightId],
      score,
      left: record.left,
      right: record.right,
    });
  }
  return candidates;
}

export function latestMemoryMaintenanceReview(events: MemoryEvent[]): MemoryMaintenanceReview | null {
  const event = events.find((candidate) => candidate.action === MEMORY_MAINTENANCE_REVIEW_ACTION);
  if (!event) return null;
  return {
    event,
    cleanupCandidateCount: numberDetail(event.details, "cleanup_candidate_count"),
    cleanupCandidateIds: numberListDetail(event.details, "cleanup_candidate_ids"),
    duplicateFactCandidateCount: numberDetail(event.details, "duplicate_fact_candidate_count"),
    duplicateFactCandidates: duplicateCandidateListDetail(event.details, "duplicate_fact_candidates"),
    duplicateObservationCandidateCount: numberDetail(event.details, "duplicate_observation_candidate_count"),
    duplicateObservationCandidates: duplicateCandidateListDetail(event.details, "duplicate_observation_candidates"),
    storageIssues: numberDetail(event.details, "storage_issues"),
    provenanceIssues: numberDetail(event.details, "provenance_issues"),
    relationIssues: numberDetail(event.details, "relation_issues"),
  };
}
