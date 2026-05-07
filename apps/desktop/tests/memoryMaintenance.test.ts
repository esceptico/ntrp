import { expect, test } from "bun:test";
import type { MemoryEvent } from "../src/api";
import { latestMemoryMaintenanceReview } from "../src/lib/memoryMaintenance.js";

function event(patch: Partial<MemoryEvent>): MemoryEvent {
  return {
    id: 1,
    created_at: "2026-05-07T00:00:00Z",
    actor: "automation",
    action: "memory.maintenance.reviewed",
    target_type: "memory",
    target_id: null,
    source_type: null,
    source_ref: null,
    reason: null,
    policy_version: "memory.maintenance.review.v1",
    details: {},
    ...patch,
  };
}

test("extracts latest memory maintenance review details", () => {
  const review = latestMemoryMaintenanceReview([
    event({
      details: {
        cleanup_candidate_count: 3,
        cleanup_candidate_ids: [10, 11, "skip"],
        duplicate_fact_candidate_count: 2,
        duplicate_fact_candidates: [
          { ids: [1, 2], score: 0.9921, left: "User likes concise reports", right: "User prefers concise reports" },
          { ids: [3, "bad"], score: 0.5, left: "skip", right: "skip" },
        ],
        duplicate_observation_candidate_count: 4,
        duplicate_observation_candidates: [
          { ids: [20, 21], score: 1, left: "Pattern one", right: "Pattern two" },
        ],
        storage_issues: 1,
        provenance_issues: 2,
        relation_issues: 0,
      },
    }),
  ]);

  expect(review?.cleanupCandidateCount).toBe(3);
  expect(review?.cleanupCandidateIds).toEqual([10, 11]);
  expect(review?.duplicateFactCandidateCount).toBe(2);
  expect(review?.duplicateObservationCandidateCount).toBe(4);
  expect(review?.duplicateFactCandidates).toEqual([
    { ids: [1, 2], score: 0.9921, left: "User likes concise reports", right: "User prefers concise reports" },
  ]);
  expect(review?.duplicateObservationCandidates).toEqual([
    { ids: [20, 21], score: 1, left: "Pattern one", right: "Pattern two" },
  ]);
  expect(review?.storageIssues).toBe(1);
  expect(review?.provenanceIssues).toBe(2);
});

test("ignores unrelated memory events", () => {
  expect(latestMemoryMaintenanceReview([event({ action: "fact.created" })])).toBeNull();
});
