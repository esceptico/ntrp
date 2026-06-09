import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { ChevronDown, Code2 } from "lucide-react";
import { ICON } from "../../lib/icons";
import { EASE_EMPHASIZED, MOTION } from "../../lib/tokens/motion";
import { useTimeTicker, useTimeoutFlag } from "../../lib/hooks";
import { formatDuration } from "../../lib/agentRun";
import { switchSession } from "../../actions";
import { useStore } from "../../store";
import { highlight } from "../../highlight";
import { CopyGlyph } from "../CopyGlyph";
import { isActiveWorkflow, type Workflow, type WorkflowAgent, type WorkflowPhase } from "../../store/workflow-domain";
import { formatTokens, PhaseSparkline, WorkflowProgressCard } from "./WorkflowProgress";

// A workflow card that expands IN PLACE to reveal its phases → agents — used in
// both the chat trace and the sidebar hub, each with its own local expand state.
// Clicking an agent opens its session (live tool calls).
export function ExpandableWorkflowCard({ workflow }: { workflow: Workflow }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <WorkflowProgressCard
        workflow={workflow}
        expanded={expanded}
        onOpen={() => setExpanded((v) => !v)}
      />
      {expanded && (
        <>
          <WorkflowDetail workflow={workflow} onOpenAgent={(sid) => void switchSession(sid)} />
          <WorkflowSource parentToolCallId={workflow.parentToolCallId} />
        </>
      )}
    </>
  );
}

// The Python script the agent authored for this dynamic workflow lives in the
// `workflow` tool call's args — not in the streamed domain events — so we resolve
// it from the matching activity item by the workflow's parentToolCallId. Same
// lookup the ToolViewer uses; works in both the trace and the sidebar since both
// render through ExpandableWorkflowCard. Returns the raw args string (a value-
// stable primitive, so Zustand won't re-render on unrelated updates) for the
// caller to parse.
function useWorkflowArgs(parentToolCallId: string | undefined): string | undefined {
  return useStore((s) => {
    if (!parentToolCallId) return undefined;
    for (const msg of s.messages.values()) {
      if (!msg.activity) continue;
      const found = msg.activity.items.find((it) => it.id === parentToolCallId);
      if (found) return found.args;
    }
    return undefined;
  });
}

function parseScript(args: string | undefined): string | null {
  if (!args) return null;
  try {
    const parsed = JSON.parse(args);
    if (typeof parsed?.script === "string" && parsed.script.trim()) return parsed.script;
  } catch {
    // args still streaming / not yet valid JSON — no source to show yet.
  }
  return null;
}

const SOURCE_PRE_CLASS =
  "hljs mt-1 mx-1.5 mb-0.5 p-2.5 rounded-lg bg-code-bg border border-line-soft text-xs leading-[1.55] " +
  "text-ink-soft font-mono whitespace-pre max-h-[40vh] min-w-0 max-w-full overflow-auto scroll-thin";

