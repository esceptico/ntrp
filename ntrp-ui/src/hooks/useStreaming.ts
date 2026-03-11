import { useCallback, useRef, useEffect, useMemo } from "react";
import { useStore } from "zustand";
import type { Message, ServerEvent, Config, PendingApproval, TokenUsage } from "../types.js";
import { ZERO_USAGE } from "../types.js";
import type { ToolChainItem } from "../components/toolchain/types.js";
import { connectEvents, sendChatMessage, submitToolResult, cancelRun, backgroundRun, revertSession } from "../api/client.js";
import {
  MAX_TOOL_DESCRIPTION_CHARS,
  Status,
  type Status as StatusType,
} from "../lib/constants.js";
import { truncateText } from "../lib/utils.js";
import { createStreamingStore, type SessionNotification, type SessionStreamState, type MessageInput } from "../stores/streamingStore.js";

export type { SessionNotification };

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
  const storeRef = useRef(createStreamingStore());
  const store = storeRef.current;

  const skipApprovalsRef = useRef(skipApprovals);
  skipApprovalsRef.current = skipApprovals;
  const onSessionInfoRef = useRef(onSessionInfo);
  onSessionInfoRef.current = onSessionInfo;
  const configRef = useRef(config);
  configRef.current = config;
  const disconnectRef = useRef<(() => void) | null>(null);
  const prevBgCountRef = useRef(0);

  const { getSession, mutateSession, addMessageToSession, finalizeText, setViewedId, deleteSession } =
    store.getState();

  const viewed = useStore(store, (state) => {
    const id = state.viewedId;
    if (!id) return null;
    return state.sessions.get(id) ?? null;
  });

  const messages = viewed?.messages ?? [];
  const isStreaming = viewed?.isStreaming ?? false;
  const status = viewed?.status ?? Status.IDLE;
  const toolChain = viewed?.toolChain ?? [];
  const pendingApproval = viewed?.pendingApproval ?? null;
  const usage = viewed?.usage ?? ZERO_USAGE;
  const backgroundTaskCount = viewed?.backgroundTaskCount ?? 0;

  const sessions = useStore(store, (state) => state.sessions);
  const viewedId = useStore(store, (state) => state.viewedId);
  const sessionStates = useMemo(() => {
    const states = new Map<string, SessionNotification>();
    for (const [id, s] of sessions) {
      if (id === viewedId) continue;
      if (s.notification) states.set(id, s.notification);
      else if (s.isStreaming) states.set(id, "streaming");
    }
    return states;
  }, [sessions, viewedId]);

  // Ref-based handler so the SSE effect doesn't need to re-subscribe on changes
  const handleEventRef = useRef<(targetId: string, event: ServerEvent) => Promise<void>>(null);
  handleEventRef.current = async (targetId: string, event: ServerEvent) => {
    const viewedId = store.getState().viewedId;

    // These events update pendingText without triggering re-render
    if (event.type === "text") {
      getSession(targetId).pendingText = event.content;
      return;
    }
    if (event.type === "question") {
      getSession(targetId).pendingText = event.question;
      return;
    }

    mutateSession(targetId, (s) => {
      switch (event.type) {
        case "session_info":
          s.runId = event.run_id;
          if (targetId === viewedId) {
            onSessionInfoRef.current?.({
              session_id: event.session_id,
              sources: event.sources,
              session_name: event.session_name,
            });
          }
          break;

        case "thinking":
          s.status = event.status?.includes("compress")
            ? Status.COMPRESSING
            : Status.THINKING;
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
          s.tools.descriptions.set(event.tool_id, description);
          s.tools.startTimes.set(event.tool_id, Date.now());
          const seq = s.tools.sequence++;
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
          const toolDescription = s.tools.descriptions.get(event.tool_id);
          const startTime = s.tools.startTimes.get(event.tool_id);
          const duration = startTime ? Math.round((Date.now() - startTime) / 1000) : undefined;
          s.tools.startTimes.delete(event.tool_id);
          s.tools.descriptions.delete(event.tool_id);
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
            addMessageToSession(s, { role: "tool", content: event.result, toolName: event.name, toolDescription, duration, autoApproved });
            s.toolChain = s.toolChain.filter((item) => item.id !== event.tool_id);
          }
          s.status = Status.THINKING;
          break;
        }

        case "approval_needed": {
          const session = getSession(targetId);
          if (session.alwaysAllowedTools.has(event.name) && session.runId) {
            s.autoApprovedIds.add(event.tool_id);
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
          if (targetId !== viewedId) {
            s.notification = "approval";
          }
          break;
        }

        case "done":
          finalizeText(s);
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
          s.isStreaming = false;
          s.toolChain = s.toolChain.map((item) =>
            item.status === "running" ? { ...item, status: "done" as const } : item
          );
          if (targetId !== viewedId && !s.notification) {
            s.notification = "done";
          }
          break;

        case "error":
          finalizeText(s);
          addMessageToSession(s, { role: "error", content: event.message });
          s.status = Status.IDLE;
          s.isStreaming = false;
          if (targetId !== viewedId) {
            s.notification = "error";
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
          s.pendingText = "";
          break;
        }

        case "backgrounded":
          finalizeText(s);
          s.pendingApproval = null;
          s.status = Status.IDLE;
          s.isStreaming = false;
          s.toolChain = s.toolChain.map((item) =>
            item.status === "running" ? { ...item, status: "done" as const } : item
          );
          if (targetId !== viewedId && !s.notification) {
            s.notification = "done";
          }
          break;

        case "background_task":
          if (event.status === "started") s.backgroundTaskCount++;
          else s.backgroundTaskCount = Math.max(0, s.backgroundTaskCount - 1);
          break;

        default: {
          const _exhaustive: never = event;
          return _exhaustive;
        }
      }
    });

    // Auto-approval: fire submitToolResult outside mutateSession so it can be async
    if (event.type === "approval_needed") {
      const session = getSession(targetId);
      if (session.alwaysAllowedTools.has(event.name) && session.runId) {
        submitToolResult(session.runId, event.tool_id, "Approved", true, configRef.current).catch(() => {
          mutateSession(targetId, (s) => addMessageToSession(s, { role: "error", content: "Auto-approval failed" }));
        });
      }
    }
  };

  // Persistent SSE connection — stable deps, handler accessed via ref
  useEffect(() => {
    if (!sessionId) return;

    const targetId = sessionId;
    getSession(targetId); // ensure session exists

    const disconnect = connectEvents(
      targetId,
      configRef.current,
      (event) => handleEventRef.current!(targetId, event),
    );

    disconnectRef.current = disconnect;

    return () => {
      disconnect();
      disconnectRef.current = null;
    };
  }, [sessionId, getSession]);

  const addMessage = useCallback((msg: MessageInput) => {
    const id = store.getState().viewedId;
    if (!id) return;
    mutateSession(id, (s) => addMessageToSession(s, msg));
  }, [store, mutateSession, addMessageToSession]);

  const clearMessages = useCallback(() => {
    const id = store.getState().viewedId;
    if (!id) return;
    mutateSession(id, (s) => {
      s.messages = [];
      s.historyLoaded = true;
    });
  }, [store, mutateSession]);

  const sendMessage = useCallback(async (message: string) => {
    const id = store.getState().viewedId;
    if (!id) return;

    const s = getSession(id);
    if (s.isStreaming) {
      mutateSession(id, (s) => addMessageToSession(s, { role: "user", content: message }));
      try {
        await sendChatMessage(message, id, configRef.current, skipApprovalsRef.current);
      } catch (error) {
        mutateSession(id, (s) => addMessageToSession(s, { role: "error", content: `Inject failed: ${error}` }));
      }
      return;
    }

    mutateSession(id, (s) => {
      addMessageToSession(s, { role: "user", content: message });
      s.isStreaming = true;
      s.pendingText = "";
      s.status = Status.THINKING;
      s.toolChain = [];
      s.tools.descriptions.clear();
      s.tools.startTimes.clear();
      s.tools.sequence = 0;
    });

    try {
      const res = await sendChatMessage(message, id, configRef.current, skipApprovalsRef.current);
      mutateSession(id, (s) => { s.runId = res.run_id; });
    } catch (error) {
      mutateSession(id, (s) => {
        addMessageToSession(s, { role: "error", content: `${error}` });
        s.isStreaming = false;
        s.status = Status.IDLE;
      });
    }
  }, [store, getSession, addMessageToSession, mutateSession]);

  const handleApproval = useCallback(async (
    result: "once" | "always" | "reject",
    feedback?: string
  ) => {
    const id = store.getState().viewedId;
    if (!id) return;
    const s = store.getState().sessions.get(id);
    if (!s?.pendingApproval || !s.runId) return;

    const approved = result !== "reject";
    const toolName = s.pendingApproval.name;
    const toolId = s.pendingApproval.toolId;
    const runId = s.runId;

    if (result === "always") {
      mutateSession(id, (s) => { s.alwaysAllowedTools.add(toolName); });
    }

    const resultText = approved ? "Approved" : feedback || "";
    try {
      await submitToolResult(runId, toolId, resultText, approved, configRef.current);
    } catch (err) {
      mutateSession(id, (s) => addMessageToSession(s, { role: "error", content: `Approval failed: ${err}` }));
      return;
    }

    mutateSession(id, (s) => {
      s.pendingApproval = null;
      s.status = Status.THINKING;
    });
  }, [store, addMessageToSession, mutateSession]);

  const cancel = useCallback(async () => {
    const id = store.getState().viewedId;
    if (!id) return;
    const s = store.getState().sessions.get(id);
    if (!s?.isStreaming || !s.runId) return;
    try {
      await cancelRun(s.runId, configRef.current);
    } catch {}
  }, [store]);

  const background = useCallback(async () => {
    const id = store.getState().viewedId;
    if (!id) return;
    const s = store.getState().sessions.get(id);
    if (!s?.isStreaming || !s.runId) return;
    try {
      await backgroundRun(s.runId, configRef.current);
    } catch {}
  }, [store]);

  const switchToSession = useCallback((targetId: string, history?: Message[]) => {
    mutateSession(targetId, (s) => {
      s.notification = null;
      if (history && !s.isStreaming) {
        s.messages = history;
        s.historyLoaded = true;
      }
    });
    prevBgCountRef.current = getSession(targetId).backgroundTaskCount;
    setViewedId(targetId);
  }, [getSession, mutateSession, setViewedId]);

  const setStatusPublic = useCallback((newStatus: StatusType) => {
    const id = store.getState().viewedId;
    if (!id) return;
    mutateSession(id, (s) => { s.status = newStatus; });
  }, [store, mutateSession]);

  const revert = useCallback(async (): Promise<string | null> => {
    const id = store.getState().viewedId;
    if (!id) return null;
    const s = store.getState().sessions.get(id);
    if (!s || s.isStreaming) return null;

    try {
      const result = await revertSession(configRef.current, id);
      mutateSession(id, (s) => {
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
      });
      return result.user_message;
    } catch {
      return null;
    }
  }, [store, mutateSession]);

  const deleteSessionState = useCallback((targetId: string) => {
    deleteSession(targetId);
  }, [deleteSession]);

  // Sync sessionId and initial messages
  useEffect(() => {
    if (!sessionId) return;
    const s = getSession(sessionId);
    if (!s.historyLoaded && initialMessages && initialMessages.length > 0) {
      mutateSession(sessionId, (s) => {
        s.messages = initialMessages!;
        s.historyLoaded = true;
      });
    }
    setViewedId(sessionId);
  }, [sessionId, initialMessages, getSession, mutateSession, setViewedId]);

  // Auto-process background task results
  useEffect(() => {
    const prev = prevBgCountRef.current;
    prevBgCountRef.current = backgroundTaskCount;
    if (backgroundTaskCount < prev && !isStreaming) {
      sendMessage("[background task completed, process the results]");
    }
  }, [backgroundTaskCount, isStreaming, sendMessage]);

  // Cleanup
  useEffect(() => {
    return () => { disconnectRef.current?.(); };
  }, []);

  return {
    messages,
    isStreaming,
    status,
    toolChain,
    pendingApproval,
    usage,
    backgroundTaskCount,
    sessionStates,
    addMessage,
    clearMessages,
    sendMessage,
    setStatus: setStatusPublic,
    handleApproval,
    cancel,
    background,
    revert,
    switchToSession,
    deleteSessionState,
  };
}
