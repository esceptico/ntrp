import type { ToolChainItem } from "./components/toolchain/types.js";

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
  description: string;
  depth: number;
  parent_id: string;
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
  data?: Record<string, unknown>;
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
  skip_approvals?: boolean;
  session_name?: string;
}

export interface DoneEvent {
  type: "done";
  run_id: string;
  usage: {
    prompt: number;
    completion: number;
    total: number;
    cache_read: number;
    cache_write: number;
    cost: number;
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

export interface Message {
  id?: string;
  role: "user" | "assistant" | "tool" | "status" | "error" | "thinking" | "tool_chain";
  content: string;
  depth?: number;
  toolName?: string;
  toolDescription?: string;
  toolCount?: number;
  duration?: number;
  toolChain?: ToolChainItem[];
  autoApproved?: boolean;
}

export interface PendingApproval {
  toolId: string;
  name: string;
  path?: string;
  diff?: string;
  preview: string;
}

export type ApprovalResult = "once" | "always" | "reject";

export interface Config {
  serverUrl: string;
}

export const defaultConfig: Config = {
  serverUrl: process.env.NTRP_SERVER_URL || "http://localhost:8000",
};
