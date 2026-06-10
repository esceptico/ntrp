import { useMemo, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Bot, ChevronDown, Square, SquareTerminal } from "lucide-react";
import clsx from "clsx";
import { useStore, type ActivityItem, type ActivityLabel } from "../../store";
import { activityItemStatus, isAgent, isWorkflow } from "../../lib/agent";
import { cancelSubagent, switchSession } from "../../actions";
// Collapse/expand height shift on the trace — layout-style settle, not a modal entry.
import { SPRING_LAYOUT } from "../../lib/tokens/motion";
import { RollingToken } from "./RollingToken";
import { ICON } from "../../lib/icons";
import { StatusDot } from "../StatusDot";
import { agentRunFromActivityItem, isActiveAgentStatus } from "../../lib/agentRun";
import { useWorkflows } from "../../hooks/useWorkflows";
import { ExpandableWorkflowCard } from "../workflow/WorkflowDetail";
import type { Workflow, WorkflowStatus } from "../../store/workflow-domain";

export type { ActivityItem };

// A workflow renders as its own card, NOT one of the "N calls". It is recognized
// by the tool-call ITEM (semanticKind === "workflow"), which always exists — so
// the card shows immediately and survives reload, independent of the streamed
// workflow-domain events. When a live domain row IS present (parent_tool_call_id
// match) it wins and supplies real phases/agents/tokens; otherwise we synthesize
// a sparse Workflow from the item (title + status) so the card still renders.

