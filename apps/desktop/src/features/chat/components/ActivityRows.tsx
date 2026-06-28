import { ArrowUpRight, Bot, Square } from "lucide-react";
import clsx from "clsx";
import type { ActivityItem } from "@/stores";
import { activityItemStatus, isAgent } from "@/lib/agent";
import { switchSession } from "@/actions/sessions";
import { cancelSubagent } from "@/actions/messages";
import { ICON } from "@/lib/icons";
import { StatusDot } from "@/components/ui/StatusDot";
import { ThinkingStep } from "@/components/ui/ThinkingStep";
import { Tooltip } from "@/components/ui/Tooltip";
import { operationLabel } from "@/features/chat/lib/operationLabel";
import { agentRunFromActivityItem, isActiveAgentStatus } from "@/lib/agentRun";
import { MAX_NEST_DEPTH, NEST_PX } from "@/features/chat/lib/trace";

type RowProps = {
  item: ActivityItem;
  onOpen: (item: ActivityItem) => void;
  first?: boolean;
  last?: boolean;
};

export function ItemButton({ item, onOpen, first, last }: RowProps) {
  const depth = Math.min(item.depth ?? 0, MAX_NEST_DEPTH);
  if (isAgent(item)) {
    return <AgentRow item={item} depth={depth} onOpen={onOpen} first={first} last={last} />;
  }
  const running = activityItemStatus(item) === "ongoing";
  const errored = !!item.error;
  const { verb, detail } = operationLabel(item);
  return (
    <ThinkingStep
      first={first}
      last={last}
      node={<ToolDot running={running} errored={errored} />}
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
    >
      <button
        type="button"
        onClick={() => onOpen(item)}
        title={`${item.target || item.kind} — click to inspect`}
        data-state={running && !errored ? "running" : undefined}
        // No transition-colors here: when a tool finishes, the shine
        // animation stops and `color: transparent` would otherwise fade
        // to `text-faint` over 150ms — during which the gradient is
        // already gone, leaving the text briefly invisible. The hover
        // color snap is unnoticeable in exchange for no flicker.
        className={clsx(
          "tool-line flex items-baseline gap-1.5 truncate text-left bg-transparent border-0 p-0 m-0 cursor-pointer",
          errored
            ? "text-bad hover:text-bad"
            : running
              ? "text-ink-soft"
              : "text-faint hover:text-ink-soft",
        )}
      >
        <span className="truncate font-medium">{verb}</span>
        {detail && <span className="truncate font-mono text-faint">{detail}</span>}
      </button>
    </ThinkingStep>
  );
}

// Spine node for an ordinary tool step: a status dot threaded by the timeline.
// Lives outside the `.tool-line` button so the running-shine rule (which forces
// `background: inherit` on every descendant) can't erase the dot's colour.
function ToolDot({ running, errored }: { running: boolean; errored: boolean }) {
  if (running) return <StatusDot tone="accent" pulse />;
  if (errored) return <StatusDot tone="bad" />;
  return <StatusDot tone="neutral" />;
}

// One row treatment for every agent in the trace — session-backed sub-agents
// (clickable → open the child session) and inline tool-group agents alike. It's
// a visual peer of the tool rows: same height + rhythm, a Bot glyph (accent
// while running, muted when settled) carrying a stop-on-hover as the spine node,
// the name, a faint inline progress/result line, and status via the small
// StatusDot — no card chrome, so the stack reads as one coherent timeline.
function AgentRow({
  item,
  depth,
  onOpen,
  first,
  last,
}: {
  item: ActivityItem;
  depth: number;
  onOpen: (item: ActivityItem) => void;
  first?: boolean;
  last?: boolean;
}) {
  const run = agentRunFromActivityItem(item);
  const running = isActiveAgentStatus(run.status);
  const childSessionId = run.childSessionId;
  const canStop = item.taskStatus === "running" && !!item.runId && !item.cancelRequested;
  const detail = running ? run.progress : run.resultPreview;
  const terminalBad = run.status === "failed" || run.status === "cancelled";
  return (
    <ThinkingStep
      first={first}
      last={last}
      className="group/agent"
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      node={
        <span className="relative grid h-[18px] w-[18px] place-items-center">
          <span
            aria-hidden
            className={clsx(
              "grid h-[18px] w-[18px] place-items-center rounded-md transition-opacity duration-row ease-out",
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
      }
    >
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
    </ThinkingStep>
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
