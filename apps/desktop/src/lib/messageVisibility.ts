import type { Role } from "../store";

export function visibleMessageIds({
  ids,
  roles,
}: {
  ids: string[];
  roles: (Role | null)[];
}): string[] {
  return ids.filter((_, index) => roles[index] !== "reasoning");
}
