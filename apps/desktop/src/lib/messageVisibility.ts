import type { Role } from "../store";

export function visibleMessageIds({
  ids,
  roles,
  showReasoning,
}: {
  ids: string[];
  roles: (Role | null)[];
  showReasoning: boolean;
}): string[] {
  return ids.filter((_, index) => showReasoning || roles[index] !== "reasoning");
}
