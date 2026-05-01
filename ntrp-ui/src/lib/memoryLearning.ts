export type LearningLane = "memory" | "runtime" | "skill" | "automation";
export type LearningLaneFilter = "all" | LearningLane;

export function learningChangeLabel(changeType: string): string {
  switch (changeType) {
    case "skill_note":
      return "skill note";
    case "prompt_note":
      return "prompt note";
    case "automation_rule":
      return "automation rule";
    case "supersession_review":
      return "profile conflict";
    case "memory_feedback":
      return "memory feedback";
    case "injection_rule":
      return "injection rule";
    case "recall_rule":
      return "recall rule";
    case "profile_rule":
      return "profile rule";
    case "prune_rule":
      return "cleanup rule";
    default:
      return changeType.replaceAll("_", " ");
  }
}

export function learningTargetLabel(targetKey: string): string {
  switch (targetKey) {
    case "memory.injection.budget":
      return "memory injection budget";
    case "memory.injection.ranking":
      return "memory injection ranking";
    case "memory.profile.quality":
      return "profile memory quality";
    case "memory.facts.supersession.profile":
      return "profile fact conflict review";
    case "memory.observations.compression.feedback":
      return "pattern compression feedback";
    case "memory.observations.prune.low_evidence":
      return "low-evidence pattern cleanup";
    case "prompt.runtime":
      return "runtime prompt";
    case "prompt.prompt":
      return "agent prompt";
    case "automation.review":
      return "automation review";
    default:
      if (targetKey.startsWith("skill.")) return `skill: ${readableKeyPart(targetKey.slice(6))}`;
      if (targetKey.startsWith("prompt.")) return `prompt: ${readableKeyPart(targetKey.slice(7))}`;
      if (targetKey.startsWith("automation.")) return `automation: ${readableKeyPart(targetKey.slice(11))}`;
      return readableKeyPart(targetKey);
  }
}

export function learningLane(changeType: string, targetKey: string): LearningLane {
  if (changeType === "skill_note" || targetKey.startsWith("skill.")) return "skill";
  if (changeType === "prompt_note" || targetKey.startsWith("prompt.") || targetKey.startsWith("runtime.")) {
    return "runtime";
  }
  if (changeType === "automation_rule" || targetKey.startsWith("automation.")) return "automation";
  return "memory";
}

export function learningLaneLabel(lane: LearningLaneFilter): string {
  switch (lane) {
    case "runtime":
      return "runtime";
    case "skill":
      return "skills";
    case "automation":
      return "automation";
    case "memory":
      return "memory";
    default:
      return "all";
  }
}

export function learningCandidateEffect(changeType: string, status: string): string | null {
  if (status === "rejected" || status === "reverted") return "not used";
  if (status !== "approved" && status !== "applied") return learningApprovalEffect(changeType);
  if (changeType === "skill_note" || changeType === "prompt_note") {
    return "active in future prompts";
  }
  if (changeType === "automation_rule") {
    return status === "applied" ? "active in future automation runs" : "ready to apply to automation runs";
  }
  return status === "applied" ? "active in memory policy prompts" : "ready to apply to memory policy prompts";
}

export function canApproveLearningCandidate(status: string | undefined): boolean {
  return status === "proposed";
}

export function canApplyLearningCandidate(status: string | undefined): boolean {
  return status === "approved";
}

export function canRejectLearningCandidate(status: string | undefined): boolean {
  return status === "proposed" || status === "approved";
}

export function canRevertLearningCandidate(status: string | undefined): boolean {
  return status === "applied";
}

export function learningApprovalEffect(changeType: string): string {
  if (changeType === "skill_note" || changeType === "prompt_note") {
    return "approval adds this to future prompts";
  }
  if (changeType === "automation_rule") {
    return "approval accepts it; apply adds an automation policy note";
  }
  return "approval accepts it; apply adds a memory policy note";
}

function readableKeyPart(value: string): string {
  return value.replace(/[._:-]+/g, " ").replace(/\s+/g, " ").trim();
}
