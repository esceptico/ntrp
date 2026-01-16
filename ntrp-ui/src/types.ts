// SSE Event types from the server
export type EventType =
  | "thinking"
  | "text"
  | "tool_call"
  | "tool_result"
  | "approval_needed"
  | "question"
  | "choice"
  | "session_info"
  | "done"
  | "error"
  | "cancelled";

export interface ThinkingEvent {
  type: "thinking";
  status: string;
}

export interface TextEvent {
  type: "text";
  content: string;
}

export interface SlashCommand {
  name: string;
  description: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  tool_id: string;
  name: string;
  args: Record<string, unknown>;
  description: string;  // Formatted: name(key=value, ...)
  depth: number;        // 0 = top-level, >0 = subagent
  parent_id: string;    // Parent tool_call_id for grouping subagent calls
}

export interface ToolResultEvent {
  type: "tool_result";
  tool_id: string;
  name: string;
  result: string;
  preview: string;
  duration_ms: number;
  depth: number;
  parent_id: string;
  metadata?: {
    diff?: string;
    lines_changed?: number;
    [key: string]: unknown;
  };
}

export interface ApprovalNeededEvent {
  type: "approval_needed";
  tool_id: string;
  name: string;
  path?: string;
  diff?: string;
  content_preview?: string;
}

export interface SessionInfoEvent {
  type: "session_info";
  session_id: string;
  run_id: string;
  sources: string[];
  source_errors: Record<string, string>;
  yolo?: boolean;
}

export interface DoneEvent {
  type: "done";
  run_id: string;
  usage: {
    prompt: number;
    completion: number;
    total: number;
  };
}

export interface ErrorEvent {
  type: "error";
  message: string;
  recoverable: boolean;
}

export interface CancelledEvent {
  type: "cancelled";
  run_id: string;
}

export interface QuestionEvent {
  type: "question";
  question: string;
  tool_id: string;
}

export interface ChoiceOption {
  id: string;
  label: string;
  description?: string;
}

export interface ChoiceEvent {
  type: "choice";
  question: string;
  options: ChoiceOption[];
  allow_multiple: boolean;
  tool_id: string;
}

export type ServerEvent =
  | ThinkingEvent
  | TextEvent
  | ToolCallEvent
  | ToolResultEvent
  | ApprovalNeededEvent
  | QuestionEvent
  | ChoiceEvent
  | SessionInfoEvent
  | DoneEvent
  | ErrorEvent
  | CancelledEvent;

export interface ToolChainItemData {
  id: string;
  type: "task" | "tool";
  depth: number;
  name: string;
  description?: string;
  result?: string;
  status: "pending" | "running" | "done" | "error";
  seq?: number;
  parentId?: string;
}

// Message types for display
export interface Message {
  id?: string;
  role: "user" | "assistant" | "tool" | "status" | "error" | "thinking" | "tool_chain";
  content: string;
  toolName?: string;
  toolDescription?: string; // Server-formatted: name(key=value, ...)
  toolCount?: number;
  duration?: number;
  toolChain?: ToolChainItemData[];
}

// Approval types
export interface PendingApproval {
  toolId: string;
  name: string;
  path?: string;
  diff?: string;
  preview: string;
}

export type ApprovalResult = "once" | "always" | "reject";

// Config
export interface Config {
  serverUrl: string;
}

export const defaultConfig: Config = {
  serverUrl: process.env.NTRP_SERVER_URL || "http://localhost:8000",
};
