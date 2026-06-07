import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { ChevronDown, Workflow as WorkflowIcon } from "lucide-react";
import { ICON } from "../../lib/icons";
import { EASE_EMPHASIZED, MOTION } from "../../lib/tokens/motion";
import { useTimeTicker } from "../../lib/hooks";
import { formatDuration, type AgentRunStatus } from "../../lib/agentRun";
import { useStore } from "../../store";
import { useWorkflows } from "../../hooks/useWorkflows";
import {
  isActiveWorkflow,
  type Workflow,
  type WorkflowAgent,
  type WorkflowPhase,
} from "../../store/workflow-domain";
import { PageModal } from "../PageModal";
import { Badge, type BadgeTone } from "../Badge";
import { StatusDot } from "../StatusDot";

// The workflow overlay — phases + their agents in collapsible groups. Mirrors
// the app's modal/overlay pattern (PageModal: portal, backdrop, Esc-to-close,
// .surface-panel). The header carries the workflow name, a status badge, a live
// elapsed label, the agent count, and Σ tokens. The body lists phases; each
// phase expands to its agent rows (StatusDot + name + a meta lane of tokens /
// cost / elapsed). Reveal uses MOTION tokens; no flashy effects.

const WORKFLOW_BADGE_TONE: Record<Workflow["status"], BadgeTone> = {
  running: "accent",
  completed: "ok",
  failed: "bad",
};

export function WorkflowPanel() {
  const viewer = useStore((s) => s.workflowViewer);
  const setViewingWorkflow = useStore((s) => s.setViewingWorkflow);
  const workflows = useWorkflows(viewer?.sessionId ?? null);
  const workflow = useMemo(
    () => (viewer ? workflows.find((w) => w.workflowId === viewer.workflowId) : undefined),
    [workflows, viewer],
  );

  const open = !!viewer && !!workflow;

  return (
    <PageModal
      open={open}
      onClose={() => setViewingWorkflow(null)}
      header={
        workflow
          ? {
              title: (
                <span className="flex items-center gap-2">
                  <WorkflowIcon size={ICON.XL} strokeWidth={2} className="shrink-0 text-faint" />
                  <span className="truncate">{workflow.name ?? "Workflow"}</span>
                </span>
              ),
              subtitle: <WorkflowHeaderMeta workflow={workflow} />,
            }
          : undefined
      }
      size="w-[min(640px,calc(100vw-32px))] h-[min(560px,calc(100vh-32px))] sm:w-[min(640px,calc(100vw-80px))] sm:h-[min(560px,calc(100vh-80px))]"
    >
      {workflow && <WorkflowBody workflow={workflow} />}
    </PageModal>
  );
}

function WorkflowHeaderMeta({ workflow }: { workflow: Workflow }) {
  const running = isActiveWorkflow(workflow);
  useTimeTicker(running ? 1000 : 60_000);

  const agentCount = workflow.totalAgents || countAgents(workflow);
  const durationMs = (workflow.completedAt ?? Date.now()) - workflow.startedAt;
  const elapsedLabel = durationMs > 0 ? formatDuration(durationMs) : "";
  const totalTokens = sumTokens(workflow);

  return (
    <span className="flex items-center gap-2 font-sans text-faint normal-case">
      <Badge tone={WORKFLOW_BADGE_TONE[workflow.status]}>{workflow.status}</Badge>
      {elapsedLabel && <span className="tabular-nums">{elapsedLabel}</span>}
      <span>·</span>
      <span className="tabular-nums">
        {agentCount} {plural(agentCount, "agent")}
      </span>
      {totalTokens > 0 && (
        <>
          <span>·</span>
          <span className="tabular-nums">Σ {formatTokens(totalTokens)}</span>
        </>
      )}
    </span>
  );
}

function WorkflowBody({ workflow }: { workflow: Workflow }) {
  const phases = Object.values(workflow.phasesByName);

  return (
    <div className="min-h-0 min-w-0 overflow-y-auto scroll-thin px-5 pb-5">
      {phases.length === 0 ? (
        <div className="grid place-items-center py-10 text-sm text-faint">
          {isActiveWorkflow(workflow)
            ? "Spinning up agents…"
            : "No agents ran in this workflow."}
        </div>
      ) : (
        <div className="space-y-1.5">
          {phases.map((phase) => (
            <PhaseGroup key={phase.name} phase={phase} />
          ))}
        </div>
      )}
    </div>
  );
}

