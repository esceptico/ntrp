import type { ActivityItem } from "../store";

export const SEMANTIC_KIND_AGENT = "agent" as const;

export function isAgent(item: ActivityItem): boolean {
  return item.semanticKind === SEMANTIC_KIND_AGENT;
}
