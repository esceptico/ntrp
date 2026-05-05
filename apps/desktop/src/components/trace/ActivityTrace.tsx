import { useMemo, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bot, ChevronDown } from "lucide-react";
import clsx from "clsx";
import { RollingToken } from "./RollingToken";
import { useStore, type ActivityItem } from "../../store";
import { isAgent } from "../../lib/agent";

export type { ActivityItem };

const EASE = [0.32, 0.72, 0, 1] as const;
const ROW_HEIGHT_EM = 1.55;
const NEST_PX = 16;
const MAX_NEST_DEPTH = 4; // visual cap; deeper nesting collapses to the same indent

export function ActivityTrace({ children }: { children: ReactNode }) {
  return (
    <motion.div
      layout
      transition={{ layout: { duration: 0.22, ease: EASE } }}
      className="font-sans text-[13px] leading-[1.55] text-muted"
    >
      {children}
    </motion.div>
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

  return (
    <button
      type={interactive ? "button" : undefined}
      onClick={onToggle}
      disabled={!interactive}
      className={clsx(
        "flex items-baseline gap-1 m-0 p-0 bg-transparent border-0 text-left",
        interactive ? "cursor-pointer hover:opacity-70 select-none" : "cursor-default",
      )}
    >
      <span className="font-medium text-ink-soft mr-1.5">
        <RollingToken value={label} />
      </span>
      <span>
        <RollingToken value={String(count)} mono />
        {" "}
        <RollingToken value={word} />
      </span>
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
}: {
  items: ActivityItem[];
  max?: number;
  collapsed?: boolean;
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

  const visible = rolling
    ? buildRollingList(items, max)
    : items.filter((it) => (it.depth ?? 0) === 0);

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
      transition={{ duration: 0.24, ease: EASE }}
      style={{ overflow: "hidden" }}
      className="pl-4 mt-0.5"
    >
      {rolling ? (
        <AnimatePresence mode="popLayout" initial={false}>
          {visible.map((item) => (
            <motion.div
              key={item.id}
              layout
              initial={{ y: 8, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -8, opacity: 0 }}
              transition={{ duration: 0.22, ease: EASE }}
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
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      title={`${item.kind} — click to inspect`}
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      className="flex items-baseline gap-1.5 font-mono text-faint truncate text-left bg-transparent border-0 p-0 m-0 hover:text-ink-soft transition-colors cursor-pointer"
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
    </button>
  );
}

function extractTask(args: string | undefined): string | null {
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

function friendlyAgentLabel(toolName: string): string {
  // "research" → "Research", "research_agent" → "Research"
  const stripped = toolName.replace(/_agent$/i, "");
  if (!stripped) return toolName;
  return stripped[0].toUpperCase() + stripped.slice(1);
}
