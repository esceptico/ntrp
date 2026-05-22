import type { KnowledgeObject, KnowledgeObjectType, KnowledgeSurface } from "../api";

export interface KnowledgeLibraryView {
  type: KnowledgeObjectType;
  label: string;
  description: string;
}

export const KNOWLEDGE_LIBRARY_TYPES: KnowledgeLibraryView[] = [
  { type: "episode", label: "Episodes", description: "captured work moments" },
  { type: "fact", label: "Facts", description: "source-backed facts" },
  { type: "pattern", label: "Patterns", description: "derived context" },
  { type: "lesson", label: "Lessons", description: "reusable conclusions" },
  { type: "procedure", label: "Procedures", description: "approved behavior" },
  { type: "entity_profile", label: "Profiles", description: "source-backed entity context" },
  { type: "action_candidate", label: "Actions", description: "proactive drafts" },
  { type: "artifact", label: "Artifacts", description: "reusable outputs" },
  { type: "outcome_feedback", label: "Activation", description: "sent context and feedback" },
];

export const KNOWLEDGE_REVIEW_TYPES: KnowledgeObjectType[] = [
  "procedure_candidate",
  "action_candidate",
  "artifact",
];

export function shouldReviewKnowledgeObject(object: KnowledgeObject): boolean {
  return object.status === "draft" && KNOWLEDGE_REVIEW_TYPES.includes(object.object_type);
}

export function knowledgeSurfaceCount(surfaces: KnowledgeSurface[], type: KnowledgeObjectType): number {
  return surfaces.find((surface) => surface.object_type === type)?.count ?? 0;
}

export function reviewKind(object: KnowledgeObject): string {
  if (object.object_type === "procedure_candidate") return "procedure";
  if (object.object_type === "action_candidate") return "action";
  return object.object_type;
}
