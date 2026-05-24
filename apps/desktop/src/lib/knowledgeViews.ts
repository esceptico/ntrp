import type { KnowledgeObject, KnowledgeObjectStatus, KnowledgeObjectType, KnowledgeSurface } from "../api";

export interface KnowledgeLibraryView {
  type: KnowledgeObjectType;
  label: string;
  description: string;
}

export const KNOWLEDGE_LIBRARY_TYPES: KnowledgeLibraryView[] = [
  { type: "fact", label: "Facts", description: "durable source-backed facts" },
  { type: "lesson", label: "Lessons", description: "reusable conclusions and preferences" },
  { type: "artifact", label: "Artifacts", description: "important reusable outputs" },
  { type: "memory_episode", label: "Episodes", description: "short rolling conversation episodes" },
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

export function knowledgeSurfaceStatusCount(
  surfaces: KnowledgeSurface[],
  type: KnowledgeObjectType,
  status: KnowledgeObjectStatus,
): number {
  const surface = surfaces.find((item) => item.object_type === type);
  return surface?.counts_by_status?.[status] ?? (status === "active" ? surface?.count ?? 0 : 0);
}

export function knowledgeSurfaceAllStatusCount(surfaces: KnowledgeSurface[], type: KnowledgeObjectType): number {
  const surface = surfaces.find((item) => item.object_type === type);
  const statusCounts = surface?.counts_by_status;
  if (statusCounts) {
    return Object.values(statusCounts).reduce((total, count) => total + (count ?? 0), 0);
  }
  return surface?.count ?? 0;
}

export function reviewKind(object: KnowledgeObject): string {
  if (object.object_type === "procedure_candidate") return "lesson candidate";
  if (object.object_type === "action_candidate") return "action";
  return object.object_type;
}

export function reviewActionLabel(object: KnowledgeObject): string {
  if (object.object_type === "procedure_candidate") return "Promote to lesson";
  if (object.object_type === "action_candidate") return "Approve action";
  return "Approve";
}

export function reviewOutcomeHint(object: KnowledgeObject): string {
  if (object.object_type === "procedure_candidate") return "Approving creates an active lesson, not a procedure memory.";
  if (object.object_type === "action_candidate") return "Approving keeps this as an approved follow-up candidate.";
  if (object.object_type === "artifact") return "Publishing records this artifact through the local review sink.";
  return "Review before letting this change memory.";
}
