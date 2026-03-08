import { useState, useCallback, useRef, useEffect } from "react";
import type { Message, ServerEvent, Config, PendingApproval } from "../types.js";
import type { ToolChainItem } from "../components/toolchain/types.js";
import { streamChat, submitToolResult, cancelRun, revertSession } from "../api/client.js";
import {
  MAX_MESSAGES,
  MAX_TOOL_MESSAGE_CHARS,
  MAX_TOOL_DESCRIPTION_CHARS,
  MAX_ASSISTANT_CHARS,
  Status,
  type Status as StatusType,
} from "../lib/constants.js";
import { truncateText } from "../lib/utils.js";

type MessageInput = Omit<Message, "id"> & { id?: string };

export type SessionNotification = "streaming" | "done" | "approval" | "error";

interface SessionStreamState {
  messages: Message[];
  toolChain: ToolChainItem[];
  pendingApproval: PendingApproval | null;
  status: StatusType;
  usage: { prompt: number; completion: number; cache_read: number; cache_write: number; cost: number; lastCost: number };
  isStreaming: boolean;
  historyLoaded: boolean;
  runId: string | null;
  pendingText: string;
  currentDepth: number;
  toolDesc: Map<string, string>;
  toolStart: Map<string, number>;
  toolSeq: number;
  alwaysAllowedTools: Set<string>;
  autoApprovedIds: Set<string>;
  messageIdCounter: number;
  abortController: AbortController | null;
  notification: SessionNotification | null;
}

const ZERO_USAGE = { prompt: 0, completion: 0, cache_read: 0, cache_write: 0, cost: 0, lastCost: 0 };

function createSessionState(): SessionStreamState {
  return {
    messages: [],
    toolChain: [],
    pendingApproval: null,
    status: Status.IDLE,
    usage: { ...ZERO_USAGE },
    isStreaming: false,
    historyLoaded: false,
    runId: null,
    pendingText: "",
    currentDepth: 0,
    toolDesc: new Map(),
    toolStart: new Map(),
    toolSeq: 0,
    alwaysAllowedTools: new Set(),
    autoApprovedIds: new Set(),
    messageIdCounter: 0,
    abortController: null,
    notification: null,
  };
}

interface UseStreamingOptions {
  config: Config;
  sessionId: string | null;
  skipApprovals: boolean;
  onSessionInfo?: (info: { session_id: string; sources: string[]; session_name?: string }) => void;
  initialMessages?: Message[];
}

