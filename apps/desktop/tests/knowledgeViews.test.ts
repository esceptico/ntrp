import { expect, test } from "bun:test";
import type { KnowledgeObject, KnowledgeSurface } from "../src/api";
import {
  KNOWLEDGE_LIBRARY_TYPES,
  KNOWLEDGE_REVIEW_TYPES,
  knowledgeSurfaceCount,
  shouldReviewKnowledgeObject,
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
    "episode",
    "fact",
    "pattern",
    "lesson",
    "procedure",
    "action_candidate",
    "artifact",
    "outcome_feedback",
  ]);
});

test("review queue contains only draft behavior-changing knowledge", () => {
  expect(shouldReviewKnowledgeObject(object({ object_type: "procedure_candidate", status: "draft" }))).toBe(true);
  expect(shouldReviewKnowledgeObject(object({ object_type: "action_candidate", status: "draft" }))).toBe(true);
  expect(shouldReviewKnowledgeObject(object({ object_type: "artifact", status: "draft" }))).toBe(true);
  expect(shouldReviewKnowledgeObject(object({ object_type: "fact", status: "draft" }))).toBe(false);
  expect(shouldReviewKnowledgeObject(object({ object_type: "procedure_candidate", status: "approved" }))).toBe(false);
  expect(KNOWLEDGE_REVIEW_TYPES).toEqual(["procedure_candidate", "action_candidate", "artifact"]);
});

test("surface counts default to zero for missing types", () => {
  const surfaces: KnowledgeSurface[] = [
    { name: "Lessons", object_type: "lesson", count: 3, description: "x" },
  ];

  expect(knowledgeSurfaceCount(surfaces, "lesson")).toBe(3);
  expect(knowledgeSurfaceCount(surfaces, "fact")).toBe(0);
});
