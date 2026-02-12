import { useState, useCallback, useRef, useEffect } from "react";
import type { Message, ServerEvent, Config, PendingApproval } from "../types.js";
import type { ToolChainItem } from "../components/toolchain/types.js";
import { streamChat, submitToolResult, submitChoiceResult, cancelRun } from "../api/client.js";
import {
  MAX_MESSAGES,
  MAX_TOOL_MESSAGE_CHARS,
  MAX_TOOL_DESCRIPTION_CHARS,
  MAX_ASSISTANT_CHARS,
  Status,
  type Status as StatusType,
} from "../lib/constants.js";
import { truncateText } from "../lib/utils.js";

interface PendingChoice {
  toolId: string;
  question: string;
  options: { id: string; label: string; description?: string }[];
  allowMultiple: boolean;
}

type MessageInput = Omit<Message, "id"> & { id?: string };

interface UseStreamingOptions {
  config: Config;
  sessionId: string | null;
  skipApprovals: boolean;
  onSessionInfo?: (info: { session_id: string; sources: string[] }) => void;
  initialMessages?: Message[];
}

export function useStreaming({
  config,
  sessionId,
  skipApprovals,
  onSessionInfo,
  initialMessages,
}: UseStreamingOptions) {
  const messageIdRef = useRef(0);
  const runIdRef = useRef<string | null>(null);

  const toolDescRef = useRef<Map<string, string>>(new Map());
  const toolStartRef = useRef<Map<string, number>>(new Map());
  const toolSeqRef = useRef(0);
  const pendingTextRef = useRef("");
  const currentDepthRef = useRef(0);
  const alwaysAllowedToolsRef = useRef<Set<string>>(new Set());

  const [messages, setMessages] = useState<Message[]>([]);
  const historyLoadedRef = useRef(false);

  useEffect(() => {
    if (initialMessages && initialMessages.length > 0 && !historyLoadedRef.current) {
      historyLoadedRef.current = true;
      setMessages(initialMessages);
    }
  }, [initialMessages]);

  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState<StatusType>(Status.IDLE);
  const [toolChain, setToolChain] = useState<ToolChainItem[]>([]);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [pendingChoice, setPendingChoice] = useState<PendingChoice | null>(null);
  const [usage, setUsage] = useState({ prompt: 0, completion: 0 });

  const generateId = useCallback(() => {
    return `m-${Date.now()}-${messageIdRef.current++}`;
  }, []);

  const addMessage = useCallback((msg: MessageInput) => {
    const content = msg.role === "tool"
      ? truncateText(msg.content, MAX_TOOL_MESSAGE_CHARS, 'end')
      : msg.content;
    const withId: Message = {
      ...msg,
      content,
      id: msg.id ?? generateId(),
    } as Message;
    setMessages((prev) => {
      const updated = [...prev, withId];
      return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
    });
  }, [generateId]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    historyLoadedRef.current = true; // Don't reload history after clear
  }, []);

  const handleSessionInfo = useCallback((event: Extract<ServerEvent, { type: "session_info" }>) => {
    runIdRef.current = event.run_id;
    onSessionInfo?.({
      session_id: event.session_id,
      sources: event.sources,
    });
  }, [onSessionInfo]);

  const handleToolCall = useCallback((event: Extract<ServerEvent, { type: "tool_call" }>) => {
    const text = pendingTextRef.current.trim();
    if (text) {
      addMessage({ role: "assistant", content: text, depth: currentDepthRef.current });
      pendingTextRef.current = "";
    }
    currentDepthRef.current = event.depth;

    setStatus(Status.TOOL);
    const description = truncateText(event.description, MAX_TOOL_DESCRIPTION_CHARS, 'end');
    toolDescRef.current.set(event.tool_id, description);
    toolStartRef.current.set(event.tool_id, Date.now());
    const seq = toolSeqRef.current++;

    setToolChain((prev) => [
      ...prev,
      {
        id: event.tool_id,
        type: "tool" as const,
        depth: event.depth,
        name: event.name,
        description,
        status: "running" as const,
        seq,
        parentId: event.parent_id || undefined,
      },
    ]);
  }, [addMessage]);

  const handleToolResult = useCallback((event: Extract<ServerEvent, { type: "tool_result" }>) => {
    const toolDescription = toolDescRef.current.get(event.tool_id);
    const startTime = toolStartRef.current.get(event.tool_id);
    const duration = startTime ? Math.round((Date.now() - startTime) / 1000) : undefined;
    toolStartRef.current.delete(event.tool_id);

    if (event.name === "ask_choice") {
      setToolChain((prev) => prev.filter((item) => item.id !== event.tool_id));
      setStatus(Status.THINKING);
      return;
    }

    setToolChain((prev) => {
      const childCount = prev.filter((item) => item.parentId === event.tool_id).length;

      if (childCount > 0) {
        addMessage({
          role: "tool",
          content: event.result,
          toolName: event.name,
          toolDescription,
          toolCount: childCount,
          duration,
        });
        return prev.filter((item) => item.id !== event.tool_id && item.parentId !== event.tool_id);
      }

      if (event.depth > 0) {
        return prev.map((item) =>
          item.id === event.tool_id
            ? { ...item, status: "done" as const, result: event.result, preview: event.preview, data: event.data }
            : item
        );
      }

      addMessage({ role: "tool", content: event.result, toolName: event.name, toolDescription });
      return prev.filter((item) => item.id !== event.tool_id);
    });

    setStatus(Status.THINKING);
  }, [addMessage]);

  const handleApprovalNeeded = useCallback(async (event: Extract<ServerEvent, { type: "approval_needed" }>) => {
    const currentRunId = runIdRef.current;

    if (alwaysAllowedToolsRef.current.has(event.name) && currentRunId) {
      await submitToolResult(currentRunId, event.tool_id, "Approved", true, config);
      addMessage({ role: "status", content: `\u2713 Auto-approved ${event.name} (always)` });
      setStatus(Status.THINKING);
      return;
    }

    setPendingApproval({
      toolId: event.tool_id,
      name: event.name,
      path: event.path,
      diff: event.diff,
      preview: event.content_preview || "",
    });
    setStatus(Status.AWAITING_APPROVAL);
  }, [config, addMessage]);

  const handleEvent = useCallback(async (event: ServerEvent) => {
    switch (event.type) {
      case "session_info":
        handleSessionInfo(event);
        break;
      case "thinking":
        setStatus(event.status?.includes("compress") ? Status.COMPRESSING : Status.THINKING);
        break;
      case "text":
        pendingTextRef.current = event.content;
        break;
      case "tool_call":
        handleToolCall(event);
        break;
      case "tool_result":
        handleToolResult(event);
        break;
      case "approval_needed":
        await handleApprovalNeeded(event);
        break;
      case "done":
        setUsage((prev) => ({
          prompt: prev.prompt + event.usage.prompt,
          completion: prev.completion + event.usage.completion,
        }));
        setStatus(Status.IDLE);
        setToolChain((prev) =>
          prev.map((item) =>
            item.status === "running" ? { ...item, status: "done" as const } : item
          )
        );
        break;
      case "error":
        addMessage({ role: "error", content: event.message });
        setStatus(Status.IDLE);
        break;
      case "cancelled":
        setToolChain([]);
        setStatus(Status.IDLE);
        setIsStreaming(false);
        break;
      case "question":
        pendingTextRef.current = event.question;
        break;
      case "choice":
        setPendingChoice({
          toolId: event.tool_id,
          question: event.question,
          options: event.options,
          allowMultiple: event.allow_multiple,
        });
        setStatus(Status.AWAITING_CHOICE);
        break;
      default: {
        const _exhaustive: never = event;
        return _exhaustive;
      }
    }
  }, [
    handleSessionInfo,
    handleToolCall,
    handleToolResult,
    handleApprovalNeeded,
    addMessage,
  ]);

  const sendMessage = useCallback(async (message: string) => {
    addMessage({ role: "user", content: message });
    setIsStreaming(true);
    pendingTextRef.current = "";
    setStatus(Status.THINKING);
    setToolChain([]);
    toolDescRef.current.clear();
    toolSeqRef.current = 0;

    try {
      for await (const event of streamChat(message, sessionId, config, skipApprovals)) {
        await handleEvent(event);
      }
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    }

    const finalContent = truncateText(pendingTextRef.current, MAX_ASSISTANT_CHARS, 'end');
    pendingTextRef.current = "";
    if (finalContent) addMessage({ role: "assistant", content: finalContent, depth: currentDepthRef.current });
    currentDepthRef.current = 0;

    setIsStreaming(false);
    setStatus(Status.IDLE);
  }, [sessionId, config, skipApprovals, handleEvent, addMessage]);

  const handleApproval = useCallback(async (
    result: "once" | "always" | "reject",
    feedback?: string
  ) => {
    const currentRunId = runIdRef.current;
    if (!pendingApproval || !currentRunId) return;

    const approved = result !== "reject";

    if (result === "always") {
      alwaysAllowedToolsRef.current.add(pendingApproval.name);
    }

    const resultText = approved
      ? "Approved"
      : feedback
        ? `Rejected: ${feedback}`
        : "Rejected";
    await submitToolResult(currentRunId, pendingApproval.toolId, resultText, approved, config);

    const statusIcon = result === "reject" ? "\u2717" : "\u2713";
    const statusText = result === "always" ? "Always allowed" : result === "once" ? "Allowed" : "Rejected";
    addMessage({ role: "status", content: `${statusIcon} ${statusText}: ${pendingApproval.name}` });

    setPendingApproval(null);
    setStatus(Status.THINKING);
  }, [pendingApproval, config, addMessage]);

  const handleChoice = useCallback(async (selected: string[]) => {
    const currentRunId = runIdRef.current;
    if (!pendingChoice || !currentRunId) return;

    const labels = selected.map((id) => {
      const opt = pendingChoice.options.find((o) => o.id === id);
      return opt?.label ?? id;
    });

    await submitChoiceResult(currentRunId, pendingChoice.toolId, selected, config);
    addMessage({ role: "status", content: `Selected: ${labels.join(", ")}` });

    setPendingChoice(null);
    setStatus(Status.THINKING);
  }, [pendingChoice, config, addMessage]);

  const cancelChoice = useCallback(async () => {
    const currentRunId = runIdRef.current;
    if (!pendingChoice || !currentRunId) return;

    await submitChoiceResult(currentRunId, pendingChoice.toolId, [], config);
    addMessage({ role: "status", content: "Choice cancelled" });

    setPendingChoice(null);
    setStatus(Status.THINKING);
  }, [pendingChoice, config, addMessage]);

  const cancel = useCallback(async () => {
    const currentRunId = runIdRef.current;
    if (!currentRunId || !isStreaming) return;

    try {
      await cancelRun(currentRunId, config);
    } catch {
      // Server might have already finished
    }
  }, [config, isStreaming]);

  return {
    messages,
    isStreaming,
    status,
    toolChain,
    pendingApproval,
    pendingChoice,
    usage,
    addMessage,
    clearMessages,
    sendMessage,
    handleApproval,
    handleChoice,
    cancelChoice,
    cancel,
  };
}
