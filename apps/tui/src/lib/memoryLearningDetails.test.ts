import { expect, test } from "bun:test";
import { cleanLearningText, learningDetailRows, summarizeLearningEvidence } from "./memoryLearningDetails.js";

test("summarizes evidence ids without exposing raw ids", () => {
  expect(summarizeLearningEvidence(["observation:50", "observation:82", "fact:12"])).toBe("2 patterns, 1 fact");
});

test("renders learning details as review metadata rows", () => {
  const rows = learningDetailRows({
    criteria: { older_than_days: 30, max_sources: 5, limit: 100 },
    summary: { total: 1058 },
    observation_ids: [50, 82, 89],
    outcome_counts: { corrected: 2, failed: 1 },
    source_event_id: 123,
  });

  expect(rows).toContainEqual({ label: "cleanup rule", value: "30d old, <= 5 facts, review 100" });
  expect(rows).toContainEqual({ label: "source summary", value: "1058 source rows" });
  expect(rows).toContainEqual({ label: "matched patterns", value: "3" });
  expect(rows).toContainEqual({ label: "outcomes", value: "corrected: 2, failed: 1" });
  expect(rows.some((row) => row.value.includes("50"))).toBe(false);
});

test("cleans direct evidence text from model-facing rationale", () => {
  expect(cleanLearningText("Review this; direct evidence: observation:50, observation:82.")).toBe(
    "Review this; direct evidence is loaded."
  );
});
