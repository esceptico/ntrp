import clsx from "clsx";
import { ArrowUpRight, Workflow as WorkflowIcon } from "lucide-react";
import { ICON } from "../../lib/icons";
import { useTimeTicker } from "../../lib/hooks";
import { formatDuration, type AgentRunStatus } from "../../lib/agentRun";
import { StatusDot } from "../StatusDot";
import { isActiveWorkflow, type Workflow } from "../../store/workflow-domain";

// One dense, borderless trace row for a workflow tool call — a visual peer of
// the activity trace's AgentRow (same height + rhythm). A status-toned glyph,
// the workflow name, an inline "N phases · M agents · status" meta lane, the
// small StatusDot, a live elapsed label, and an open affordance on hover. The
// whole row is the click target; clicking opens the WorkflowPanel overlay.

const WORKFLOW_STATUS_TONE: Record<Workflow["status"], AgentRunStatus> = {
  running: "running",
  completed: "completed",
  failed: "failed",
};

export function WorkflowPreviewRow({
  workflow,
  onOpen,
}: {
  workflow: Workflow;
  onOpen: () => void;
}) {
  const running = isActiveWorkflow(workflow);
  // Tick once a second while running so the elapsed label stays live; finished
  // workflows have a fixed duration and don't need the timer.
  useTimeTicker(running ? 1000 : 60_000);

  const phaseCount = Object.keys(workflow.phasesByName).length;
  const agentCount = workflow.totalAgents || countAgents(workflow);
  const durationMs = (workflow.completedAt ?? Date.now()) - workflow.startedAt;
  const elapsedLabel = durationMs > 0 ? formatDuration(durationMs) : "";
  const dotStatus = WORKFLOW_STATUS_TONE[workflow.status];

  const meta = [
    phaseCount > 0 ? `${phaseCount} ${plural(phaseCount, "phase")}` : null,
    `${agentCount} ${plural(agentCount, "agent")}`,
    workflow.status,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={onOpen}
      title={`${workflow.name ?? "Workflow"} — click to open`}
      className="group/workflow flex items-center gap-2 min-w-0 w-full text-left bg-transparent border-0 p-0 m-0 cursor-pointer"
    >
      <span
        aria-hidden
        className={clsx(
          "grid place-items-center w-[18px] h-[18px] shrink-0 rounded-md",
          running ? "bg-accent-soft text-accent-strong" : "bg-surface-soft text-faint",
        )}
      >
        <WorkflowIcon size={ICON.XS} strokeWidth={2} />
      </span>
      <span
        className={clsx(
          "shrink truncate font-medium max-w-[16rem] group-hover/workflow:text-ink transition-colors",
          running ? "text-ink-soft" : workflow.status === "failed" ? "text-bad" : "text-faint",
        )}
      >
        {workflow.name ?? "Workflow"}
      </span>
      <span className="min-w-0 flex-1 truncate text-faint">{meta}</span>
      <StatusDot status={dotStatus} pulse={running} />
      {elapsedLabel && (
        <span className="shrink-0 text-2xs tabular-nums text-faint">{elapsedLabel}</span>
      )}
      <ArrowUpRight
        size={ICON.XS}
        strokeWidth={2}
        className="shrink-0 text-faint opacity-0 transition-opacity group-hover/workflow:opacity-100"
        aria-hidden
      />
    </button>
  );
}

function countAgents(workflow: Workflow): number {
  let n = 0;
  for (const phase of Object.values(workflow.phasesByName)) {
    n += Object.keys(phase.agentsByTaskId).length;
  }
  return n;
}

function plural(n: number, word: string): string {
  return n === 1 ? word : `${word}s`;
}
