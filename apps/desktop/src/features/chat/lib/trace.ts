import type { ActivityItem } from "@/stores";
import { activityItemStatus, isAgent, isHtmlWidget, isWorkflow } from "@/lib/agent";
import type { Workflow, WorkflowStatus } from "@/stores/workflow-domain";

// A workflow renders as its own card, NOT one of the "N calls". It is recognized
// by the tool-call ITEM (semanticKind === "workflow"), which always exists — so
// the card shows immediately and survives reload, independent of the streamed
// workflow-domain events. When a live domain row IS present (parent_tool_call_id
// match) it wins and supplies real phases/agents/tokens; otherwise we synthesize
// a sparse Workflow from the item (title + status) so the card still renders.

export type TraceEntry =
  | { kind: "workflow"; workflow: Workflow }
  | { kind: "html_widget"; item: ActivityItem }
  | { kind: "rows"; items: ActivityItem[] };

// The trace in chronological order: runs of ordinary tool rows, with each
// workflow card at the position its tool call actually holds — a workflow
// called after setup tools renders after their rows, not lifted above them.
export function orderedTraceEntries(
  items: ActivityItem[],
  workflows: Workflow[],
  sessionId: string | null,
): TraceEntry[] {
  // The tool-call items that ARE workflows — their entire subtree (leaf agents +
  // those agents' tool calls, which the server rebases under this id) is
  // contained in the card's drill-in, never shown as parent rows.
  const workflowItemIds = new Set(
    items
      .filter((it) => isWorkflow(it) || workflows.some((w) => w.parentToolCallId === it.id))
      .map((it) => it.id),
  );
  const byId = new Map(items.map((it) => [it.id, it] as const));
  const insideWorkflow = (it: ActivityItem): boolean => {
    let cur = it.parentToolId;
    while (cur) {
      if (workflowItemIds.has(cur)) return true;
      cur = byId.get(cur)?.parentToolId;
    }
    return false;
  };

  const entries: TraceEntry[] = [];
  let segment: ActivityItem[] = [];
  const flush = () => {
    if (segment.length > 0) {
      entries.push({ kind: "rows", items: segment });
      segment = [];
    }
  };
  for (const it of items) {
    const domain = workflows.find((w) => w.parentToolCallId === it.id);
    if (domain) {
      flush();
      entries.push({ kind: "workflow", workflow: domain });
    } else if (isWorkflow(it)) {
      flush();
      entries.push({ kind: "workflow", workflow: synthWorkflow(it, sessionId) });
    } else if (isHtmlWidget(it)) {
      flush();
      entries.push({ kind: "html_widget", item: it });
    } else if (insideWorkflow(it)) {
      continue; // contained in the workflow, not a parent row
    } else {
      segment.push(it);
    }
  }
  flush();
  return entries;
}

/** Flat view over orderedTraceEntries for callers that only need the split
 *  (e.g. the header's "N calls" count over post-lift rows). */
export function liftWorkflows(
  items: ActivityItem[],
  workflows: Workflow[],
  sessionId: string | null,
): { workflowRows: Workflow[]; htmlWidgetItems: ActivityItem[]; rowItems: ActivityItem[] } {
  const entries = orderedTraceEntries(items, workflows, sessionId);
  return {
    workflowRows: entries.filter((e) => e.kind === "workflow").map((e) => e.workflow),
    htmlWidgetItems: entries.filter((e) => e.kind === "html_widget").map((e) => e.item),
    rowItems: entries.flatMap((e) => (e.kind === "rows" ? e.items : [])),
  };
}

function synthWorkflow(item: ActivityItem, sessionId: string | null): Workflow {
  const now = Date.now();
  const status = workflowStatusFromItem(item);
  // Use the tool call's own duration so a settled card shows real elapsed (not
  // 0s) even with no domain row; a running one ticks from now until the live
  // domain takes over.
  const settled = status !== "running";
  const dur = item.durationMs ?? 0;
  return {
    workflowId: item.workflowId ?? item.id,
    sessionId: sessionId ?? "",
    runId: item.runId ?? "",
    parentToolCallId: item.id,
    name: workflowNameFromItem(item),
    status,
    phasesByName: {},
    totalAgents: 0,
    startedAt: settled ? now - dur : now,
    completedAt: settled ? now : undefined,
    updatedAt: now,
  };
}

function workflowStatusFromItem(item: ActivityItem): WorkflowStatus {
  if (activityItemStatus(item) === "ongoing") return "running";
  return item.error ? "failed" : "completed";
}

