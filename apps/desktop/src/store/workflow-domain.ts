import type { BackgroundAgentStatus } from "./types";

export type WorkflowStatus = "running" | "completed" | "failed" | "cancelled";

export type WorkflowPhaseStatus = "pending" | "running" | "completed" | "failed";

export interface WorkflowTokenUsage {
  prompt: number;
  completion: number;
  total: number;
  cache_read?: number;
  cache_write?: number;
}

export interface WorkflowAgent {
  taskId: string;
  phase: string;
  name?: string;
  agentType?: string;
  childSessionId?: string;
  status: BackgroundAgentStatus;
  detail?: string;
  startedAt: number;
  completedAt?: number;
  durationMs?: number;
  tokens?: WorkflowTokenUsage;
  cost?: number;
  toolCount?: number;
  /** Ledger seq of the last token_usage event applied. Token spend ACCUMULATES,
   *  so replays (history rehydration over a live-built row, revisiting a
   *  session) must be skipped rather than re-added — seq is the dedupe key. */
  lastTokenSeq?: number;
}

export interface WorkflowPhase {
  name: string;
  status: WorkflowPhaseStatus;
  agentsByTaskId: Record<string, WorkflowAgent>;
  startedAt: number | null;
  completedAt: number | null;
}

export interface Workflow {
  workflowId: string;
  sessionId: string;
  runId: string;
  /** Tool-call id of the `workflow` tool call that spawned this workflow.
   *  Lets the activity trace match a workflow to its tool row. */
  parentToolCallId?: string;
  name?: string;
  description?: string;
  status: WorkflowStatus;
  phasesByName: Record<string, WorkflowPhase>;
  totalAgents: number;
  summary?: string;
  startedAt: number;
  completedAt?: number;
  updatedAt: number;
}

export interface WorkflowsDomainState {
  rows: Record<string, Workflow>;
}

export interface WorkflowStartedInput {
  workflowId: string;
  sessionId: string;
  runId: string;
  parentToolCallId?: string;
  name?: string;
  description?: string;
  /** Declared plan: phase titles in order, rendered as pending segments
   *  before the first agent spawns. */
  phases?: string[];
  startedAt?: number;
}

export interface WorkflowFinishedInput {
  workflowId: string;
  sessionId: string;
  status: "completed" | "failed" | "cancelled";
  summary?: string;
  agentCount?: number;
}

export type WorkflowTaskEventKind = "started" | "progress" | "finished";

export interface WorkflowTaskEventInput {
  kind: WorkflowTaskEventKind;
  workflowId: string;
  sessionId: string;
  taskId: string;
  phase?: string | null;
  name?: string;
  agentType?: string;
  childSessionId?: string;
  detail?: string;
  toolCount?: number;
  /** Required for "finished"; ignored otherwise. */
  status?: BackgroundAgentStatus;
}

export interface WorkflowTokenUsageInput {
  workflowId: string;
  sessionId: string;
  taskId: string;
  phase?: string | null;
  /** Session-ledger seq of the originating event; used to skip replays. */
  seq?: number;
  usage: {
    prompt: number;
    completion: number;
    total?: number;
    cache_read?: number;
    cache_write?: number;
  };
  cost?: number;
}

const DEFAULT_PHASE = "default";

export function createWorkflowsDomainState(): WorkflowsDomainState {
  return { rows: {} };
}

export function workflowKey(sessionId: string, workflowId: string): string {
  return `${sessionId}:${workflowId}`;
}

export function isActiveWorkflow(workflow: Pick<Workflow, "status">): boolean {
  return workflow.status === "running";
}

export function selectWorkflowsForSession(
  state: WorkflowsDomainState,
  sessionId: string,
): Workflow[] {
  return Object.values(state.rows).filter((workflow) => workflow.sessionId === sessionId);
}

// The declared plan renders as pending segments immediately; phase() calls fill
// them in (same name = same bucket, insertion order preserved). A replayed
// started event over a live-built row keeps the built phases — seeding is for
// the fresh-row case only.
function seedPhases(titles: string[] | undefined): Record<string, WorkflowPhase> {
  const phases: Record<string, WorkflowPhase> = {};
  for (const name of titles ?? []) {
    phases[name] = { name, status: "pending", agentsByTaskId: {}, startedAt: null, completedAt: null };
  }
  return phases;
}