function PhaseGroup({ phase }: { phase: WorkflowPhase }) {
  const agents = Object.values(phase.agentsByTaskId);
  const running = phase.status === "running";
  // Phases default open while running so live work is visible; finished phases
  // collapse to keep a multi-phase workflow scannable.
  const [expanded, setExpanded] = useState(running);

  return (
    <div className="rounded-md border border-line-soft bg-surface-soft overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-transparent border-0 m-0 cursor-pointer hover:bg-surface-sunken transition-colors duration-row"
      >
        <ChevronDown
          size={ICON.XS}
          strokeWidth={2}
          className={clsx(
            "shrink-0 text-faint transition-transform duration-row",
            !expanded && "-rotate-90",
          )}
        />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{phase.name}</span>
        <span className="shrink-0 text-2xs tabular-nums text-faint">
          {agents.length} {plural(agents.length, "agent")}
        </span>
        <StatusDot status={phaseDotStatus(phase.status)} pulse={running} />
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ gridTemplateRows: "0fr", opacity: 0 }}
            animate={{ gridTemplateRows: "1fr", opacity: 1 }}
            exit={{ gridTemplateRows: "0fr", opacity: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
            style={{ display: "grid" }}
            className="border-t border-line-soft"
          >
            <div className="min-h-0 overflow-hidden">
              <div className="px-3 py-1">
                {agents.length === 0 ? (
                  <div className="py-1.5 text-2xs text-faint">No agents yet.</div>
                ) : (
                  agents.map((agent) => <AgentRow key={agent.taskId} agent={agent} />)
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AgentRow({ agent }: { agent: WorkflowAgent }) {
  const running = agent.status === "running" || agent.status === "cancel_requested";
  useTimeTicker(running ? 1000 : 60_000);

  const durationMs =
    agent.durationMs ?? (running ? Date.now() - agent.startedAt : undefined);
  const elapsedLabel = durationMs != null && durationMs > 0 ? formatDuration(durationMs) : "";
  const tokens = agent.tokens?.total ?? 0;

  return (
    <div className="flex items-center gap-2 min-w-0 py-1 text-xs">
      <StatusDot status={agent.status} pulse={running} />
      <span
        className={clsx(
          "min-w-0 flex-1 truncate",
          running ? "text-ink-soft" : agent.status === "failed" ? "text-bad" : "text-muted",
        )}
      >
        {agent.name ?? agent.taskId}
      </span>
      <span className="shrink-0 flex items-center gap-1.5 tabular-nums text-faint">
        {elapsedLabel && <span>{elapsedLabel}</span>}
        {tokens > 0 && <span>· {formatTokens(tokens)}</span>}
        {agent.cost != null && agent.cost > 0 && <span>· {formatCost(agent.cost)}</span>}
      </span>
    </div>
  );
}

function phaseDotStatus(status: WorkflowPhase["status"]): AgentRunStatus {
  switch (status) {
    case "running":
      return "running";
    case "completed":
      return "completed";
    case "failed":
      return "failed";
    default:
      return "interrupted"; // pending → muted
  }
}

function countAgents(workflow: Workflow): number {
  let n = 0;
  for (const phase of Object.values(workflow.phasesByName)) {
    n += Object.keys(phase.agentsByTaskId).length;
  }
  return n;
}

function sumTokens(workflow: Workflow): number {
  let total = 0;
  for (const phase of Object.values(workflow.phasesByName)) {
    for (const agent of Object.values(phase.agentsByTaskId)) {
      total += agent.tokens?.total ?? 0;
    }
  }
  return total;
}

function formatTokens(total: number): string {
  if (total < 1000) return `${total}`;
  if (total < 10_000) return `${(total / 1000).toFixed(1)}k`;
  return `${Math.round(total / 1000)}k`;
}

function formatCost(cost: number): string {
  return cost < 0.01 ? `$${cost.toFixed(4)}` : `$${cost.toFixed(3)}`;
}

function plural(n: number, word: string): string {
  return n === 1 ? word : `${word}s`;
}