// A collapsible "Source" disclosure that reveals the exact Python the agent
// authored for this workflow run, syntax-highlighted. Only mounts while the card
// is expanded, so the store scan in useWorkflowArgs is bounded to open cards.
function WorkflowSource({ parentToolCallId }: { parentToolCallId?: string }) {
  const args = useWorkflowArgs(parentToolCallId);
  const script = useMemo(() => parseScript(args), [args]);
  const html = useMemo(() => (script ? highlight(script, "python") : ""), [script]);
  const [open, setOpen] = useState(false);
  const [copied, flashCopied] = useTimeoutFlag(1200);
  if (!script) return null;

  const onCopy = async () => {
    if (await window.ntrpDesktop?.clipboard?.writeText(script)) flashCopied();
  };

  return (
    <div className="mt-1">
      <div className="flex items-center gap-1.5 px-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="group/src flex min-w-0 flex-1 items-center gap-1.5 py-0.5 text-left bg-transparent border-0 cursor-pointer rounded hover:bg-surface-soft transition-colors duration-row"
        >
          <ChevronDown
            size={ICON.XS}
            strokeWidth={2}
            className={clsx("shrink-0 text-faint transition-transform duration-row", !open && "-rotate-90")}
          />
          <Code2 size={ICON.XS} strokeWidth={2} className="shrink-0 text-faint" />
          <span className="shrink-0 text-2xs font-medium text-ink">Source</span>
        </button>
        {open && (
          <button
            type="button"
            onClick={() => void onCopy()}
            aria-label={copied ? "Copied" : "Copy script"}
            className={clsx(
              "shrink-0 inline-flex items-center gap-1 h-5 px-1.5 rounded-md text-2xs font-medium transition-colors",
              copied ? "text-accent-strong bg-accent-soft" : "text-faint hover:bg-surface-soft hover:text-ink",
            )}
          >
            <CopyGlyph copied={copied} size={ICON.XS} />
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ gridTemplateRows: "0fr", opacity: 0 }}
            animate={{ gridTemplateRows: "1fr", opacity: 1 }}
            exit={{ gridTemplateRows: "0fr", opacity: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
            style={{ display: "grid" }}
          >
            <div className="min-h-0 overflow-hidden">
              {html ? (
                <pre className={SOURCE_PRE_CLASS} dangerouslySetInnerHTML={{ __html: html }} />
              ) : (
                <pre className={SOURCE_PRE_CLASS}>{script}</pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// The workflow's phases → agents, compact enough for the ~300px sidebar (the
// hub). Replaces the old overlay modal: expand a workflow card in place to see
// its agents; click an agent to open its session and watch its tool calls live.
// Per-agent tokens + elapsed only — the full per-tool detail lives in that
// agent's own session.

export function WorkflowDetail({
  workflow,
  onOpenAgent,
}: {
  workflow: Workflow;
  onOpenAgent: (childSessionId: string) => void;
}) {
  const phases = Object.values(workflow.phasesByName);

  if (phases.length === 0) {
    return (
      <div className="px-2 py-3 text-2xs text-faint">
        {isActiveWorkflow(workflow) ? "Spinning up agents…" : "No agents ran."}
      </div>
    );
  }

  return (
    <div className="mt-0.5 space-y-1">
      {phases.map((phase) => (
        <PhaseGroup key={phase.name} phase={phase} onOpenAgent={onOpenAgent} />
      ))}
    </div>
  );
}

function PhaseGroup({
  phase,
  onOpenAgent,
}: {
  phase: WorkflowPhase;
  onOpenAgent: (childSessionId: string) => void;
}) {
  const agents = Object.values(phase.agentsByTaskId);
  // Default OPEN: the user expanded the card specifically to see the subagents.
  // The phase chevron is then a further collapse, not a gate.
  const [expanded, setExpanded] = useState(true);

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="group/phase flex w-full items-center gap-1.5 px-1.5 py-0.5 text-left bg-transparent border-0 cursor-pointer rounded hover:bg-surface-soft transition-colors duration-row"
      >
        <ChevronDown
          size={ICON.XS}
          strokeWidth={2}
          className={clsx("shrink-0 text-faint transition-transform duration-row", !expanded && "-rotate-90")}
        />
        <span className="shrink-0 text-2xs font-medium text-ink">{phase.name}</span>
        <PhaseSparkline agents={agents} />
        <span className="flex-1" />
        <span className="shrink-0 text-2xs tabular-nums text-faint">{agents.length}</span>
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ gridTemplateRows: "0fr", opacity: 0 }}
            animate={{ gridTemplateRows: "1fr", opacity: 1 }}
            exit={{ gridTemplateRows: "0fr", opacity: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
            style={{ display: "grid" }}
          >
            <div className="min-h-0 overflow-hidden">
              {agents.length === 0 ? (
                <div className="pl-6 py-0.5 text-2xs text-faint">No agents yet.</div>
              ) : (
                agents.map((agent) => (
                  <AgentRow key={agent.taskId} agent={agent} onOpenAgent={onOpenAgent} />
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AgentRow({
  agent,
  onOpenAgent,
}: {
  agent: WorkflowAgent;
  onOpenAgent: (childSessionId: string) => void;
}) {
  const running = agent.status === "running" || agent.status === "cancel_requested";
  useTimeTicker(running ? 1000 : 60_000);

  const durationMs = agent.durationMs ?? (running ? Date.now() - agent.startedAt : undefined);
  const elapsedLabel = durationMs != null && durationMs > 0 ? formatDuration(durationMs) : "";
  const tokens = agent.tokens?.total ?? 0;
  const childSessionId = agent.childSessionId;

  const body = (
    <>
      <span
        className={clsx(
          "min-w-0 flex-1 truncate",
          running ? "text-ink-soft" : agent.status === "failed" ? "text-bad" : "text-muted",
        )}
      >
        {agent.name ?? agent.taskId}
      </span>
      {tokens > 0 && <span className="shrink-0 text-2xs tabular-nums text-faint">{formatTokens(tokens)}</span>}
      {elapsedLabel && <span className="shrink-0 text-2xs tabular-nums text-faint">{elapsedLabel}</span>}
    </>
  );

  if (!childSessionId) {
    return <div className="flex items-center gap-2 pl-6 pr-1.5 py-0.5 text-xs">{body}</div>;
  }
  return (
    <button
      type="button"
      onClick={() => onOpenAgent(childSessionId)}
      title={`Open ${agent.name ?? "agent"} — watch its tool calls live`}
      className="group/agent flex w-full items-center gap-2 pl-6 pr-1.5 py-0.5 text-xs text-left bg-transparent border-0 cursor-pointer rounded hover:bg-surface-soft transition-colors"
    >
      {body}
    </button>
  );
}
