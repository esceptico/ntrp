import type { ActivityItem } from "../store";

export const SEMANTIC_KIND_AGENT = "agent" as const;

export function isAgent(item: ActivityItem): boolean {
  return item.semanticKind === SEMANTIC_KIND_AGENT;
}

export function activityItemStatus(item: ActivityItem): "ongoing" | "executed" {
  if (item.status) return item.status;
  if (item.taskStatus === "running") return "ongoing";
  if (item.taskStatus === "completed" || item.taskStatus === "failed" || item.taskStatus === "cancelled") {
    return "executed";
  }
  return item.result == null ? "ongoing" : "executed";
}

export function activityTraceStats(items: ActivityItem[]): {
  totalCount: number;
  activeCount: number;
} {
  return {
    totalCount: items.length,
    activeCount: items.filter((item) => activityItemStatus(item) === "ongoing").length,
  };
}

/** Pull the natural-language `task` field out of an agent tool-call's
 *  args (which arrive as a JSON string). Used by both the chat row and
 *  the inspector to show the task instead of the raw args dict. */
export function extractTask(args: string | undefined): string | null {
  if (!args) return null;
  try {
    const parsed = JSON.parse(args);
    if (parsed && typeof parsed === "object" && typeof parsed.task === "string") {
      return parsed.task;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** "research" → "Research", "research_agent" → "Research". */
export function friendlyAgentLabel(toolName: string): string {
  const stripped = toolName.replace(/_agent$/i, "");
  if (!stripped) return toolName;
  return stripped[0].toUpperCase() + stripped.slice(1);
}
