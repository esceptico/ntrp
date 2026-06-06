import type { ActivityItem, BackgroundAgent } from "../store";
import { activityItemStatus, extractTask, friendlyAgentLabel } from "./agent";

// One view-model for "a sub-agent run", shared by every surface that shows
// one: the inline chat card, the right-sidebar agents hub, and the inspector.
// The point is that an agent looks like the same object everywhere — name,
// type, status, elapsed, result — instead of three different cryptic rows.

export type AgentRunStatus = BackgroundAgent["status"];

export interface AgentRunView {
  /** Stable identity + React key. */
  key: string;
  /** Human title — the task, never a raw run id. */
  name: string;
  /** Humanized agent type, e.g. "Research". */
  type: string;
  status: AgentRunStatus;
  /** Compact elapsed/duration label, e.g. "2m". May be empty. */
  elapsedLabel: string;
  /** Child session to open on click. */
  childSessionId?: string;
  /** Run/task id used to cancel a running agent. */
  runId?: string;
  /** Detached (wait === false) vs awaited. undefined when unknown. */
  detached?: boolean;
  /** Live progress / detail line while running. */
  progress?: string;
  /** One-line result preview for terminal runs. */
  resultPreview?: string;
}

const KNOWN_AGENT_TYPES: Record<string, string> = {
  background_research: "Research",
  research: "Research",
  sub_agent: "Agent",
  "sub-agent": "Agent",
};

/** "background_research" → "Research", "code_review_agent" → "Code review". */
export function humanizeAgentType(type: string | undefined): string {
  if (!type) return "Agent";
  const known = KNOWN_AGENT_TYPES[type.toLowerCase()];
  if (known) return known;
  const cleaned = type
    .replace(/[_-]+/g, " ")
    .replace(/\bagent\b/i, "")
    .trim();
  if (!cleaned) return "Agent";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export function isActiveAgentStatus(status: AgentRunStatus): boolean {
  return status === "running" || status === "cancel_requested";
}

// Both bg-* and text-* so the breathing-glow box-shadow (which uses
// `currentColor`) tints to the same hue as the dot fill.
export function statusDotClass(status: AgentRunStatus | "running"): string {
  switch (status) {
    case "completed":
      return "bg-ok text-ok";
    case "failed":
      return "bg-bad text-bad";
    case "cancelled":
    case "interrupted":
      return "bg-faint text-faint";
    default:
      return "bg-accent text-accent"; // running, cancel_requested
  }
}

// Compact relative-time formatter ("2m", "3h"). Sans suffix — space is
// tight in the sidebar column.
export function formatElapsed(since: number | string): string {
  const started = typeof since === "number" ? since : new Date(since).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h`;
}

function formatDuration(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h`;
}

/** First meaningful line of a result, stripped of markdown chrome and
 *  truncated — for the one-line preview under a finished agent. */
export function resultSnippet(
  text: string | null | undefined,
  max = 140,
): string | undefined {
  if (!text) return undefined;
  for (const raw of text.split(/\r?\n/)) {
    let line = raw.trim();
    if (!line || line.startsWith("```")) continue;
    line = line
      .replace(/^#{1,6}\s+/, "")
      .replace(/^[-*+]\s+/, "")
      .replace(/^>\s+/, "")
      .replace(/^\d+\.\s+/, "")
      .replace(/\*\*/g, "")
      .replace(/[*_`]/g, "")
      .trim();
    if (!line) continue;
    return line.length > max ? `${line.slice(0, max - 1).trimEnd()}…` : line;
  }
  return undefined;
}

// A child agent session id is minted as `${parentSessionId}::${hex}` by the
// spawner; nested agents stack suffixes (`root::a::b`), so the immediate
// parent is everything before the LAST "::". Server-authoritative
// `parent_session_id` is preferred where available; this is the fallback.
export function parentSessionIdOf(sessionId: string | null | undefined): string | null {
  if (!sessionId) return null;
  const idx = sessionId.lastIndexOf("::");
  return idx > 0 ? sessionId.slice(0, idx) : null;
}

export function isAgentSessionId(sessionId: string | null | undefined): boolean {
  return !!sessionId && sessionId.includes("::");
}

function resolveActivityStatus(item: ActivityItem): AgentRunStatus {
  if (item.cancelRequested) return "cancel_requested";
  if (item.taskStatus === "running") return "running";
  if (item.taskStatus === "completed") return "completed";
  if (item.taskStatus === "failed") return "failed";
  if (item.taskStatus === "cancelled") return "cancelled";
  const childStatus = item.childAgent?.status;
  if (
    childStatus === "completed" ||
    childStatus === "failed" ||
    childStatus === "cancelled" ||
    childStatus === "interrupted"
  ) {
    return childStatus;
  }
  return activityItemStatus(item) === "ongoing" ? "running" : "completed";
}

/** Build a view from an inline activity-trace agent item. */
export function agentRunFromActivityItem(item: ActivityItem): AgentRunView {
  const child = item.childAgent;
  const status = resolveActivityStatus(item);
  // Prefer the server's concise display name; fall back to the task (better
  // than the raw `Background(task: "…")` tool target) then the target itself.
  const name =
    item.displayName ?? extractTask(item.args) ?? item.target ?? friendlyAgentLabel(item.kind);
  return {
    key: item.id,
    name: name?.trim() || "Agent",
    type: humanizeAgentType(child?.agentType ?? item.kind),
    status,
    elapsedLabel: item.durationMs != null ? formatDuration(item.durationMs) : "",
    childSessionId: child?.childSessionId,
    runId: item.runId,
    detached: child ? child.wait === false : undefined,
    progress: item.progress,
    // For a detached agent the parent's `item.result` is only the spawn ack,
    // not the real output (that lives in the child session) — so don't preview
    // it inline. Awaited agents do carry their result here.
    resultPreview:
      isActiveAgentStatus(status) || child?.wait === false
        ? undefined
        : resultSnippet(item.result),
  };
}

/** Build a view from a polled background-agent row (sidebar hub). */
export function agentRunFromBackgroundAgent(
  agent: BackgroundAgent,
  resultPreview?: string,
): AgentRunView {
  const active = isActiveAgentStatus(agent.status);
  return {
    key: agent.taskId,
    // Never surface a raw run id; a blank command degrades to the type label.
    name: agent.command?.trim() || humanizeAgentType(agent.agentType),
    type: humanizeAgentType(agent.agentType),
    status: agent.status,
    // createdAt is client poll-time, not the real start — only meaningful for
    // a still-running agent; a finished run would read a misleading "0s".
    elapsedLabel: active ? formatElapsed(agent.createdAt) : "",
    childSessionId: agent.childSessionId,
    runId: agent.taskId,
    detached: agent.wait === false,
    progress: active ? agent.detail : undefined,
    resultPreview: active ? undefined : resultPreview ?? resultSnippet(agent.detail),
  };
}
