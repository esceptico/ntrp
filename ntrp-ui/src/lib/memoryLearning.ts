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

export function learningCandidateEffect(changeType: string, status: string): string | null {
  if (status !== "approved") return null;
  if (changeType === "skill_note" || changeType === "prompt_note") {
    return "active in future prompts";
  }
  return "approved for manual follow-up";
}
