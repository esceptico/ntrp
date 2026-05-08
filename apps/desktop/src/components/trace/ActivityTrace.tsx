import { useMemo, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bot, ChevronDown, SquareTerminal } from "lucide-react";
import clsx from "clsx";
import { useStore, type ActivityItem } from "../../store";
import { extractTask, friendlyAgentLabel, isAgent } from "../../lib/agent";
import { MOTION, EASE_EMPHASIZED, SPRING_SMOOTH } from "../../lib/motion";

export type { ActivityItem };

const EASE = EASE_EMPHASIZED;
const ROW_HEIGHT_EM = 1.4;
const NEST_PX = 16;
const MAX_NEST_DEPTH = 4; // visual cap; deeper nesting collapses to the same indent

export function ActivityTrace({ children }: { children: ReactNode }) {
  return (
    <div className="font-sans chat-meta text-muted">{children}</div>
  );
}

export function ActivityHeader({
  label,
  count,
  onToggle,
  expanded,
}: {
  label: string;
  count: number;
  onToggle?: () => void;
  expanded?: boolean;
}) {
  const word = count === 1 ? "tool" : "tools";
  const interactive = !!onToggle;
  const summary = `${label} ${count} ${word}`;

  return (
    <button
      type={interactive ? "button" : undefined}
      onClick={onToggle}
      disabled={!interactive}
      className={clsx(
        "flex h-[18px] items-center gap-2 m-0 p-0 bg-transparent border-0 text-left chat-meta text-faint",
        interactive ? "cursor-pointer hover:text-muted select-none" : "cursor-default",
      )}
    >
      <SquareTerminal size={13} strokeWidth={1.8} className="shrink-0" />
      <span>{summary}</span>
      {interactive && (
        <ChevronDown
          size={12}
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
  animateRows = true,
}: {
  items: ActivityItem[];
  max?: number;
  collapsed?: boolean;
  animateRows?: boolean;
}) {
  // Two render modes:
  //   - "rolling" (max set): used live during a run. Each level (top, plus
  //     each *running* parent's children) keeps its last `max` rows; deeper
  //     descendants of a finished parent are hidden so the tail stays short.
  //     We render the result as a flat ordered list — parents come before
  //     their children, depth handles indent — so motion has only one layout
  //     surface to manage rather than nested motion.divs.
  //   - "static"  (max unset): post-run, expanded list. Flat top-level only —
  //     children are reachable via the inspector.
  const rolling = max != null;
  const setViewingTool = useStore((s) => s.setViewingTool);

  const visible = useMemo(
    () => (rolling ? buildRollingList(items, max as number) : buildStaticTree(items)),
    [items, max, rolling],
  );

  // Compute explicit height instead of leaving it to a `layout` prop on the
  // outer container. Mixing `layout` and an explicit `animate.height` causes
  // the two systems to fight (motion docs warn against this), which produced
  // the visible "jumping" / "wait then batch move" the user reported.
  const targetHeight = `${visible.length * ROW_HEIGHT_EM}em`;

  return (
    <motion.div
      initial={false}
      animate={{
        opacity: collapsed ? 0 : 1,
        height: collapsed ? 0 : targetHeight,
      }}
      transition={SPRING_SMOOTH}
      style={{ overflow: "hidden" }}
      className="pl-3 mt-0.5"
    >
      {rolling && animateRows ? (
        <AnimatePresence mode="popLayout" initial={false}>
          {visible.map((item) => (
            <motion.div
              key={item.id}
              layout
              initial={{ y: 8, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -8, opacity: 0 }}
              transition={{ duration: MOTION.panel, ease: EASE }}
              style={{ height: `${ROW_HEIGHT_EM}em` }}
              className="flex items-baseline min-w-0"
            >
              <ItemButton item={item} onOpen={setViewingTool} />
            </motion.div>
          ))}
        </AnimatePresence>
      ) : (
        visible.map((item) => (
          <div
            key={item.id}
            style={{ height: `${ROW_HEIGHT_EM}em` }}
            className="flex items-baseline min-w-0"
          >
            <ItemButton item={item} onOpen={setViewingTool} />
          </div>
        ))
      )}
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
 *  rolling mode. Each level is capped at `max`; we recurse into a parent's
 *  children only while the parent is still running, so finished agents
 *  don't keep their detail on screen. Parents appear before their kids so
 *  the natural document order doubles as visual hierarchy (depth-based
 *  indent comes from `ItemButton`).
 *
 *  A `seen` set guards the recursion so a malformed tree (cycle, or a
 *  depth-0 row that also points at a parent) can't blow the stack or emit
 *  duplicate React keys. */
function buildRollingList(items: ActivityItem[], max: number): ActivityItem[] {
  const childrenByParent = new Map<string, ActivityItem[]>();
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
    if (item.result == null) {
      const kids = childrenByParent.get(item.id);
      if (kids) for (const k of kids.slice(-max)) include(k);
    }
  };

  const topLevel = items.filter((it) => (it.depth ?? 0) === 0);
  for (const t of topLevel.slice(-max)) include(t);
  return out;
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
  const running = item.result == null;
  const errored = !!item.error;
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      title={`${item.kind} — click to inspect`}
      data-state={running && !errored ? "running" : undefined}
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      className={clsx(
        "tool-line flex items-baseline gap-1.5 font-mono truncate text-left bg-transparent border-0 p-0 m-0 transition-colors cursor-pointer",
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
  const task = useMemo(() => extractTask(item.args), [item.args]);
  const label = friendlyAgentLabel(item.kind);
  const status = item.taskStatus ?? (item.result == null ? "running" : "completed");
  const statusText = item.progress ?? status;
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      title={`${item.kind} — click to inspect`}
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      className="flex items-baseline gap-2 min-w-0 text-left bg-transparent border-0 p-0 m-0 cursor-pointer group/agent"
    >
      {depth > 0 && (
        <span className="text-whisper select-none self-center" aria-hidden="true">↳</span>
      )}
      <span
        aria-hidden
        className="grid place-items-center w-[18px] h-[18px] rounded-md bg-accent-soft text-accent-strong shrink-0 self-center"
      >
        <Bot size={11} strokeWidth={2} />
      </span>
      <span className="font-medium text-ink-soft shrink-0 group-hover/agent:text-ink transition-colors">
        {label}
      </span>
      {task && (
        <span className="text-faint truncate group-hover/agent:text-ink-soft transition-colors">
          {task}
        </span>
      )}
      <span
        className={clsx(
          "text-faint shrink-0 max-w-[9rem] truncate",
          (status === "failed" || status === "cancelled") && "text-bad",
        )}
      >
        {statusText}
      </span>
    </button>
  );
}
