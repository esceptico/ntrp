export function learningChangeLabel(changeType: string): string {
  switch (changeType) {
    case "skill_note":
      return "skill note";
    case "supersession_review":
      return "profile conflict";
    case "memory_policy":
      return "memory policy";
    case "prompt_update":
      return "prompt";
    case "profile_policy":
      return "profile";
    case "memory_feedback":
      return "memory feedback";
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
    default:
      if (targetKey.startsWith("skill.")) return `skill: ${targetKey.slice(6).replaceAll("-", " ")}`;
      if (targetKey.startsWith("prompt.")) return `prompt: ${targetKey.slice(7).replaceAll(".", " ")}`;
      return targetKey.replaceAll("_", " ").replaceAll(".", " ");
  }
}

export function learningCandidateEffect(changeType: string, status: string): string | null {
  if (status === "rejected" || status === "reverted") return "not used";
  if (status !== "approved" && status !== "applied") return learningApprovalEffect(changeType);
  if (changeType === "skill_note" || changeType === "prompt_note") {
    return "active in future prompts";
  }
  return "accepted for manual follow-up";
}

export function canApproveLearningCandidate(status: string | undefined): boolean {
  return status === "proposed";
}

export function canRejectLearningCandidate(status: string | undefined): boolean {
  return status === "proposed" || status === "approved";
}

export function learningApprovalEffect(changeType: string): string {
  if (changeType === "skill_note" || changeType === "prompt_note") {
    return "approval adds this to future prompts";
  }
  return "approval records manual follow-up; it does not change runtime";
}