function workflowNameFromItem(item: ActivityItem): string | undefined {
  try {
    const parsed = JSON.parse(item.args ?? "{}");
    if (parsed && typeof parsed.title === "string" && parsed.title.trim()) return parsed.title.trim();
  } catch {
    // args not yet complete / not JSON — fall back to the generic card name.
  }
  return undefined;
}

export const NEST_PX = 16;
export const MAX_NEST_DEPTH = 4; // visual cap; deeper nesting collapses to the same indent

/** Static-mode tree: post-run, expanded panel. Emit every item in DFS
 *  order (parent before children). Session-backed child agents are leaves:
 *  their internal tools now live in the child session, not the parent trace. */
export function buildStaticTree(items: ActivityItem[]): ActivityItem[] {
  const childrenByParent = new Map<string, ActivityItem[]>();
  for (const it of items) {
    if (!it.parentToolId) continue;
    const arr = childrenByParent.get(it.parentToolId) ?? [];
    arr.push(it);
    childrenByParent.set(it.parentToolId, arr);
  }

  const out: ActivityItem[] = [];
  const seen = new Set<string>();

  const visit = (item: ActivityItem) => {
    if (seen.has(item.id)) return;
    seen.add(item.id);
    out.push(item);
    if (isSessionBackedAgent(item)) {
      markDescendantsSeen(item.id);
      return;
    }
    const kids = childrenByParent.get(item.id);
    if (kids) for (const k of kids) visit(k);
  };

  const markDescendantsSeen = (parentId: string) => {
    const kids = childrenByParent.get(parentId);
    if (!kids) return;
    for (const kid of kids) {
      if (seen.has(kid.id)) continue;
      seen.add(kid.id);
      markDescendantsSeen(kid.id);
    }
  };

  for (const t of items.filter((it) => (it.depth ?? 0) === 0)) visit(t);
  // Belt-and-suspenders: surface any item whose parentToolId points
  // outside this activity's items (e.g. when sub-agent calls span
  // multiple activity messages). Better to show unanchored than to
  // silently drop and have the user wonder where the tool went.
  for (const it of items) {
    if (!seen.has(it.id)) {
      seen.add(it.id);
      out.push(it);
    }
  }
  return out;
}

/** Walk the activity tree and return a flat ordered list to render in
 *  rolling mode. Agent rows are pinned so all spawned research agents remain
 *  visible; non-agent rows at each level are capped at `max`. We recurse into
 *  a parent's children only while the parent is still running, so finished
 *  agents don't keep their detail on screen. Parents appear before their kids
 *  so the natural document order doubles as visual hierarchy (depth-based
 *  indent comes from `ItemButton`).
 *
 *  A `seen` set guards the recursion so a malformed tree (cycle, or a
 *  depth-0 row that also points at a parent) can't blow the stack or emit
 *  duplicate React keys. */
export function buildRollingList(items: ActivityItem[], max: number): ActivityItem[] {
  const childrenByParent = new Map<string, ActivityItem[]>();
  const ids = new Set(items.map((it) => it.id));
  for (const it of items) {
    if (!it.parentToolId) continue;
    const arr = childrenByParent.get(it.parentToolId) ?? [];
    arr.push(it);
    childrenByParent.set(it.parentToolId, arr);
  }

  const out: ActivityItem[] = [];
  const seen = new Set<string>();

  const include = (item: ActivityItem) => {
    if (seen.has(item.id)) return;
    seen.add(item.id);
    out.push(item);
    if (activityItemStatus(item) === "ongoing" && !isSessionBackedAgent(item)) {
      const kids = childrenByParent.get(item.id);
      if (kids) for (const k of rollingLevel(kids, max)) include(k);
    }
  };

  const topLevel = items.filter((it) => (it.depth ?? 0) === 0);
  for (const t of rollingLevel(topLevel, max)) include(t);
  for (const it of rollingLevel(items.filter((item) => item.parentToolId && !ids.has(item.parentToolId)), max)) {
    include(it);
  }
  if (out.length === 0) {
    for (const it of rollingLevel(items, max)) include(it);
  }
  return out;
}

function rollingLevel(items: ActivityItem[], max: number): ActivityItem[] {
  const pinnedAgentIds = new Set(items.filter(isAgent).map((item) => item.id));
  const tailIds = new Set(items.slice(-max).map((item) => item.id));
  return items.filter((item) => pinnedAgentIds.has(item.id) || tailIds.has(item.id));
}

export function isSessionBackedAgent(item: ActivityItem): boolean {
  return isAgent(item) && !!item.childAgent?.childSessionId;
}
