import { expect, test } from "bun:test";
import { learningCandidateEffect, learningChangeLabel } from "./memoryLearning.js";

test("labels memory learning change types for humans", () => {
  expect(learningChangeLabel("skill_note")).toBe("skill note");
  expect(learningChangeLabel("memory_feedback")).toBe("memory feedback");
  expect(learningChangeLabel("custom_rule_name")).toBe("custom rule name");
});

test("describes approved learning effects", () => {
  expect(learningCandidateEffect("skill_note", "approved")).toBe("active in future prompts");
  expect(learningCandidateEffect("prompt_note", "approved")).toBe("active in future prompts");
  expect(learningCandidateEffect("memory_feedback", "approved")).toBe("approved for manual follow-up");
  expect(learningCandidateEffect("skill_note", "proposed")).toBeNull();
});
