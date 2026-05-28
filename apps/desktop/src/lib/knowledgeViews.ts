import type { KnowledgeActivationUsageEvent, KnowledgeObject, KnowledgeObjectStatus, KnowledgeObjectType, KnowledgeSurface } from "../api";

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

export const KNOWLEDGE_REVIEW_TYPES: KnowledgeObjectType[] = ["action_candidate", "artifact"];

export function shouldReviewKnowledgeObject(object: KnowledgeObject): boolean {
  return object.status === "draft" && KNOWLEDGE_REVIEW_TYPES.includes(object.object_type);
}

export function isSkillPromotionCandidate(object: KnowledgeObject): boolean {
  return object.object_type === "action_candidate" && object.metadata?.promotion_kind === "skill";
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
  if (isSkillPromotionCandidate(object)) return "skill candidate";
  if (object.object_type === "action_candidate") return "action";
  return object.object_type;
}

export function reviewActionLabel(object: KnowledgeObject): string {
  if (isSkillPromotionCandidate(object)) return "Create skill";
  if (object.object_type === "action_candidate") return "Approve action";
  return "Approve";
}

export function reviewOutcomeHint(object: KnowledgeObject): string {
  if (isSkillPromotionCandidate(object)) {
    return "Review the generated SKILL.md draft before creating the skill.";
  }
  if (object.object_type === "action_candidate") return "Approving keeps this as an approved follow-up candidate.";
  if (object.object_type === "artifact") return "Publishing records this artifact through the local review sink.";
  return "Review before letting this change memory.";
}


function activationDetailText(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function humanizeActivationSurface(surface: string): string {
  return surface.replace(/_/g, " ");
}

export type SkillActivationSubtypeKey =
  | "all"
  | "explicit"
  | "chat_auto"
  | "operator_auto"
  | "background_auto"
  | "research_auto"
  | "other_auto"
  | "other";

export const SKILL_ACTIVATION_SUBTYPE_FILTERS: Array<{ key: SkillActivationSubtypeKey; label: string }> = [
  { key: "all", label: "All" },
  { key: "explicit", label: "Explicit" },
  { key: "chat_auto", label: "Chat auto" },
  { key: "operator_auto", label: "Operator auto" },
  { key: "background_auto", label: "Background auto" },
  { key: "research_auto", label: "Research auto" },
  { key: "other_auto", label: "Other auto" },
  { key: "other", label: "Other" },
];

export function skillActivationSubtypeKey(event: KnowledgeActivationUsageEvent): SkillActivationSubtypeKey {
  if (event.policy_version === "skills.use.activation.v1") return "explicit";
  if (event.policy_version === "skills.auto_activation.v1") {
    const activationSurface = activationDetailText(event.details, "activation_surface");
    if (activationSurface === "chat_prompt") return "chat_auto";
    if (activationSurface === "operator_prompt") return "operator_auto";
    if (activationSurface === "background_prompt") return "background_auto";
    if (activationSurface === "research_context") return "research_auto";
    return "other_auto";
  }
  return "other";
}

export function skillActivationSubtypeLabel(event: KnowledgeActivationUsageEvent): string {
  if (event.policy_version === "skills.use.activation.v1") return "explicit use_skill";
  if (event.policy_version === "skills.auto_activation.v1") {
    const activationSurface = activationDetailText(event.details, "activation_surface");
    if (activationSurface === "chat_prompt") return "chat auto-activation";
    if (activationSurface === "operator_prompt") return "operator auto-activation";
    if (activationSurface) return `${humanizeActivationSurface(activationSurface)} auto-activation`;
    return "auto-activation";
  }
  return event.source === "skill_activation" ? "skill activation" : event.source;
}
