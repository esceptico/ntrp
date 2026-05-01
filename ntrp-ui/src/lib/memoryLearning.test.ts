import { expect, test } from "bun:test";
import {
  canApplyLearningCandidate,
  canApproveLearningCandidate,
  canRejectLearningCandidate,
  canRevertLearningCandidate,
  learningApprovalEffect,
  learningCandidateEffect,
  learningChangeLabel,
  learningLane,
  learningLaneLabel,
  learningTargetLabel,
} from "./memoryLearning.js";

test("labels memory learning change types for humans", () => {
  expect(learningChangeLabel("skill_note")).toBe("skill note");
  expect(learningChangeLabel("prompt_note")).toBe("prompt note");
  expect(learningChangeLabel("automation_rule")).toBe("automation rule");
  expect(learningChangeLabel("memory_feedback")).toBe("memory feedback");
  expect(learningChangeLabel("custom_rule_name")).toBe("custom rule name");
});

test("labels memory learning targets for humans", () => {
  expect(learningTargetLabel("memory.injection.budget")).toBe("memory injection budget");
  expect(learningTargetLabel("memory.observations.compression.feedback")).toBe("pattern compression feedback");
  expect(learningTargetLabel("skill.release-workflow")).toBe("skill: release workflow");
  expect(learningTargetLabel("automation.builtin_learning_review")).toBe("automation: builtin learning review");
  expect(learningTargetLabel("automation.builtin:learning-review")).toBe("automation: builtin learning review");
});

test("describes approved learning effects", () => {
  expect(learningCandidateEffect("skill_note", "approved")).toBe("active in future prompts");
  expect(learningCandidateEffect("prompt_note", "applied")).toBe("active in future prompts");
  expect(learningCandidateEffect("prompt_note", "approved")).toBe("active in future prompts");
  expect(learningCandidateEffect("memory_feedback", "approved")).toBe("ready to apply to memory policy prompts");
  expect(learningCandidateEffect("memory_feedback", "applied")).toBe("active in memory policy prompts");
  expect(learningCandidateEffect("automation_rule", "approved")).toBe("ready to apply to automation runs");
  expect(learningCandidateEffect("automation_rule", "applied")).toBe("active in future automation runs");
  expect(learningCandidateEffect("memory_feedback", "rejected")).toBe("not used");
  expect(learningCandidateEffect("skill_note", "proposed")).toBe("approval adds this to future prompts");
});

test("explains approval before mutation", () => {
  expect(learningApprovalEffect("skill_note")).toBe("approval adds this to future prompts");
  expect(learningApprovalEffect("memory_feedback")).toBe("approval accepts it; apply adds a memory policy note");
  expect(learningApprovalEffect("automation_rule")).toBe("approval accepts it; apply adds an automation policy note");
});

test("classifies learning lanes", () => {
  expect(learningLane("skill_note", "skill.release")).toBe("skill");
  expect(learningLane("prompt_note", "prompt.learning_context")).toBe("runtime");
  expect(learningLane("automation_rule", "automation.learning_review")).toBe("automation");
  expect(learningLane("memory_feedback", "memory.extraction.feedback")).toBe("memory");
  expect(learningLaneLabel("automation")).toBe("automation");
});

test("matches learning action affordances to legal transitions", () => {
  expect(canApproveLearningCandidate("proposed")).toBe(true);
  expect(canApproveLearningCandidate("approved")).toBe(false);
  expect(canApproveLearningCandidate("applied")).toBe(false);

  expect(canApplyLearningCandidate("approved")).toBe(true);
  expect(canApplyLearningCandidate("proposed")).toBe(false);

  expect(canRejectLearningCandidate("proposed")).toBe(true);
  expect(canRejectLearningCandidate("approved")).toBe(true);
  expect(canRejectLearningCandidate("applied")).toBe(false);
  expect(canRejectLearningCandidate("reverted")).toBe(false);

  expect(canRevertLearningCandidate("applied")).toBe(true);
  expect(canRevertLearningCandidate("approved")).toBe(false);
});