export function reduceWorkflowStarted(
  state: WorkflowsDomainState,
  input: WorkflowStartedInput,
  now = Date.now(),
): WorkflowsDomainState {
  const key = workflowKey(input.sessionId, input.workflowId);
  const prev = state.rows[key];
  const next: Workflow = {
    workflowId: input.workflowId,
    sessionId: input.sessionId,
    runId: input.runId,
    parentToolCallId: input.parentToolCallId ?? prev?.parentToolCallId,
    name: input.name ?? prev?.name,
    description: input.description ?? prev?.description,
    status: prev?.status ?? "running",
    phasesByName: prev?.phasesByName ?? seedPhases(input.phases),
    totalAgents: prev?.totalAgents ?? 0,
    summary: prev?.summary,
    startedAt: prev?.startedAt ?? input.startedAt ?? now,
    completedAt: prev?.completedAt,
    updatedAt: now,
  };
  return { ...state, rows: { ...state.rows, [key]: next } };
}

export function reduceWorkflowFinished(
  state: WorkflowsDomainState,
  input: WorkflowFinishedInput,
  now = Date.now(),
): WorkflowsDomainState {
  const key = workflowKey(input.sessionId, input.workflowId);
  const prev = state.rows[key];
  if (!prev) return state;
  // Declared phases the script never reached (early exit, failure) would
  // otherwise read as eternally "pending" on a settled run.
  const phasesByName = Object.fromEntries(
    Object.entries(prev.phasesByName).filter(
      ([, phase]) => Object.keys(phase.agentsByTaskId).length > 0,
    ),
  );
  const next: Workflow = {
    ...prev,
    status: input.status,
    summary: input.summary ?? prev.summary,
    phasesByName,
    totalAgents: input.agentCount ?? prev.totalAgents,
    completedAt: now,
    updatedAt: now,
  };
  return { ...state, rows: { ...state.rows, [key]: next } };
}

// Dismissal is a sidebar-visibility concern, persisted in prefs — NOT domain
// deletion. The row stays so the chat-trace card keeps its phases/tokens, and
// the persisted key keeps rehydration from resurfacing the card after reload.
export const DISMISSED_WORKFLOWS_CAP = 300;

export function appendDismissedWorkflow(list: string[], key: string): string[] {
  if (list.includes(key)) return list;
  const next = [...list, key];
  return next.length > DISMISSED_WORKFLOWS_CAP ? next.slice(-DISMISSED_WORKFLOWS_CAP) : next;
}

export function reduceWorkflowTaskEvent(
  state: WorkflowsDomainState,
  input: WorkflowTaskEventInput,
  now = Date.now(),
): WorkflowsDomainState {
  const key = workflowKey(input.sessionId, input.workflowId);
  const workflow = state.rows[key];
  if (!workflow) return state;

  const phaseName = input.phase ?? DEFAULT_PHASE;
  const prevPhase = workflow.phasesByName[phaseName];
  const prevAgent = prevPhase?.agentsByTaskId[input.taskId];

  const status = nextAgentStatus(input, prevAgent);
  const startedAt = prevAgent?.startedAt ?? now;
  const settled = input.kind === "finished";

  const agent: WorkflowAgent = {
    taskId: input.taskId,
    phase: phaseName,
    name: input.name ?? prevAgent?.name,
    agentType: input.agentType ?? prevAgent?.agentType,
    childSessionId: input.childSessionId ?? prevAgent?.childSessionId,
    status,
    detail: input.detail ?? prevAgent?.detail,
    startedAt,
    completedAt: settled ? now : prevAgent?.completedAt,
    durationMs: settled ? now - startedAt : prevAgent?.durationMs,
    tokens: prevAgent?.tokens,
    cost: prevAgent?.cost,
    toolCount: input.toolCount ?? prevAgent?.toolCount,
  };

  const agentsByTaskId = { ...prevPhase?.agentsByTaskId, [input.taskId]: agent };
  const phase: WorkflowPhase = {
    name: phaseName,
    status: derivePhaseStatus(agentsByTaskId),
    agentsByTaskId,
    startedAt: prevPhase?.startedAt ?? now,
    completedAt: derivePhaseCompletedAt(agentsByTaskId, prevPhase?.completedAt ?? null),
  };

  const phasesByName = { ...workflow.phasesByName, [phaseName]: phase };
  const next: Workflow = { ...workflow, phasesByName, updatedAt: now };
  return { ...state, rows: { ...state.rows, [key]: next } };
}