export function useStreaming({
  config,
  sessionId,
  skipApprovals,
  onSessionInfo,
  initialMessages,
}: UseStreamingOptions) {
  const sessionsRef = useRef(new Map<string, SessionStreamState>());
  const viewedIdRef = useRef<string | null>(sessionId);
  const mountedRef = useRef(true);
  const skipApprovalsRef = useRef(skipApprovals);
  skipApprovalsRef.current = skipApprovals;
  const onSessionInfoRef = useRef(onSessionInfo);
  onSessionInfoRef.current = onSessionInfo;
  const configRef = useRef(config);
  configRef.current = config;

  interface ViewState {
    messages: Message[];
    isStreaming: boolean;
    status: StatusType;
    toolChain: ToolChainItem[];
    pendingApproval: PendingApproval | null;
    usage: SessionStreamState["usage"];
  }

  const [view, setView] = useState<ViewState>({
    messages: [],
    isStreaming: false,
    status: Status.IDLE,
    toolChain: [],
    pendingApproval: null,
    usage: { ...ZERO_USAGE },
  });
  const [sessionStates, setSessionStates] = useState<Map<string, SessionNotification>>(new Map());

  const getSession = useCallback((id: string): SessionStreamState => {
    let s = sessionsRef.current.get(id);
    if (!s) {
      s = createSessionState();
      sessionsRef.current.set(id, s);
    }
    return s;
  }, []);

  const lastSyncRef = useRef<ViewState | null>(null);

  const syncView = useCallback((targetId: string) => {
    if (!mountedRef.current || targetId !== viewedIdRef.current) return;
    const s = sessionsRef.current.get(targetId);
    if (!s) return;
    const last = lastSyncRef.current;
    if (last
      && last.messages === s.messages
      && last.isStreaming === s.isStreaming
      && last.status === s.status
      && last.toolChain === s.toolChain
      && last.pendingApproval === s.pendingApproval
      && last.usage === s.usage
    ) return;
    const next: ViewState = {
      messages: s.messages, isStreaming: s.isStreaming, status: s.status,
      toolChain: s.toolChain, pendingApproval: s.pendingApproval, usage: s.usage,
    };
    lastSyncRef.current = next;
    setView(next);
  }, []);

  const updateSessionStates = useCallback(() => {
    if (!mountedRef.current) return;
    const states = new Map<string, SessionNotification>();
    for (const [id, s] of sessionsRef.current) {
      if (id === viewedIdRef.current) continue;
      if (s.notification) states.set(id, s.notification);
      else if (s.isStreaming) states.set(id, "streaming");
    }
    setSessionStates(prev => {
      if (prev.size === states.size && [...prev].every(([k, v]) => states.get(k) === v)) return prev;
      return states;
    });
  }, []);

  const generateId = useCallback((s: SessionStreamState) => {
    return `m-${Date.now()}-${s.messageIdCounter++}`;
  }, []);

  const addMessageToSession = useCallback((s: SessionStreamState, msg: MessageInput) => {
    const content = msg.role === "tool"
      ? truncateText(msg.content, MAX_TOOL_MESSAGE_CHARS, 'end')
      : msg.content;
    const withId: Message = { ...msg, content, id: msg.id ?? generateId(s) } as Message;
    const updated = [...s.messages, withId];
    s.messages = updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
  }, [generateId]);

  const addMessage = useCallback((msg: MessageInput) => {
    const id = viewedIdRef.current;
    if (!id) return;
    const s = getSession(id);
    addMessageToSession(s, msg);
    syncView(id);
  }, [getSession, addMessageToSession, syncView]);

  const clearMessages = useCallback(() => {
    const id = viewedIdRef.current;
    if (!id) return;
    const s = getSession(id);
    s.messages = [];
    s.historyLoaded = true;
    syncView(id);
  }, [getSession, syncView]);

  const handleEventForSession = useCallback(async (
    targetId: string,
    s: SessionStreamState,
    event: ServerEvent,
  ) => {
    switch (event.type) {
      case "session_info":
        s.runId = event.run_id;
        if (targetId === viewedIdRef.current) {
          onSessionInfoRef.current?.({
            session_id: event.session_id,
            sources: event.sources,
            session_name: event.session_name,
          });
        }
        break;

      case "thinking":
        s.status = event.status?.includes("compress") ? Status.COMPRESSING : Status.THINKING;
        break;

      case "text":
        s.pendingText = event.content;
        break;

      case "tool_call": {
        const text = s.pendingText.trim();
        if (text && s.currentDepth === 0) {
          addMessageToSession(s, { role: "assistant", content: text });
          s.pendingText = "";
        }
        s.currentDepth = event.depth;
        s.status = Status.TOOL;
        const description = truncateText(event.description, MAX_TOOL_DESCRIPTION_CHARS, 'end');
        s.toolDesc.set(event.tool_id, description);
        s.toolStart.set(event.tool_id, Date.now());
        const seq = s.toolSeq++;
        s.toolChain = [...s.toolChain, {
          id: event.tool_id,
          type: "tool" as const,
          depth: event.depth,
          name: event.name,
          description,
          status: "running" as const,
          seq,
          parentId: event.parent_id || undefined,
        }];
        break;
      }

      case "tool_result": {
        const toolDescription = s.toolDesc.get(event.tool_id);
        const startTime = s.toolStart.get(event.tool_id);
        const duration = startTime ? Math.round((Date.now() - startTime) / 1000) : undefined;
        s.toolStart.delete(event.tool_id);
        s.toolDesc.delete(event.tool_id);
        const autoApproved = s.autoApprovedIds.delete(event.tool_id);
        const childCount = s.toolChain.filter((item) => item.parentId === event.tool_id).length;

        if (childCount > 0) {
          addMessageToSession(s, {
            role: "tool", content: event.result, toolName: event.name,
            toolDescription, toolCount: childCount, duration, autoApproved,
          });
          s.toolChain = s.toolChain.filter((item) => item.id !== event.tool_id && item.parentId !== event.tool_id);
        } else if (event.depth > 0) {
          s.toolChain = s.toolChain.map((item) =>
            item.id === event.tool_id
              ? { ...item, status: "done" as const, result: event.result, preview: event.preview, data: event.data }
              : item
          );
        } else {
          addMessageToSession(s, { role: "tool", content: event.result, toolName: event.name, toolDescription, autoApproved });
          s.toolChain = s.toolChain.filter((item) => item.id !== event.tool_id);
        }
        s.status = Status.THINKING;
        break;
      }

      case "approval_needed": {
        if (s.alwaysAllowedTools.has(event.name) && s.runId) {
          s.autoApprovedIds.add(event.tool_id);
          await submitToolResult(s.runId, event.tool_id, "Approved", true, configRef.current);
          s.status = Status.THINKING;
          break;
        }
        s.pendingApproval = {
          toolId: event.tool_id,
          name: event.name,
          path: event.path,
          diff: event.diff,
          preview: event.content_preview || "",
        };
        s.status = Status.AWAITING_APPROVAL;
        if (targetId !== viewedIdRef.current) {
          s.notification = "approval";
          updateSessionStates();
        }
        break;
      }

      case "done":
        s.usage = {
          prompt: s.usage.prompt + event.usage.prompt,
          completion: s.usage.completion + event.usage.completion,
          cache_read: s.usage.cache_read + (event.usage.cache_read || 0),
          cache_write: s.usage.cache_write + (event.usage.cache_write || 0),
          cost: s.usage.cost + (event.usage.cost || 0),
          lastCost: event.usage.cost || 0,
        };
        s.pendingApproval = null;
        s.status = Status.IDLE;
        s.toolChain = s.toolChain.map((item) =>
          item.status === "running" ? { ...item, status: "done" as const } : item
        );
        break;

      case "error":
        addMessageToSession(s, { role: "error", content: event.message });
        s.status = Status.IDLE;
        if (targetId !== viewedIdRef.current) {
          s.notification = "error";
          updateSessionStates();
        }
        break;

      case "cancelled": {
        const containers = s.toolChain.filter(
          (item) => (item.name === "explore" || item.name === "delegate") && s.toolChain.some((c) => c.parentId === item.id)
        );
        for (const container of containers) {
          const cCount = s.toolChain.filter((c) => c.parentId === container.id).length;
          addMessageToSession(s, {
            role: "tool", content: "Cancelled",
            toolName: container.name, toolDescription: container.description, toolCount: cCount,
          });
        }
        s.toolChain = [];
        s.pendingApproval = null;
        s.status = Status.IDLE;
        s.isStreaming = false;
        break;
      }

      case "question":
        s.pendingText = event.question;
        break;

      default: {
        const _exhaustive: never = event;
        return _exhaustive;
      }
    }

    // text/question: only pendingText (not visible), session_info: only runId — skip re-render
    // thinking: only status — set directly to avoid full sync
    if (event.type === "thinking") {
      if (targetId === viewedIdRef.current) setView(prev => prev.status === s.status ? prev : { ...prev, status: s.status });
    } else if (event.type !== "text" && event.type !== "question" && event.type !== "session_info") {
      syncView(targetId);
    }
  }, [addMessageToSession, syncView, updateSessionStates]);

  const sendMessage = useCallback(async (message: string) => {
    const targetId = viewedIdRef.current;
    if (!targetId) return;
    const s = getSession(targetId);
    if (s.isStreaming) return;

    addMessageToSession(s, { role: "user", content: message });
    s.isStreaming = true;
    s.pendingText = "";
    s.status = Status.THINKING;
    s.toolChain = [];
    s.toolDesc.clear();
    s.toolSeq = 0;
    s.abortController = new AbortController();
    syncView(targetId);
    updateSessionStates();

    try {
      let lastYield = Date.now();
      for await (const event of streamChat(message, targetId, configRef.current, skipApprovalsRef.current, s.abortController.signal)) {
        await handleEventForSession(targetId, s, event);
        const now = Date.now();
        if (now - lastYield > 16) {
          await new Promise(resolve => setTimeout(resolve, 0));
          lastYield = Date.now();
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        s.pendingText = "";
      } else {
        addMessageToSession(s, { role: "error", content: `${error}` });
      }
    }

    s.currentDepth = 0;
    const finalContent = truncateText(s.pendingText, MAX_ASSISTANT_CHARS, 'end');
    s.pendingText = "";
    if (finalContent) addMessageToSession(s, { role: "assistant", content: finalContent });

    s.isStreaming = false;
    s.status = Status.IDLE;
    s.abortController = null;

    if (targetId !== viewedIdRef.current) {
      if (!s.notification) s.notification = "done";
    }

    syncView(targetId);
    updateSessionStates();
  }, [getSession, addMessageToSession, handleEventForSession, syncView, updateSessionStates]);

  const handleApproval = useCallback(async (
    result: "once" | "always" | "reject",
    feedback?: string
  ) => {
    const id = viewedIdRef.current;
    if (!id) return;
    const s = sessionsRef.current.get(id);
    if (!s?.pendingApproval || !s.runId) return;

    const approved = result !== "reject";
    if (result === "always") {
      s.alwaysAllowedTools.add(s.pendingApproval.name);
    }

    const resultText = approved ? "Approved" : feedback || "";
    try {
      await submitToolResult(s.runId, s.pendingApproval.toolId, resultText, approved, configRef.current);
    } catch (err) {
      addMessageToSession(s, { role: "error", content: `Approval failed: ${err}` });
      syncView(id);
      return;
    }

    s.pendingApproval = null;
    s.status = Status.THINKING;
    syncView(id);
  }, [addMessageToSession, syncView]);

  const cancel = useCallback(async () => {
    const id = viewedIdRef.current;
    if (!id) return;
    const s = sessionsRef.current.get(id);
    if (!s?.isStreaming || !s.runId) return;

    try {
      await cancelRun(s.runId, configRef.current);
    } catch {}

    s.abortController?.abort();
  }, []);

  const switchToSession = useCallback((targetId: string, history?: Message[]) => {
    const target = getSession(targetId);
    target.notification = null;

    if (history && !target.isStreaming) {
      target.messages = history;
      target.historyLoaded = true;
    }

    viewedIdRef.current = targetId;
    lastSyncRef.current = null;
    syncView(targetId);
    updateSessionStates();
  }, [getSession, syncView, updateSessionStates]);

  const setStatusPublic = useCallback((newStatus: StatusType) => {
    const id = viewedIdRef.current;
    if (!id) return;
    const s = sessionsRef.current.get(id);
    if (s) {
      s.status = newStatus;
      syncView(id);
    }
  }, [syncView]);

  const revert = useCallback(async (): Promise<string | null> => {
    const id = viewedIdRef.current;
    if (!id) return null;
    const s = sessionsRef.current.get(id);
    if (!s || s.isStreaming) return null;

    try {
      const result = await revertSession(configRef.current, id);

      // Remove messages from last user message onwards in local state
      let lastUserIdx = -1;
      for (let i = s.messages.length - 1; i >= 0; i--) {
        if (s.messages[i].role === "user") {
          lastUserIdx = i;
          break;
        }
      }
      if (lastUserIdx >= 0) {
        s.messages = s.messages.slice(0, lastUserIdx);
      }
      syncView(id);
      return result.user_message;
    } catch {
      return null;
    }
  }, [syncView]);

  const deleteSessionState = useCallback((targetId: string) => {
    const s = sessionsRef.current.get(targetId);
    if (s) {
      s.abortController?.abort();
      sessionsRef.current.delete(targetId);
      updateSessionStates();
    }
  }, [updateSessionStates]);

  useEffect(() => {
    if (!sessionId) return;
    const s = getSession(sessionId);
    if (sessionId !== viewedIdRef.current) {
      viewedIdRef.current = sessionId;
      updateSessionStates();
    }
    if (!s.historyLoaded && initialMessages && initialMessages.length > 0) {
      s.messages = initialMessages;
      s.historyLoaded = true;
    }
    syncView(sessionId);
  }, [sessionId, initialMessages, getSession, syncView, updateSessionStates]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      for (const s of sessionsRef.current.values()) {
        s.abortController?.abort();
      }
    };
  }, []);

  return {
    messages: view.messages,
    isStreaming: view.isStreaming,
    status: view.status,
    toolChain: view.toolChain,
    pendingApproval: view.pendingApproval,
    usage: view.usage,
    sessionStates,
    addMessage,
    clearMessages,
    sendMessage,
    setStatus: setStatusPublic,
    handleApproval,
    cancel,
    revert,
    switchToSession,
    deleteSessionState,
  };
}
