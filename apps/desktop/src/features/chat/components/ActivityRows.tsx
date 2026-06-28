import { ArrowUpRight, Bot, Square } from "lucide-react";
import clsx from "clsx";
import type { ActivityItem } from "@/stores";
import { activityItemStatus, isAgent } from "@/lib/agent";
import { switchSession } from "@/actions/sessions";
import { cancelSubagent } from "@/actions/messages";
import { ICON } from "@/lib/icons";
import { StatusDot } from "@/components/ui/StatusDot";
import { Tooltip } from "@/components/ui/Tooltip";
import { agentRunFromActivityItem, isActiveAgentStatus } from "@/lib/agentRun";
import { MAX_NEST_DEPTH, NEST_PX } from "@/features/chat/lib/trace";

export function ItemButton({
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
            "grid place-items-center w-[18px] h-[18px] rounded-md transition-opacity duration-row ease-out",
            running ? "bg-accent-soft text-accent-strong" : "bg-surface-soft text-faint",
            canStop && "group-hover/agent:opacity-0",
          )}
        >
          <Bot size={ICON.XS} strokeWidth={2} />
        </span>
        {canStop && (
          <Tooltip label="Stop subagent" side="right">
            <button
              type="button"
              aria-label="Stop subagent"
              onClick={(event) => {
                event.stopPropagation();
                if (item.runId) void cancelSubagent(item.runId, item.id);
              }}
              className="absolute inset-0 grid place-items-center rounded-md border-0 p-0 m-0 bg-surface-soft text-faint opacity-0 pointer-events-none transition-[opacity,color] duration-row ease-out group-hover/agent:pointer-events-auto group-hover/agent:opacity-100 hover:text-bad focus-visible:pointer-events-auto focus-visible:opacity-100"
            >
              <Square size={ICON.XS} strokeWidth={2} />
            </button>
          </Tooltip>
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
            "shrink truncate font-medium max-w-[18rem] group-hover/agent:text-ink transition-colors duration-row ease-out",
            running ? "text-ink-soft" : terminalBad ? "text-bad" : "text-faint",
          )}
        >
          {run.name}
        </span>
        {detail && (
          <span className={clsx("min-w-0 flex-1 truncate text-muted", running && "italic")}>
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
          className="shrink-0 text-faint opacity-0 transition-opacity duration-row ease-out group-hover/agent:opacity-100"
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