export type TraceEntry =
  | { kind: "workflow"; workflow: Workflow }
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
): { workflowRows: Workflow[]; rowItems: ActivityItem[] } {
  const entries = orderedTraceEntries(items, workflows, sessionId);
  return {
    workflowRows: entries.filter((e) => e.kind === "workflow").map((e) => e.workflow),
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

const ROW_HEIGHT_EM = 1.4;
const NEST_PX = 16;
const MAX_NEST_DEPTH = 4; // visual cap; deeper nesting collapses to the same indent

export function ActivityTrace({ children }: { children: ReactNode }) {
  return (
    <div className="font-sans text-sm leading-[1.4] text-muted">{children}</div>
  );
}

export function ActivityHeader({
  done,
  label,
  count,
  activeCount = 0,
  backgrounded = false,
  motionDisabled,
  onToggle,
  expanded,
}: {
  done: boolean;
  label?: ActivityLabel;
  count: number;
  activeCount?: number;
  backgrounded?: boolean;
  motionDisabled?: boolean;
  onToggle?: () => void;
  expanded?: boolean;
}) {
  const word = count === 1 ? "call" : "calls";
  const heading = backgrounded
    ? "Backgrounded"
    : label === "Stopped"
      ? "Stopped"
      : activeCount > 0
        ? "Running"
        : done
          ? "Executed"
          : "Calling";
  const interactive = !!onToggle;
  const streamReplaying = useStore((s) => s.streamReplaying);
  const suppressMotion = motionDisabled ?? streamReplaying;

  return (
    <button
      type={interactive ? "button" : undefined}
      onClick={onToggle}
      disabled={!interactive}
      className={clsx(
        "flex h-[18px] items-center gap-2 m-0 p-0 bg-transparent border-0 text-left text-sm leading-[1.4] text-faint",
        interactive ? "cursor-pointer hover:text-muted select-none" : "cursor-default",
      )}
    >
      <SquareTerminal size={ICON.MD} strokeWidth={2} className="shrink-0" />
      {/* Three odometer slots so the label flip ("Running" → "Done"),
          the digit roll (5 → 6 as another tool starts), and the
          singular/plural switch ("tool" / "tools") each animate
          independently instead of the whole string snapping. */}
      <span className="mr-1.5 inline-flex h-full items-center leading-none">
        <RollingToken value={heading} motionDisabled={suppressMotion} />
      </span>
      <span className="inline-flex h-full items-center gap-1 leading-none">
        <RollingToken value={String(count)} mono motionDisabled={suppressMotion} />
        <RollingToken value={word} motionDisabled={suppressMotion} />
      </span>
      {activeCount > 0 && (
        <span className="inline-flex h-full items-center gap-1.5 leading-none">
          <RollingToken value={String(activeCount)} mono motionDisabled={suppressMotion} />
          <span>active</span>
        </span>
      )}
      {interactive && (
        <ChevronDown
          size={ICON.SM}
          strokeWidth={2}
          className={clsx(
            "ml-1 self-center transition-transform duration-trace text-faint",
            expanded && "rotate-180",
          )}
        />
      )}
    </button>
  );
}

export function ActivityTail({
  items,
  max,
  collapsed = false,
  motionDisabled,
}: {
  items: ActivityItem[];
  max?: number;
  collapsed?: boolean;
  motionDisabled?: boolean;
}) {
  // Two render modes:
  //   - "rolling" (max set): used live during a run. Agent parent rows stay
  //     visible so parallel research agents do not disappear; ordinary tool
  //     rows still keep a short tail at each level. Deeper descendants of a
  //     finished parent are hidden so the tail stays short.
  //   - "static"  (max unset): post-run, expanded list. Flat top-level only —
  //     children are reachable via the inspector.
  const rolling = max != null;
  const setViewingTool = useStore((s) => s.setViewingTool);
  const streamReplaying = useStore((s) => s.streamReplaying);
  const suppressMotion = motionDisabled ?? streamReplaying;

  const sessionId = useStore((s) => s.currentSessionId);
  const workflows = useWorkflows(sessionId);

  // Chronological entries: rows segments interleaved with workflow cards at
  // the position their tool call holds in the trace.
  const entries = useMemo(
    () => orderedTraceEntries(items, workflows, sessionId),
    [items, workflows, sessionId],
  );

  // Rolling (live) mode: do NOT animate the container's height. The chat's
  // scroll container above us uses `useStickToBottom` whose own resize-spring
  // would chase a height-spring's intermediate values over many frames —
  // visible as the "odd animation above the chat". Instead let the container
  // resize instantly as rows mount/unmount (one reflow per tool, not 30) and
  // animate only per-row enter/exit + sibling reflow via FLIP transforms.
  //
  // `position: relative` is critical: `mode="popLayout"` sets exiting items
  // to `position: absolute`. Without a positioned ancestor they snap to the
  // scroll viewport at (0, 0) and pile up as ghosts at the top of the chat.
  // `overflow: hidden` clips the exit slide so it doesn't leak above the row.
  //
  // Entry keys: cards key by workflowId; rows segments by position. Segments
  // only shift when a new workflow card lands between them, so the remount
  // that index-keying implies happens exactly at that boundary and nowhere
  // else (appending rows to the last segment keeps its index).
  if (rolling) {
    return (
      <>
        {entries.map((entry, i) =>
          entry.kind === "workflow" ? (
            <div key={`wf:${entry.workflow.workflowId}`} className="mt-1 space-y-1">
              <ExpandableWorkflowCard workflow={entry.workflow} />
            </div>
          ) : (
            <div key={`rows:${i}`} className="relative overflow-hidden pl-3 mt-0.5">
              <AnimatePresence mode="popLayout" initial={false}>
                {buildRollingList(entry.items, max as number).map((item) => (
                  <motion.div
                    key={item.id}
                    data-activity-motion-row="true"
                    data-motion-suppressed={suppressMotion ? "true" : "false"}
                    layout={suppressMotion ? false : "position"}
                    initial={suppressMotion ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={suppressMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: -8 }}
                    transition={
                      suppressMotion
                        ? { duration: 0 }
                        : { type: "spring", stiffness: 350, damping: 40, mass: 0.8 }
                    }
                    style={{ height: `${ROW_HEIGHT_EM}em` }}
                    className="flex items-center min-w-0"
                  >
                    <ItemButton item={item} onOpen={setViewingTool} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          ),
        )}
      </>
    );
  }

  // Static (post-run) mode: the user-driven collapse toggle is a one-shot
  // event, not a per-frame stream, so animating height here is fine. Every
  // row (tool or agent) is a uniform single line, so an exact em count is
  // both correct and cheaper than measuring to `auto`.
  //
  // Workflow cards are the turn's primary artifact, NOT collapsible tool rows —
  // they stay visible after the run finishes (a finished `onlyWorkflows` turn
  // has no header toggle, so hiding them would leave no way back). The header
  // chevron collapses only the rows segments around them.
  return (
    <>
      {entries.map((entry, i) => {
        if (entry.kind === "workflow") {
          return (
            <div key={`wf:${entry.workflow.workflowId}`} className="mt-1 space-y-1">
              <ExpandableWorkflowCard workflow={entry.workflow} />
            </div>
          );
        }
        const visible = buildStaticTree(entry.items);
        return (
          <motion.div
            key={`rows:${i}`}
            initial={false}
            animate={{
              opacity: collapsed ? 0 : 1,
              height: collapsed ? 0 : `${visible.length * ROW_HEIGHT_EM}em`,
            }}
            transition={suppressMotion ? { duration: 0 } : SPRING_LAYOUT}
            style={{ overflow: "hidden" }}
            className="pl-3 mt-0.5"
          >
            {visible.map((item) => (
              <div
                key={item.id}
                style={{ height: `${ROW_HEIGHT_EM}em` }}
                className="flex items-center min-w-0"
              >
                <ItemButton item={item} onOpen={setViewingTool} />
              </div>
            ))}
          </motion.div>
        );
      })}
    </>
  );
}

/** Static-mode tree: post-run, expanded panel. Emit every item in DFS
 *  order (parent before children). Session-backed child agents are leaves:
 *  their internal tools now live in the child session, not the parent trace. */
function buildStaticTree(items: ActivityItem[]): ActivityItem[] {
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
function buildRollingList(items: ActivityItem[], max: number): ActivityItem[] {
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

function isSessionBackedAgent(item: ActivityItem): boolean {
  return isAgent(item) && !!item.childAgent?.childSessionId;
}

function ItemButton({
  item,
  onOpen,
}: {
  item: ActivityItem;
  onOpen: (item: ActivityItem) => void;
}) {
  const depth = Math.min(item.depth ?? 0, MAX_NEST_DEPTH);
  if (isAgent(item)) {
    return <AgentRow item={item} depth={depth} onOpen={onOpen} />;
  }
  const running = activityItemStatus(item) === "ongoing";
  const errored = !!item.error;
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      title={`${item.target || item.kind} — click to inspect`}
      data-state={running && !errored ? "running" : undefined}
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      // No transition-colors here: when a tool finishes, the shine
      // animation stops and `color: transparent` would otherwise fade
      // to `text-faint` over 150ms — during which the gradient is
      // already gone, leaving the text briefly invisible. The hover
      // color snap is unnoticeable in exchange for no flicker.
      className={clsx(
        "tool-line flex items-baseline gap-1.5 font-mono truncate text-left bg-transparent border-0 p-0 m-0 cursor-pointer",
        errored
          ? "text-bad hover:text-bad"
          : running
            ? "text-ink-soft"
            : "text-faint hover:text-ink-soft",
      )}
    >
      {depth > 0 && (
        <span className="text-whisper select-none" aria-hidden="true">↳</span>
      )}
      <span className="truncate">{item.target || item.kind}</span>
    </button>
  );
}

// One row treatment for every agent in the trace — session-backed sub-agents
// (clickable → open the child session) and inline tool-group agents alike. It's
// a visual peer of the tool rows: same height + rhythm, a Bot glyph (accent
// while running, muted when settled) carrying a stop-on-hover, the name, a faint
// inline progress/result line, and status via the small StatusDot — no card
// chrome, so the stack reads as one coherent list.
function AgentRow({
  item,
  depth,
  onOpen,
}: {
  item: ActivityItem;
  depth: number;
  onOpen: (item: ActivityItem) => void;
}) {
  const run = agentRunFromActivityItem(item);
  const running = isActiveAgentStatus(run.status);
  const childSessionId = run.childSessionId;
  const canStop = item.taskStatus === "running" && !!item.runId && !item.cancelRequested;
  const detail = running ? run.progress : run.resultPreview;
  const terminalBad = run.status === "failed" || run.status === "cancelled";
  return (
    <div
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      className="flex items-center gap-2 min-w-0 group/agent"
    >
      {depth > 0 && (
        <span className="text-whisper select-none" aria-hidden="true">↳</span>
      )}
      <span className="relative grid place-items-center w-[18px] h-[18px] shrink-0">
        <span
          aria-hidden
          className={clsx(
            "grid place-items-center w-[18px] h-[18px] rounded-md transition-opacity",
            running ? "bg-accent-soft text-accent-strong" : "bg-surface-soft text-faint",
            canStop && "group-hover/agent:opacity-0",
          )}
        >
          <Bot size={ICON.XS} strokeWidth={2} />
        </span>
        {canStop && (
          <button
            type="button"
            aria-label="Stop subagent"
            title="Stop subagent"
            onClick={(event) => {
              event.stopPropagation();
              if (item.runId) void cancelSubagent(item.runId, item.id);
            }}
            className="group/stop absolute inset-0 grid place-items-center rounded-md border-0 p-0 m-0 bg-surface-soft text-faint opacity-0 pointer-events-none transition-[opacity,color] group-hover/agent:pointer-events-auto group-hover/agent:opacity-100 hover:text-bad focus-visible:pointer-events-auto focus-visible:opacity-100"
          >
            <Square size={ICON.XS} strokeWidth={2} />
            <span
              aria-hidden
              className="pointer-events-none absolute left-full top-1/2 z-10 ml-1.5 -translate-y-1/2 whitespace-nowrap rounded-md bg-ink px-1.5 py-0.5 text-2xs font-medium leading-none text-on-ink opacity-0 shadow-sm transition-opacity group-hover/stop:opacity-100 group-focus-visible/stop:opacity-100"
            >
              Stop subagent
            </span>
          </button>
        )}
      </span>
      <button
        type="button"
        onClick={() => {
          if (childSessionId) {
            void switchSession(childSessionId);
            return;
          }
          onOpen(item);
        }}
        title={childSessionId ? "Open agent session" : `${item.kind} — click to inspect`}
        data-child-session-id={childSessionId}
        className="flex items-center gap-2 min-w-0 flex-1 text-left bg-transparent border-0 p-0 m-0 cursor-pointer"
      >
        <span
          className={clsx(
            "shrink truncate font-medium max-w-[18rem] group-hover/agent:text-ink transition-colors",
            running ? "text-ink-soft" : terminalBad ? "text-bad" : "text-faint",
          )}
        >
          {run.name}
        </span>
        {detail && (
          <span className={clsx("min-w-0 flex-1 truncate text-faint", running && "italic")}>
            {detail}
          </span>
        )}
      </button>
      <StatusDot status={run.status} pulse={running} />
      {run.elapsedLabel && (
        <span className="shrink-0 text-2xs tabular-nums text-faint">{run.elapsedLabel}</span>
      )}
      {childSessionId && (
        <ArrowUpRight
          size={ICON.XS}
          strokeWidth={2}
          className="shrink-0 text-faint opacity-0 transition-opacity group-hover/agent:opacity-100"
          aria-hidden
        />
      )}
      {item.usage && activityItemStatus(item) === "executed" && !detail && (
        <AgentUsageSuffix tokens={item.usage.total} cost={item.cost} />
      )}
    </div>
  );
}

/** Compact `· 4.2k · $0.03` suffix that hangs off a finished agent row.
 *  Renders only when the subagent reported usage (i.e. it actually ran
 *  LLM calls). Used by the activity trace and the ToolViewer's AgentBody. */
export function AgentUsageSuffix({ tokens, cost }: { tokens: number; cost?: number }) {
  if (tokens <= 0 && !cost) return null;
  const tk =
    tokens < 1000
      ? `${tokens}`
      : tokens < 10000
        ? `${(tokens / 1000).toFixed(1)}k`
        : `${Math.round(tokens / 1000)}k`;
  const ct = cost
    ? cost < 0.01
      ? `$${cost.toFixed(4)}`
      : `$${cost.toFixed(3)}`
    : null;
  return (
    <span className="text-whisper tabular-nums shrink-0" aria-label="Subagent usage">
      · {tk}
      {ct && ` · ${ct}`}
    </span>
  );
}
