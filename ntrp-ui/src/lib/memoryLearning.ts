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
    default:
      return changeType.replaceAll("_", " ");
  }
}
