import { type ActivityItem } from "@/stores";
import { isAgent } from "@/lib/agent";
import { humanizeAgentType } from "@/lib/agentRun";

/** Pretty-print JSON; fall back to the raw string when parse fails. The
 *  `lang` field is set to "json" when we successfully reformatted, so the
 *  viewer can syntax-highlight only when we actually have JSON. */
export function formatMaybeJson(raw: string | undefined): { body: string; lang: string } {
  if (!raw) return { body: "", lang: "" };
  const trimmed = raw.trim();
  if (!trimmed) return { body: "", lang: "" };
  try {
    return { body: JSON.stringify(JSON.parse(trimmed), null, 2), lang: "json" };
  } catch {
    return { body: raw, lang: "" };
  }
}

export function formatAgentUsage(tokens: number, cost: number | undefined): string {
  const tk =
    tokens < 1000
      ? `${tokens}`
      : tokens < 10000
        ? `${(tokens / 1000).toFixed(1)}k`
        : `${Math.round(tokens / 1000)}k`;
  if (!cost) return `${tk} tokens`;
  const ct = cost < 0.01 ? `$${cost.toFixed(4)}` : `$${cost.toFixed(3)}`;
  return `${tk} tokens · ${ct}`;
}

export function childAgentTreeDetail(item: ActivityItem): string | null {
  if (!item.childAgent) return null;
  const mode = item.childAgent.wait ? "awaited" : "detached";
  return `${humanizeAgentType(item.childAgent.agentType)} · ${mode}`;
}

export function buildStats(descendants: ActivityItem[]) {
  let agents = 0;
  for (const d of descendants) if (isAgent(d)) agents++;
  return { total: descendants.length, agents };
}
