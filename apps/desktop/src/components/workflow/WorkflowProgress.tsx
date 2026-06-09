import clsx from "clsx";
import { ChevronRight, Workflow as WorkflowIcon } from "lucide-react";
import { ICON } from "../../lib/icons";
import { useTimeTicker } from "../../lib/hooks";
import { formatDuration } from "../../lib/agentRun";
import {
  isActiveWorkflow,
  type Workflow,
  type WorkflowAgent,
  type WorkflowPhaseStatus,
} from "../../store/workflow-domain";
import { Badge, type BadgeTone } from "../Badge";

// Shared workflow presentation. Both the activity-trace chip and the sidebar hub
// render WorkflowProgressCard; the overlay (WorkflowPanel) reuses the helpers, so
// a workflow reads as the same object at two zoom levels. Status is carried by
// glyph tone, badge, and segment color — no decorative rails.

export const WORKFLOW_BADGE_TONE: Record<Workflow["status"], BadgeTone> = {
  running: "accent",
  completed: "ok",
  failed: "bad",
  cancelled: "neutral",
};

export function pipClass(status: WorkflowAgent["status"]): string {
  if (status === "completed") return "bg-ok";
  if (status === "failed") return "bg-bad";
  if (status === "cancelled" || status === "interrupted") return "bg-faint";
  return "bg-accent"; // running / cancel_requested
}

export function phaseSegmentClass(status: WorkflowPhaseStatus): string {
  if (status === "completed") return "bg-ok";
  if (status === "failed") return "bg-bad";
  if (status === "running") return "bg-accent";
  return "bg-surface-sunken"; // pending
}

const TERMINAL_AGENT = new Set<WorkflowAgent["status"]>([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

export function countAgents(workflow: Workflow): number {
  let n = 0;
  for (const phase of Object.values(workflow.phasesByName)) {
    n += Object.keys(phase.agentsByTaskId).length;
  }
  return n;
}

function settledAgents(workflow: Workflow): number {
  let n = 0;
  for (const phase of Object.values(workflow.phasesByName)) {
    for (const agent of Object.values(phase.agentsByTaskId)) {
      if (TERMINAL_AGENT.has(agent.status)) n += 1;
    }
  }
  return n;
}

export function sumTokens(workflow: Workflow): number {
  let total = 0;
  for (const phase of Object.values(workflow.phasesByName)) {
    for (const agent of Object.values(phase.agentsByTaskId)) {
      total += agent.tokens?.total ?? 0;
    }
  }
  return total;
}

export function formatTokens(total: number): string {
  if (total < 1000) return `${total}`;
  if (total < 10_000) return `${(total / 1000).toFixed(1)}k`;
  return `${Math.round(total / 1000)}k`;
}

export function plural(n: number, word: string): string {
  return n === 1 ? word : `${word}s`;
}

export function PhaseSparkline({ agents }: { agents: WorkflowAgent[] }) {
  if (agents.length === 0) return null;
  return (
    <span className="flex items-center gap-[3px] shrink-0" aria-hidden>
      {agents.map((agent) => (
        <span key={agent.taskId} className={clsx("w-[5px] h-[5px] rounded-full", pipClass(agent.status))} />
      ))}
    </span>
  );
}

function statusWord(status: Workflow["status"]): string {
  return status === "cancelled" ? "stopped" : status;
}

// A compact inline progress card: identity + status + meta on line 1, a
// segmented phase bar (one segment per phase, colored by phase status) plus an
// agent-completion fraction on line 2. In the hub it expands in place (see
// `expanded`); from the chat it opens the hub focused on this workflow.
export function WorkflowProgressCard({
  workflow,
  onOpen,
  expanded,
}: {
  workflow: Workflow;
  onOpen: () => void;
  /** When provided, the chevron is an expand-in-place toggle (sidebar); when
   *  omitted, it's a static "open" affordance (chat trace). */
  expanded?: boolean;
}) {
  const running = isActiveWorkflow(workflow);
  // Tick while running so elapsed stays live; settled runs barely tick.
  useTimeTicker(running ? 1000 : 60_000);

  const phases = Object.values(workflow.phasesByName);
  const total = workflow.totalAgents || countAgents(workflow);
  const done = settledAgents(workflow);
  const durationMs = (workflow.completedAt ?? Date.now()) - workflow.startedAt;
  const elapsedLabel = durationMs > 0 ? formatDuration(durationMs) : "";
  const totalTokens = sumTokens(workflow);

  // Stats live on line 2 with the progress bar so line 1 is pure identity and
  // the name keeps its room in the narrow (~268px) sidebar.
  const meta = [
    elapsedLabel || null,
    totalTokens > 0 ? `Σ ${formatTokens(totalTokens)}` : null,
    total > 0 ? `${done}/${total}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={onOpen}
      title={`${workflow.name ?? "Workflow"} — open`}
      className="group/workflow flex w-full flex-col gap-1.5 rounded-md border border-line-soft bg-surface-soft px-2.5 py-2 text-left cursor-pointer transition-colors hover:border-line hover:bg-surface-sunken"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span
          aria-hidden
          className={clsx(
            "grid place-items-center w-5 h-5 shrink-0 rounded-md",
            running ? "bg-accent-soft text-accent-strong" : "bg-surface-sunken text-faint",
          )}
        >
          <WorkflowIcon size={ICON.SM} strokeWidth={2} />
        </span>
        <span
          className={clsx(
            "min-w-0 flex-1 truncate font-medium",
            running ? "text-ink" : workflow.status === "failed" ? "text-bad" : "text-muted",
          )}
        >
          {workflow.name ?? "Workflow"}
        </span>
        <Badge size="sm" tone={WORKFLOW_BADGE_TONE[workflow.status]}>
          {statusWord(workflow.status)}
        </Badge>
        <ChevronRight
          size={ICON.XS}
          strokeWidth={2}
          className={clsx(
            "shrink-0 text-faint transition-transform group-hover/workflow:text-muted",
            expanded && "rotate-90 text-muted", // expanded-in-place (sidebar) → points down
          )}
          aria-hidden
        />
      </div>
      {(phases.length > 0 || meta) && (
        <div className="flex items-center gap-2.5">
          {phases.length > 0 ? (
            <span className="flex flex-1 items-center gap-[2px]" aria-hidden>
              {phases.map((phase) => (
                <span
                  key={phase.name}
                  className={clsx("h-[3px] flex-1 min-w-[2px] rounded-full", phaseSegmentClass(phase.status))}
                />
              ))}
            </span>
          ) : (
            <span className="flex-1" />
          )}
          {meta && <span className="shrink-0 text-2xs tabular-nums text-faint">{meta}</span>}
        </div>
      )}
    </button>
  );
}
