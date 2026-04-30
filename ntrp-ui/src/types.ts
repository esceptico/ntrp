import type { ToolChainItem } from "./components/toolchain/types.js";

export interface ThinkingEvent {
  type: "thinking";
  status: string;
}

export interface ReasoningStartEvent {
  type: "REASONING_START";
  messageId: string;
}

export interface ReasoningMessageStartEvent {
  type: "REASONING_MESSAGE_START";
  messageId: string;
  role: "reasoning";
}

export interface ReasoningMessageContentEvent {
  type: "REASONING_MESSAGE_CONTENT";
  messageId: string;
  delta: string;
}

export interface ReasoningMessageEndEvent {
  type: "REASONING_MESSAGE_END";
  messageId: string;
}

export interface ReasoningEndEvent {
  type: "REASONING_END";
  messageId: string;
}

export interface TextEvent {
  type: "text";
  content: string;
  depth?: number;
  parent_id?: string;
}

export interface TextDeltaEvent {
  type: "text_delta";
  content: string;
  depth?: number;
  parent_id?: string;
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

export interface RunStartedEvent {
  type: "run_started";
  session_id: string;
  run_id: string;
  integrations: string[];
  integration_errors: Record<string, string>;
  skip_approvals?: boolean;
  session_name?: string;
}

export interface RunFinishedEvent {
  type: "run_finished";
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

export interface RunErrorEvent {
  type: "run_error";
  message: string;
  recoverable: boolean;
}

export interface BackgroundTaskEvent {
  type: "background_task";
  task_id: string;
  command: string;
  status: "started" | "completed" | "failed" | "cancelled" | "activity";
  detail?: string;
}

export interface RunCancelledEvent {
  type: "run_cancelled";
  run_id: string;
}

export interface RunBackgroundedEvent {
  type: "run_backgrounded";
  run_id: string;
}

export interface QuestionEvent {
  type: "question";
  question: string;
  tool_id: string;
}

export interface TextMessageStartEvent {
  type: "text_message_start";
  message_id: string;
  role: string;
}

export interface TextMessageEndEvent {
  type: "text_message_end";
  message_id: string;
}

export interface MessageIngestedEvent {
  type: "message_ingested";
  client_id: string;
  run_id: string;
}

export type ServerEvent =
  | ThinkingEvent
  | ReasoningStartEvent
  | ReasoningMessageStartEvent
  | ReasoningMessageContentEvent
  | ReasoningMessageEndEvent
  | ReasoningEndEvent
  | TextEvent
  | TextDeltaEvent
  | TextMessageStartEvent
  | TextMessageEndEvent
  | ToolCallEvent
  | ToolResultEvent
  | ApprovalNeededEvent
  | QuestionEvent
  | BackgroundTaskEvent
  | RunStartedEvent
  | RunFinishedEvent
  | RunErrorEvent
  | RunCancelledEvent
  | RunBackgroundedEvent
  | MessageIngestedEvent;

export interface Message {
  id?: string;
  role: "user" | "assistant" | "tool" | "status" | "error" | "thinking" | "tool_chain";
  content: string;
  depth?: number;
  toolName?: string;
  toolDescription?: string;
  toolCount?: number;
  duration?: number;
  data?: Record<string, unknown>;
  toolChain?: ToolChainItem[];
  autoApproved?: boolean;
  imageCount?: number;
  images?: Array<{ media_type: string; data: string }>;
}

export interface PendingApproval {
  toolId: string;
  name: string;
  path?: string;
  diff?: string;
  preview: string;
}

export type ApprovalResult = "once" | "always" | "reject";

export interface TokenUsage {
  prompt: number;
  completion: number;
  cache_read: number;
  cache_write: number;
  cost: number;
  lastCost: number;
}

export const ZERO_USAGE: Readonly<TokenUsage> = Object.freeze({ prompt: 0, completion: 0, cache_read: 0, cache_write: 0, cost: 0, lastCost: 0 });

export interface Config {
  serverUrl: string;
  apiKey: string;
  needsSetup: boolean;
  needsProvider?: boolean;
}
