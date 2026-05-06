import type { MemoryEvent } from "../api";

export const MEMORY_MAINTENANCE_REVIEW_ACTION = "memory.maintenance.reviewed";

export interface MemoryMaintenanceReview {
  event: MemoryEvent;
  cleanupCandidateCount: number;
  cleanupCandidateIds: number[];
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

export function latestMemoryMaintenanceReview(events: MemoryEvent[]): MemoryMaintenanceReview | null {
  const event = events.find((candidate) => candidate.action === MEMORY_MAINTENANCE_REVIEW_ACTION);
  if (!event) return null;
  return {
    event,
    cleanupCandidateCount: numberDetail(event.details, "cleanup_candidate_count"),
    cleanupCandidateIds: numberListDetail(event.details, "cleanup_candidate_ids"),
    storageIssues: numberDetail(event.details, "storage_issues"),
    provenanceIssues: numberDetail(event.details, "provenance_issues"),
    relationIssues: numberDetail(event.details, "relation_issues"),
  };
}
