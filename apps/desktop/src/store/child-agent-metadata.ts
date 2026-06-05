import type { ActivityItem, ChildAgentRef } from "./types";

export type ToolResultData = {
  usage?: ActivityItem["usage"];
  cost?: number;
  child_agent?: {
    child_run_id?: unknown;
    parent_tool_call_id?: unknown;
    agent_type?: unknown;
    wait?: unknown;
    status?: unknown;
  };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object";
}

export function childAgentFromToolResultData(data: unknown): ChildAgentRef | undefined {
  if (!isRecord(data)) return undefined;
  const child = data.child_agent;
  if (!isRecord(child)) return undefined;
  if (!child || typeof child.child_run_id !== "string" || !child.child_run_id) return undefined;
  return {
    childRunId: child.child_run_id,
    parentToolCallId: typeof child.parent_tool_call_id === "string" ? child.parent_tool_call_id : undefined,
    agentType: typeof child.agent_type === "string" && child.agent_type ? child.agent_type : "sub_agent",
    wait: typeof child.wait === "boolean" ? child.wait : true,
    status: typeof child.status === "string" && child.status ? child.status : "completed",
  };
}