export function reduceWorkflowTokenUsage(
  state: WorkflowsDomainState,
  input: WorkflowTokenUsageInput,
  now = Date.now(),
): WorkflowsDomainState {
  const key = workflowKey(input.sessionId, input.workflowId);
  const workflow = state.rows[key];
  if (!workflow) return state;

  const phaseName = input.phase ?? DEFAULT_PHASE;
  const prevPhase = workflow.phasesByName[phaseName];
  const prevAgent = prevPhase?.agentsByTaskId[input.taskId];
  if (!prevPhase || !prevAgent) return state;
  // Accumulation is not idempotent: rehydration replays the persisted ledger
  // over whatever live events already built, so an already-applied seq must
  // not be re-added (it would double Σ tokens on every session revisit).
  if (input.seq != null && prevAgent.lastTokenSeq != null && input.seq <= prevAgent.lastTokenSeq) {
    return state;
  }

  const agent: WorkflowAgent = {
    ...prevAgent,
    tokens: accumulateTokens(prevAgent.tokens, input.usage),
    cost: addCost(prevAgent.cost, input.cost),
    lastTokenSeq: input.seq ?? prevAgent.lastTokenSeq,
  };
  const agentsByTaskId = { ...prevPhase.agentsByTaskId, [input.taskId]: agent };
  const phase: WorkflowPhase = { ...prevPhase, agentsByTaskId };
  const phasesByName = { ...workflow.phasesByName, [phaseName]: phase };
  const next: Workflow = { ...workflow, phasesByName, updatedAt: now };
  return { ...state, rows: { ...state.rows, [key]: next } };
}

function nextAgentStatus(
  input: WorkflowTaskEventInput,
  prevAgent: WorkflowAgent | undefined,
): BackgroundAgentStatus {
  if (input.kind === "finished") return input.status ?? "completed";
  if (input.status === "failed" || input.status === "cancelled") return input.status;
  return prevAgent?.status === "running" || prevAgent === undefined
    ? "running"
    : prevAgent.status;
}

function derivePhaseStatus(
  agentsByTaskId: Record<string, WorkflowAgent>,
): WorkflowPhaseStatus {
  const agents = Object.values(agentsByTaskId);
  if (agents.length === 0) return "pending";
  if (agents.some((agent) => agent.status === "running" || agent.status === "cancel_requested")) {
    return "running";
  }
  if (agents.some((agent) => agent.status === "failed")) return "failed";
  return "completed";
}

function derivePhaseCompletedAt(
  agentsByTaskId: Record<string, WorkflowAgent>,
  prevCompletedAt: number | null,
): number | null {
  const agents = Object.values(agentsByTaskId);
  if (agents.length === 0) return prevCompletedAt;
  let latest = 0;
  for (const agent of agents) {
    if (agent.completedAt === undefined) return null;
    if (agent.completedAt > latest) latest = agent.completedAt;
  }
  return latest;
}

function accumulateTokens(
  prev: WorkflowTokenUsage | undefined,
  usage: WorkflowTokenUsageInput["usage"],
): WorkflowTokenUsage {
  const total = usage.total ?? usage.prompt + usage.completion;
  if (!prev) {
    return {
      prompt: usage.prompt,
      completion: usage.completion,
      total,
      cache_read: usage.cache_read,
      cache_write: usage.cache_write,
    };
  }
  return {
    prompt: prev.prompt + usage.prompt,
    completion: prev.completion + usage.completion,
    total: prev.total + total,
    cache_read: addOptional(prev.cache_read, usage.cache_read),
    cache_write: addOptional(prev.cache_write, usage.cache_write),
  };
}

function addOptional(prev: number | undefined, next: number | undefined): number | undefined {
  if (prev === undefined && next === undefined) return undefined;
  return (prev ?? 0) + (next ?? 0);
}

function addCost(prev: number | undefined, next: number | undefined): number | undefined {
  if (prev === undefined && next === undefined) return undefined;
  return (prev ?? 0) + (next ?? 0);
}
