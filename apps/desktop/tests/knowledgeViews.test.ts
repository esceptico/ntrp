import { expect, test } from "bun:test";
import type { KnowledgeActivationUsageEvent, KnowledgeObject, KnowledgeSurface } from "../src/api";
import {
  KNOWLEDGE_LIBRARY_TYPES,
  KNOWLEDGE_REVIEW_TYPES,
  SKILL_ACTIVATION_SUBTYPE_FILTERS,
  knowledgeSurfaceCount,
  shouldReviewKnowledgeObject,
  skillActivationSubtypeKey,
  skillActivationSubtypeLabel,
} from "../src/lib/knowledgeViews.js";

function object(patch: Partial<KnowledgeObject>): KnowledgeObject {
  return {
    id: 1,
    object_type: "fact",
    title: "Fact",
    text: "Fact text",
    status: "active",
    scope: null,
    activation: "prompt",
    proactiveness_level: "L0",
    score: 0,
    source_ids: [],
    metadata: {},
    created_at: "2026-05-19T00:00:00Z",
    updated_at: "2026-05-19T00:00:00Z",
    reviewed_at: null,
    ...patch,
  };
}

test("memory library exposes typed knowledge views, not automation state", () => {
  expect(KNOWLEDGE_LIBRARY_TYPES.map((view) => view.type)).toEqual([
    "fact",
    "lesson",
    "artifact",
    "memory_episode",
  ]);
});

test("review queue contains only draft behavior-changing knowledge", () => {
  expect(shouldReviewKnowledgeObject(object({ object_type: "procedure_candidate", status: "draft" }))).toBe(false);
  expect(shouldReviewKnowledgeObject(object({ object_type: "action_candidate", status: "draft" }))).toBe(true);
  expect(shouldReviewKnowledgeObject(object({ object_type: "artifact", status: "draft" }))).toBe(true);
  expect(shouldReviewKnowledgeObject(object({ object_type: "fact", status: "draft" }))).toBe(false);
  expect(shouldReviewKnowledgeObject(object({ object_type: "procedure_candidate", status: "approved" }))).toBe(false);
  expect(KNOWLEDGE_REVIEW_TYPES).toEqual(["action_candidate", "artifact"]);
});

test("surface counts default to zero for missing types", () => {
  const surfaces: KnowledgeSurface[] = [
    { name: "Lessons", object_type: "lesson", count: 3, description: "x" },
  ];

  expect(knowledgeSurfaceCount(surfaces, "lesson")).toBe(3);
  expect(knowledgeSurfaceCount(surfaces, "fact")).toBe(0);
});


function activationEvent(patch: Partial<KnowledgeActivationUsageEvent>): KnowledgeActivationUsageEvent {
  return {
    id: 1,
    created_at: "2026-05-26T00:00:00Z",
    source: "skill_activation",
    query: "dex-audit",
    retrieved_fact_ids: [],
    retrieved_observation_ids: [],
    injected_fact_ids: [],
    injected_observation_ids: [],
    omitted_fact_ids: [],
    omitted_observation_ids: [],
    bundled_fact_ids: [],
    formatted_chars: 0,
    policy_version: "skills.use.activation.v1",
    details: {},
    ...patch,
  };
}

test("skill activation labels distinguish explicit and auto activation surfaces", () => {
  expect(skillActivationSubtypeLabel(activationEvent({ policy_version: "skills.use.activation.v1" }))).toBe("explicit use_skill");
  expect(
    skillActivationSubtypeLabel(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "chat_prompt" },
      }),
    ),
  ).toBe("chat auto-activation");
  expect(
    skillActivationSubtypeLabel(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "operator_prompt" },
      }),
    ),
  ).toBe("operator auto-activation");
  expect(
    skillActivationSubtypeLabel(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "background_prompt" },
      }),
    ),
  ).toBe("background prompt auto-activation");
  expect(
    skillActivationSubtypeLabel(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "research_context" },
      }),
    ),
  ).toBe("research context auto-activation");
});

test("skill activation subtype filters cover explicit and auto surfaces", () => {
  expect(SKILL_ACTIVATION_SUBTYPE_FILTERS.map((filter) => filter.key)).toEqual([
    "all",
    "explicit",
    "chat_auto",
    "operator_auto",
    "background_auto",
    "research_auto",
    "other_auto",
    "other",
  ]);
  expect(skillActivationSubtypeKey(activationEvent({ policy_version: "skills.use.activation.v1" }))).toBe("explicit");
  expect(
    skillActivationSubtypeKey(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "chat_prompt" },
      }),
    ),
  ).toBe("chat_auto");
  expect(
    skillActivationSubtypeKey(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "operator_prompt" },
      }),
    ),
  ).toBe("operator_auto");
  expect(
    skillActivationSubtypeKey(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "background_prompt" },
      }),
    ),
  ).toBe("background_auto");
  expect(
    skillActivationSubtypeKey(
      activationEvent({
        policy_version: "skills.auto_activation.v1",
        details: { activation_surface: "research_context" },
      }),
    ),
  ).toBe("research_auto");
  expect(skillActivationSubtypeKey(activationEvent({ policy_version: "unknown" }))).toBe("other");
});
