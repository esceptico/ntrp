import {
  ArrowUpRight,
  Bot,
  Brain,
  FileText,
  FilePlus2,
  FolderOpen,
  Globe,
  ListChecks,
  type LucideIcon,
  PenLine,
  Search,
  Square,
  Terminal,
} from "lucide-react";
import clsx from "clsx";
import type { ActivityItem } from "@/stores";
import { activityItemStatus, isAgent } from "@/lib/agent";
import { switchSession } from "@/actions/sessions";
import { cancelSubagent } from "@/actions/messages";
import { ICON } from "@/lib/icons";
import { Badge } from "@/components/ui/Badge";
import { StatusDot } from "@/components/ui/StatusDot";
import { ThinkingStep } from "@/components/ui/ThinkingStep";
import { Tooltip } from "@/components/ui/Tooltip";
import { operationLabel, stepSources, type StepIconKey } from "@/features/chat/lib/operationLabel";
import { agentRunFromActivityItem, isActiveAgentStatus } from "@/lib/agentRun";
import { MAX_NEST_DEPTH, NEST_PX } from "@/features/chat/lib/trace";

type RowProps = {
  item: ActivityItem;
  onOpen: (item: ActivityItem) => void;
  last?: boolean;
};

const ICON_BY_KEY: Record<Exclude<StepIconKey, null>, LucideIcon> = {
  search: Search,
  globe: Globe,
  folder: FolderOpen,
  file: FileText,
  edit: PenLine,
  "file-plus": FilePlus2,
  terminal: Terminal,
  brain: Brain,
  list: ListChecks,
};

// Semantic step glyph: a lucide icon for known operations, else a plain
// timeline dot. Colour comes from the gutter (text-muted) via currentColor;
// errors tint red. Lives in the gutter, OUTSIDE the label, so the running
// label-shimmer never masks it.
function StepGlyph({ iconKey, errored }: { iconKey: StepIconKey; errored: boolean }) {
  if (!iconKey) {
    return <span className={clsx("block h-1.5 w-1.5 rounded-full", errored ? "bg-bad" : "bg-faint")} />;
  }
  const Icon = ICON_BY_KEY[iconKey];
  return <Icon size={14} strokeWidth={1.5} className={errored ? "text-bad" : undefined} />;
}

export function ItemButton({ item, onOpen, last }: RowProps) {
  const depth = Math.min(item.depth ?? 0, MAX_NEST_DEPTH);
  if (isAgent(item)) {
    return <AgentRow item={item} depth={depth} onOpen={onOpen} last={last} />;
  }
  const running = activityItemStatus(item) === "ongoing";
  const errored = !!item.error;
  const { verb, detail, iconKey } = operationLabel(item);
  const sources = stepSources(item);

  return (
    <ThinkingStep
      node={<StepGlyph iconKey={iconKey} errored={errored} />}
      last={last}
      className="rounded-lg px-1.5 py-1.5 transition-colors hover:bg-surface-soft/60"
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
    >
      <button
        type="button"
        onClick={() => onOpen(item)}
        title={`${item.target || item.kind} — click to inspect`}
        className="flex w-full min-w-0 flex-col gap-1 border-0 bg-transparent p-0 text-left cursor-pointer"
      >
        <span
          className={clsx(
            "truncate font-medium",
            errored ? "text-bad" : running ? "step-shimmer" : "text-ink",
          )}
        >
          {verb}
          {running && "…"}
        </span>
        {detail && <span className="truncate text-[13px] text-muted leading-snug">{detail}</span>}
      </button>
      {sources.length > 0 && (
        <span className="mt-1.5 flex flex-wrap gap-1.5">
          {sources.map((s) => (
            <Badge key={s} tone="neutral" size="sm" shape="pill">
              {s}
            </Badge>
          ))}
        </span>
      )}
    </ThinkingStep>
  );
}

// One row treatment for every agent in the trace — session-backed sub-agents
// (clickable → open the child session) and inline tool-group agents alike. A Bot
// glyph (accent while running, muted when settled) is the timeline node and
// carries a stop-on-hover; the name + a faint inline progress/result line + the
// StatusDot read as one coherent step.
function AgentRow({
  item,
  depth,
  onOpen,
  last,
}: {
  item: ActivityItem;
  depth: number;
  onOpen: (item: ActivityItem) => void;
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
      last={last}
      className="group/agent rounded-lg px-1.5 py-1.5 transition-colors hover:bg-surface-soft/60"
      style={depth > 0 ? { paddingLeft: depth * NEST_PX } : undefined}
      node={
        <span className="relative grid h-4 w-4 place-items-center">
          <span
            aria-hidden
            className={clsx(
              "grid h-4 w-4 place-items-center rounded-md transition-opacity duration-row ease-out",
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
      {/* Content column: name line + progress line, gap-1 to match tool rows. */}
      <span className="flex min-w-0 flex-col gap-1">
      {/* Name line: peer of a tool's label, with status/elapsed/cost trailing. */}
      <span className="flex min-w-0 items-center gap-2">
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
          className="flex min-w-0 items-center gap-1.5 text-left bg-transparent border-0 p-0 m-0 cursor-pointer"
        >
          <span
            className={clsx(
              "truncate font-medium group-hover/agent:text-ink transition-colors duration-row ease-out",
              running ? "step-shimmer" : terminalBad ? "text-bad" : "text-ink",
            )}
          >
            {run.name}
          </span>
          {childSessionId && (
            <ArrowUpRight
              size={ICON.XS}
              strokeWidth={2}
              className="shrink-0 text-faint opacity-0 transition-opacity duration-row ease-out group-hover/agent:opacity-100"
              aria-hidden
            />
          )}
        </button>
        <StatusDot status={run.status} pulse={running} />
        {run.elapsedLabel && (
          <span className="shrink-0 text-2xs tabular-nums text-faint">{run.elapsedLabel}</span>
        )}
        {item.usage && activityItemStatus(item) === "executed" && !detail && (
          <AgentUsageSuffix tokens={item.usage.total} cost={item.cost} />
        )}
      </span>
      {/* Progress / result line: the agent's "description". */}
      {detail && (
        <span className={clsx("min-w-0 truncate text-[13px] text-muted leading-snug", running && "italic")}>
          {detail}
        </span>
      )}
      </span>
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
