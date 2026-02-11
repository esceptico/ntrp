import { useState, useCallback, useRef } from "react";
import type { Message, ServerEvent, Config, PendingApproval } from "../types.js";
import type { ToolChainItem } from "../components/index.js";
import { streamChat, submitToolResult, submitChoiceResult, cancelRun } from "../api/client.js";
import {
  MAX_MESSAGES,
  MAX_TOOL_MESSAGE_CHARS,
  MAX_TOOL_DESCRIPTION_CHARS,
  MAX_ASSISTANT_CHARS,
} from "../lib/constants.js";
import { truncateText } from "../lib/utils.js";

export interface PendingChoice {
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
}

export function useStreaming({
  config,
  sessionId,
  skipApprovals,
  onSessionInfo,
}: UseStreamingOptions) {
  const messageIdRef = useRef(0);
  const runIdRef = useRef<string | null>(null);

  // Tool chain tracking refs
  const toolDescRef = useRef<Map<string, string>>(new Map());
  const toolStartRef = useRef<Map<string, number>>(new Map());
  const toolSeqRef = useRef(0);

  // Text accumulator for events arriving before finalization
  const pendingTextRef = useRef("");

  // Always-allowed tools (session-scoped)
  const alwaysAllowedToolsRef = useRef<Set<string>>(new Set());

  // State
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState("");
  const [toolChain, setToolChain] = useState<ToolChainItem[]>([]);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [pendingChoice, setPendingChoice] = useState<PendingChoice | null>(null);
  const [usage, setUsage] = useState({ prompt: 0, completion: 0 });
  // Counter to force Static re-render on clear
  const [clearCount, setClearCount] = useState(0);

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
    process.stdout.write("\x1B[2J\x1B[H");
    setMessages([]);
    setClearCount((c) => c + 1);
  }, []);

  // Event handlers by type
  const handleSessionInfo = useCallback((event: Extract<ServerEvent, { type: "session_info" }>) => {
    runIdRef.current = event.run_id;
    onSessionInfo?.({
      session_id: event.session_id,
      sources: event.sources,
    });
  }, [onSessionInfo]);

  const handleToolCall = useCallback((event: Extract<ServerEvent, { type: "tool_call" }>) => {
    // Finalize accumulated text as assistant message before tool display
    const text = pendingTextRef.current.trim();
    if (text) {
      addMessage({ role: "assistant", content: text });
      pendingTextRef.current = "";
    }

    setStatus(`${event.name}...`);
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

    // ask_choice results are handled silently - user already saw selection status
    if (event.name === "ask_choice") {
      setToolChain((prev) => prev.filter((item) => item.id !== event.tool_id));
      setStatus("thinking...");
      return;
    }

    setToolChain((prev) => {
      const childCount = prev.filter((item) => item.parentId === event.tool_id).length;

      if (childCount > 0) {
        // Subagent spawner - show summary with child count and duration
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
        // Subagent tool - mark as done
        return prev.map((item) =>
          item.id === event.tool_id
            ? { ...item, status: "done" as const, result: event.result, preview: event.preview, data: event.data }
            : item
        );
      }

      // Top-level tool
      addMessage({ role: "tool", content: event.result, toolName: event.name, toolDescription });
      return prev.filter((item) => item.id !== event.tool_id);
    });

    setStatus("thinking...");
  }, [addMessage]);

  const handleApprovalNeeded = useCallback(async (event: Extract<ServerEvent, { type: "approval_needed" }>) => {
    const currentRunId = runIdRef.current;

    // Auto-approve if always-allowed by user this session
    if (alwaysAllowedToolsRef.current.has(event.name) && currentRunId) {
      await submitToolResult(currentRunId, event.tool_id, "Approved", true, config);
      addMessage({ role: "status", content: `✓ Auto-approved ${event.name} (always)` });
      setStatus("thinking...");
      return;
    }

    setPendingApproval({
      toolId: event.tool_id,
      name: event.name,
      path: event.path,
      diff: event.diff,
      preview: event.content_preview || "",
    });
    setStatus("awaiting approval...");
  }, [config, addMessage]);

  // Main event dispatcher
  const handleEvent = useCallback(async (event: ServerEvent) => {
    switch (event.type) {
      case "session_info":
        handleSessionInfo(event);
        break;
      case "thinking":
        setStatus(event.status);
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
        setStatus("");
        setToolChain((prev) =>
          prev.map((item) =>
            item.status === "running" ? { ...item, status: "done" as const } : item
          )
        );
        break;
      case "error":
        addMessage({ role: "error", content: event.message });
        setStatus("");
        break;
      case "cancelled":
        setToolChain([]);
        setStatus("");
        setIsStreaming(false);
        break;
      case "question":
        pendingTextRef.current = event.question;
        break;
      case "choice":
        // Agent is asking user to choose from options
        setPendingChoice({
          toolId: event.tool_id,
          question: event.question,
          options: event.options,
          allowMultiple: event.allow_multiple,
        });
        setStatus("awaiting choice...");
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

  // Send message and process stream
  const sendMessage = useCallback(async (message: string) => {
    addMessage({ role: "user", content: message });
    setIsStreaming(true);
    pendingTextRef.current = "";
    setStatus("thinking...");
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

    // Finalize remaining text as assistant message
    const finalContent = truncateText(pendingTextRef.current, MAX_ASSISTANT_CHARS, 'end');
    pendingTextRef.current = "";
    if (finalContent) addMessage({ role: "assistant", content: finalContent });

    setIsStreaming(false);
    setStatus("");
  }, [sessionId, config, skipApprovals, handleEvent, addMessage]);

  // Handle approval result
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

    const statusIcon = result === "reject" ? "✗" : "✓";
    const statusText = result === "always" ? "Always allowed" : result === "once" ? "Allowed" : "Rejected";
    addMessage({ role: "status", content: `${statusIcon} ${statusText}: ${pendingApproval.name}` });

    setPendingApproval(null);
    setStatus("thinking...");
  }, [pendingApproval, config, addMessage]);

  // Handle choice selection - submit to server
  const handleChoice = useCallback(async (selected: string[]) => {
    const currentRunId = runIdRef.current;
    if (!pendingChoice || !currentRunId) return;

    // Find the labels for the selected options for status message
    const labels = selected.map((id) => {
      const opt = pendingChoice.options.find((o) => o.id === id);
      return opt?.label ?? id;
    });

    await submitChoiceResult(currentRunId, pendingChoice.toolId, selected, config);
    addMessage({ role: "status", content: `Selected: ${labels.join(", ")}` });

    setPendingChoice(null);
    setStatus("thinking...");
  }, [pendingChoice, config, addMessage]);

  // Cancel pending choice
  const cancelChoice = useCallback(async () => {
    const currentRunId = runIdRef.current;
    if (!pendingChoice || !currentRunId) return;

    await submitChoiceResult(currentRunId, pendingChoice.toolId, [], config);
    addMessage({ role: "status", content: "Choice cancelled" });

    setPendingChoice(null);
    setStatus("thinking...");
  }, [pendingChoice, config, addMessage]);

  // Cancel the current run
  const cancel = useCallback(async () => {
    const currentRunId = runIdRef.current;
    if (!currentRunId || !isStreaming) return;

    try {
      await cancelRun(currentRunId, config);
    } catch {
      // Server might have already finished, ignore errors
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
    clearCount,
    addMessage,
    clearMessages,
    sendMessage,
    handleApproval,
    handleChoice,
    cancelChoice,
    cancel,
  };
}
