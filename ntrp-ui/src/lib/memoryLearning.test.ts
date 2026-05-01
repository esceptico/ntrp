import { expect, test } from "bun:test";
import { learningApprovalEffect, learningCandidateEffect, learningChangeLabel } from "./memoryLearning.js";

test("labels memory learning change types for humans", () => {
  expect(learningChangeLabel("skill_note")).toBe("skill note");
  expect(learningChangeLabel("memory_feedback")).toBe("memory feedback");
  expect(learningChangeLabel("custom_rule_name")).toBe("custom rule name");
});

test("describes approved learning effects", () => {
  expect(learningCandidateEffect("skill_note", "approved")).toBe("active in future prompts");
  expect(learningCandidateEffect("prompt_note", "applied")).toBe("active in future prompts");
  expect(learningCandidateEffect("prompt_note", "approved")).toBe("active in future prompts");
  expect(learningCandidateEffect("memory_feedback", "approved")).toBe("accepted for manual follow-up");
  expect(learningCandidateEffect("memory_feedback", "rejected")).toBe("not used");
  expect(learningCandidateEffect("skill_note", "proposed")).toBe("approval adds this to future prompts");
});

test("explains approval before mutation", () => {
  expect(learningApprovalEffect("skill_note")).toBe("approval adds this to future prompts");
  expect(learningApprovalEffect("memory_feedback")).toBe(
    "approval records manual follow-up; it does not change runtime"
  );
});
