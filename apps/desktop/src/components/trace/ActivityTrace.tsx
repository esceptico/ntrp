import { useMemo, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bot, ChevronDown, Square, SquareTerminal } from "lucide-react";
import clsx from "clsx";
import { useStore, type ActivityItem, type ActivityLabel } from "../../store";
import { activityItemStatus, friendlyAgentLabel, isAgent } from "../../lib/agent";
import { cancelSubagent } from "../../actions";
// Collapse/expand height shift on the trace — layout-style settle, not a modal entry.
import { SPRING_LAYOUT } from "../../lib/tokens/motion";
import { RollingToken } from "./RollingToken";
import { ICON } from "../../lib/icons";

export type { ActivityItem };

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
            "ml-1 self-center transition-transform duration-200 text-faint",
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

  const visible = useMemo(
    () => (rolling ? buildRollingList(items, max as number) : buildStaticTree(items)),
    [items, max, rolling],
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
  if (rolling) {
    return (
      <div className="relative overflow-hidden pl-3 mt-0.5">
        <AnimatePresence mode="popLayout" initial={false}>
          {visible.map((item) => (
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
              className="flex items-baseline min-w-0"
            >
              <ItemButton item={item} onOpen={setViewingTool} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    );
  }

  // Static (post-run) mode: the user-driven collapse toggle is a one-shot
  // event, not a per-frame stream, so animating height here is fine.
  const targetHeight = `${visible.length * ROW_HEIGHT_EM}em`;
  return (
    <motion.div
      initial={false}
      animate={{
        opacity: collapsed ? 0 : 1,
        height: collapsed ? 0 : targetHeight,
      }}
      transition={suppressMotion ? { duration: 0 } : SPRING_LAYOUT}
      style={{ overflow: "hidden" }}
      className="pl-3 mt-0.5"
    >
      {visible.map((item) => (
        <div
          key={item.id}
          style={{ height: `${ROW_HEIGHT_EM}em` }}
          className="flex items-baseline min-w-0"
        >
          <ItemButton item={item} onOpen={setViewingTool} />
        </div>
      ))}
    </motion.div>
  );
}

/** Static-mode tree: post-run, expanded panel. Emit every item in DFS
 *  order (parent before children). The user wants to see what tools the
 *  sub-agent ran without clicking into the agent card — depth-based
 *  indent in `ItemButton` handles the visual hierarchy. */
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
    const kids = childrenByParent.get(item.id);
    if (kids) for (const k of kids) visit(k);
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
    if (activityItemStatus(item) === "ongoing") {
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

function ItemButton({
  item,
  onOpen,
}: {
  item: ActivityItem;
  onOpen: (item: ActivityItem) => void;
}) {
  const depth = Math.min(item.depth ?? 0, MAX_NEST_DEPTH);
  if (isAgent(item)) {
    return <AgentButton item={item} depth={depth} onOpen={onOpen} />;
  }
  const running = activityItemStatus(item) === "ongoing";
  const errored = !!item.error;
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      title={`${item.kind} — click to inspect`}
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

function AgentButton({
  item,
  depth,
  onOpen,
}: {
  item: ActivityItem;
  depth: number;
  onOpen: (item: ActivityItem) => void;
}) {
  const label = item.displayName ?? friendlyAgentLabel(item.kind);
  const traceStatus = activityItemStatus(item);
  const running = traceStatus === "ongoing";
  const status = item.taskStatus ?? (traceStatus === "ongoing" ? "running" : traceStatus);
  const statusText = item.progress ?? status;
  const canStop = item.taskStatus === "running" && !!item.runId && !item.cancelRequested;
  return (
    <div
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      className="flex items-baseline gap-2 min-w-0 group/agent"
    >
      {depth > 0 && (
        <span className="text-whisper select-none self-center" aria-hidden="true">↳</span>
      )}
      <span className="relative grid place-items-center w-[18px] h-[18px] shrink-0 self-center">
        <span
          aria-hidden
          className={clsx(
            "grid place-items-center w-[18px] h-[18px] rounded-md bg-accent-soft text-accent-strong transition-opacity",
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
        onClick={() => onOpen(item)}
        title={`${item.kind} — click to inspect`}
        className="flex items-baseline gap-2 min-w-0 text-left bg-transparent border-0 p-0 m-0 cursor-pointer"
      >
        <span
          className={clsx(
            "font-medium shrink-0 group-hover/agent:text-ink transition-colors",
            running ? "text-ink-soft" : "text-faint",
          )}
        >
          {label}
        </span>
        <span
          className={clsx(
            "text-faint shrink-0 max-w-[9rem] truncate",
            (status === "failed" || status === "cancelled") && "text-bad",
          )}
        >
          {statusText}
        </span>
      </button>
      {item.usage && traceStatus === "executed" && (
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
