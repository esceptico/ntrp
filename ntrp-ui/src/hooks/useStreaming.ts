import { useCallback, useRef, useEffect, useMemo } from "react";
import { useStore } from "zustand";
import type { Message, ServerEvent, Config, PendingApproval, TokenUsage } from "../types.js";
import { ZERO_USAGE } from "../types.js";
import type { ToolChainItem } from "../components/toolchain/types.js";
import { connectEvents, sendChatMessage, submitToolResult, cancelRun, backgroundRun, getBackgroundTasks, revertSession, cancelQueuedMessage, type ImageBlock } from "../api/client.js";
import {
  MAX_TOOL_DESCRIPTION_CHARS,
  MAX_ASSISTANT_CHARS,
  Status,
  type Status as StatusType,
} from "../lib/constants.js";
import { truncateText } from "../lib/utils.js";
import { createStreamingStore, type SessionNotification, type SessionStreamState, type MessageInput, type QueuedMessage } from "../stores/streamingStore.js";

export type { SessionNotification };

const BACKGROUND_ACTIVITY_MIN_INTERVAL_MS = 500;
const BACKGROUND_ACTIVITY_MAX_ITEMS = 20;

function isNestedReasoningEvent(event: ServerEvent): boolean {
  switch (event.type) {
    case "REASONING_START":
    case "REASONING_MESSAGE_START":
    case "REASONING_MESSAGE_CONTENT":
    case "REASONING_MESSAGE_END":
    case "REASONING_END":
      return (event.depth ?? 0) > 0 || Boolean(event.parent_id);
    default:
      return false;
  }
}

interface UseStreamingOptions {
  config: Config;
  sessionId: string | null;
  skipApprovals: boolean;
  streaming?: boolean;
  onSessionInfo?: (info: { session_id: string; integrations: string[]; session_name?: string }) => void;
  initialMessages?: Message[];
}

export function useStreaming({
  config,
  sessionId,
  skipApprovals,
  streaming = true,
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
  const connectionsRef = useRef<Map<string, { disconnect: () => void; stream: boolean }>>(new Map());
  const sseErrorAtRef = useRef<Map<string, number>>(new Map());
  const backgroundActivityAtRef = useRef<Map<string, number>>(new Map());
  const backgroundActivityDetailRef = useRef<Map<string, string>>(new Map());
  const prevBgCountRef = useRef(0);
  const prevIsStreamingRef = useRef(false);

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
  const backgroundTasks = viewed?.backgroundTasks ?? new Map();
  const pendingText = viewed?.pendingText ?? "";
  const queuedMessages = viewed?.queuedMessages ?? [];

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

    if (isNestedReasoningEvent(event)) {
      return;
    }

    if (event.type === "background_task" && event.status === "activity") {
      const detail = event.detail;
      if (!detail) return;
      const key = `${targetId}:${event.task_id}`;
      const now = Date.now();
      const lastAt = backgroundActivityAtRef.current.get(key) ?? 0;
      const lastDetail = backgroundActivityDetailRef.current.get(key);
      if (detail === lastDetail || now - lastAt < BACKGROUND_ACTIVITY_MIN_INTERVAL_MS) return;
      backgroundActivityAtRef.current.set(key, now);
      backgroundActivityDetailRef.current.set(key, detail);
    }

    if (event.type === "text" || event.type === "text_delta") {
      const isDelta = event.type === "text_delta";
      if ((event.depth ?? 0) > 0 && event.parent_id) {
        mutateSession(targetId, (s) => {
          const item = s.toolChain.find((i) => i.id === event.parent_id);
          if (!item) return;
          item.nestedText = isDelta ? (item.nestedText ?? "") + event.content : event.content;
        });
        return;
      }
      mutateSession(targetId, (s) => {
        s.isStreaming = true;
        if (s.status === Status.IDLE) s.status = Status.THINKING;
        s.pendingText = isDelta ? s.pendingText + event.content : event.content;
      });
      return;
    }
    if (event.type === "question") {
      getSession(targetId).pendingText = event.question;
      return;
    }
    if (event.type === "text_message_start") {
      const s = getSession(targetId);
      s.pendingMessageId = event.message_id;
      s.pendingText = "";
      return;
    }

    mutateSession(targetId, (s) => {
      switch (event.type) {
        case "run_started":
          s.runId = event.run_id;
          s.isStreaming = true;
          s.status = Status.THINKING;
          if (targetId !== viewedId) {
            s.notification = "streaming";
          }
          if (targetId === viewedId) {
            onSessionInfoRef.current?.({
              session_id: event.session_id,
              integrations: event.integrations,
              session_name: event.session_name,
            });
          }
          break;

        case "thinking":
          s.status = event.status?.includes("compress")
            ? Status.COMPRESSING
            : Status.THINKING;
          break;

        case "REASONING_START":
        case "REASONING_END":
          break;

        case "REASONING_MESSAGE_START":
          s.isStreaming = true;
          if (s.status === Status.IDLE) s.status = Status.THINKING;
          if (!s.messages.some((m) => m.id === event.messageId)) {
            addMessageToSession(s, { id: event.messageId, role: "thinking", content: "" });
          }
          break;

        case "REASONING_MESSAGE_CONTENT": {
          s.isStreaming = true;
          if (s.status === Status.IDLE) s.status = Status.THINKING;
          const index = s.messages.findIndex((m) => m.id === event.messageId);
          if (index === -1) {
            addMessageToSession(s, {
              id: event.messageId,
              role: "thinking",
              content: truncateText(event.delta.trimStart(), MAX_ASSISTANT_CHARS, "end"),
            });
          } else {
            const current = s.messages[index];
            const delta = current.content ? event.delta : event.delta.trimStart();
            s.messages = [
              ...s.messages.slice(0, index),
              {
                ...current,
                content: truncateText(current.content + delta, MAX_ASSISTANT_CHARS, "end"),
              },
              ...s.messages.slice(index + 1),
            ];
          }
          break;
        }

        case "REASONING_MESSAGE_END": {
          const message = s.messages.find((m) => m.id === event.messageId);
          if (message && !message.content) {
            s.messages = s.messages.filter((m) => m.id !== event.messageId);
          }
          break;
        }

        case "tool_call": {
          s.isStreaming = true;
          s.currentDepth = event.depth;
          s.status = Status.TOOL;
          if (targetId !== viewedId) {
            s.notification = "streaming";
          }
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
              toolDescription, toolCount: childCount, duration, autoApproved, data: event.data,
            });
            s.toolChain = s.toolChain.filter((item) => item.id !== event.tool_id && item.parentId !== event.tool_id);
          } else if (event.depth > 0) {
            s.toolChain = s.toolChain.map((item) =>
              item.id === event.tool_id
                ? { ...item, status: "done" as const, result: event.result, preview: event.preview, data: event.data }
                : item
            );
          } else {
            addMessageToSession(s, { role: "tool", content: event.result, toolName: event.name, toolDescription, duration, autoApproved, data: event.data });
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

        case "run_finished":
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
          s.queuedMessages = s.queuedMessages.map((q) =>
            q.status === "cancelling" ? { ...q, status: "pending" } : q
          );
          break;

        case "run_error":
          finalizeText(s);
          addMessageToSession(s, { role: "error", content: event.message });
          s.status = Status.IDLE;
          s.isStreaming = false;
          if (targetId !== viewedId) {
            s.notification = "error";
          }
          s.queuedMessages = s.queuedMessages.map((q) =>
            q.status === "cancelling" ? { ...q, status: "pending" } : q
          );
          break;

        case "run_cancelled": {
          const containers = s.toolChain.filter(
            (item) => item.name === "research" && s.toolChain.some((c) => c.parentId === item.id)
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
          s.queuedMessages = s.queuedMessages.map((q) =>
            q.status === "cancelling" ? { ...q, status: "pending" } : q
          );
          break;
        }

        case "run_backgrounded":
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
          s.queuedMessages = s.queuedMessages.map((q) =>
            q.status === "cancelling" ? { ...q, status: "pending" } : q
          );
          break;

        case "background_task":
          if (event.status === "started") {
            const key = `${targetId}:${event.task_id}`;
            backgroundActivityAtRef.current.delete(key);
            backgroundActivityDetailRef.current.delete(key);
            s.backgroundTaskCount++;
            s.backgroundTasks.set(event.task_id, {
              id: event.task_id,
              command: event.command,
              status: "running",
              startedAt: Date.now(),
              activity: [],
            });
          } else if (event.status === "activity") {
            const task = s.backgroundTasks.get(event.task_id);
            if (task && event.detail) {
              task.activity = [...task.activity, event.detail].slice(-BACKGROUND_ACTIVITY_MAX_ITEMS);
            }
          } else {
            const key = `${targetId}:${event.task_id}`;
            backgroundActivityAtRef.current.delete(key);
            backgroundActivityDetailRef.current.delete(key);
            s.backgroundTaskCount = Math.max(0, s.backgroundTaskCount - 1);
            if (event.status === "completed" || event.status === "failed") {
              s.completedBackgroundTasks.push({ id: event.task_id, status: event.status });
            }
            s.backgroundTasks.delete(event.task_id);
          }
          break;

        case "text_message_end": {
          const content = truncateText(s.pendingText, MAX_ASSISTANT_CHARS, 'end');
          s.pendingText = "";
          s.pendingMessageId = null;
          if (content) addMessageToSession(s, { role: "assistant", content });
          break;
        }

        case "message_ingested": {
          const idx = s.queuedMessages.findIndex((q) => q.clientId === event.client_id);
          if (idx === -1) break;
          const queued = s.queuedMessages[idx];
          s.queuedMessages = [
            ...s.queuedMessages.slice(0, idx),
            ...s.queuedMessages.slice(idx + 1),
          ];
          addMessageToSession(s, {
            role: "user",
            content: queued.text,
            imageCount: queued.images?.length ?? 0,
            images: queued.images,
          });
          break;
        }

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

    // Disconnect SSE for non-viewed sessions whose run just ended
    const isTerminal = event.type === "run_finished" || event.type === "run_error"
      || event.type === "run_cancelled" || event.type === "run_backgrounded";
    if (isTerminal && store.getState().viewedId !== targetId) {
      const conn = connectionsRef.current.get(targetId);
      if (conn) {
        conn.disconnect();
        connectionsRef.current.delete(targetId);
      }
    }
  };

  // Multi-connection SSE manager — keeps connections alive for sessions with active runs
  // so events are not lost when switching between sessions.

  useEffect(() => {
    if (!sessionId) return;

    const targetId = sessionId;
    const connections = connectionsRef.current;

    // Already connected with same streaming mode — nothing to do
    const existing = connections.get(targetId);
    if (existing && existing.stream === streaming) return;

    // Streaming mode changed — tear down old connection first
    if (existing) {
      existing.disconnect();
      connections.delete(targetId);
    }

    getSession(targetId); // ensure session exists

    // Restore background task state from server on first connect
    getBackgroundTasks(targetId, configRef.current).then((res) => {
      if (res.tasks.length === 0) return;
      mutateSession(targetId, (s) => {
        for (const t of res.tasks) {
          if (!s.backgroundTasks.has(t.task_id)) {
            s.backgroundTasks.set(t.task_id, {
              id: t.task_id,
              command: t.command,
              status: "running",
              startedAt: Date.now(),
              activity: [],
            });
          }
        }
        s.backgroundTaskCount = s.backgroundTasks.size;
      });
    }).catch(() => {});

    const disconnect = connectEvents(
      targetId,
      configRef.current,
      (event) => handleEventRef.current!(targetId, event),
      { stream: streaming },
      (error) => {
        const now = Date.now();
        const last = sseErrorAtRef.current.get(targetId) ?? 0;
        if (now - last < 10000) return;
        sseErrorAtRef.current.set(targetId, now);
        mutateSession(targetId, (s) => {
          if (!s.isStreaming) return;
          addMessageToSession(s, {
            role: "status",
            content: `Event stream disconnected (${error.message}). Reconnecting...`,
          });
          if (targetId !== store.getState().viewedId) s.notification = "error";
        });
      },
    );

    connections.set(targetId, { disconnect, stream: streaming });

    // On cleanup (sessionId changed), only disconnect if session is idle
    return () => {
      const s = store.getState().sessions.get(targetId);
      if (s?.isStreaming) return; // keep alive — run still active
      const conn = connections.get(targetId);
      if (conn) {
        conn.disconnect();
        connections.delete(targetId);
      }
    };
  }, [sessionId, streaming, getSession, store]);

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

  const sendMessage = useCallback(async (message: string, images?: ImageBlock[]) => {
    const id = store.getState().viewedId;
    if (!id) return;

    const imageCount = images?.length || 0;

    mutateSession(id, (s) => {
      addMessageToSession(s, { role: "user", content: message, imageCount, images });
      s.isStreaming = true;
      s.pendingText = "";
      s.status = Status.THINKING;
      s.toolChain = [];
      s.tools.descriptions.clear();
      s.tools.startTimes.clear();
      s.tools.sequence = 0;
    });

    try {
      const res = await sendChatMessage(message, id, configRef.current, skipApprovalsRef.current, images);
      mutateSession(id, (s) => { s.runId = res.run_id; });
    } catch (error) {
      mutateSession(id, (s) => {
        addMessageToSession(s, { role: "error", content: `${error}` });
        s.isStreaming = false;
        s.status = Status.IDLE;
      });
    }
  }, [store, addMessageToSession, mutateSession]);

  const enqueueMessage = useCallback(async (message: string, images?: ImageBlock[]) => {
    const id = store.getState().viewedId;
    if (!id) return;
    const clientId = `cid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    mutateSession(id, (s) => {
      s.queuedMessages = [
        ...s.queuedMessages,
        {
          clientId,
          text: message,
          images,
          status: "pending",
          enqueuedAt: Date.now(),
        },
      ];
    });

    try {
      await sendChatMessage(message, id, configRef.current, skipApprovalsRef.current, images, clientId);
    } catch (error) {
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.map((q) =>
          q.clientId === clientId ? { ...q, status: "failed" } : q
        );
      });
    }
  }, [store, mutateSession]);

  const cancelQueued = useCallback(async (clientId: string) => {
    const id = store.getState().viewedId;
    if (!id) return;

    mutateSession(id, (s) => {
      s.queuedMessages = s.queuedMessages.map((q) =>
        q.clientId === clientId ? { ...q, status: "cancelling" } : q
      );
    });

    let result: "cancelled" | "already_ingested" | "no_run";
    try {
      result = await cancelQueuedMessage(clientId, id, configRef.current);
    } catch {
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.map((q) =>
          q.clientId === clientId ? { ...q, status: "pending" } : q
        );
      });
      return;
    }

    if (result === "cancelled" || result === "no_run") {
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.filter((q) => q.clientId !== clientId);
      });
    } else {
      // already_ingested: leave the bubble; the imminent message_ingested
      // event will move it into the conversation. If the event already arrived,
      // the bubble is already gone and the map below is a no-op.
      mutateSession(id, (s) => {
        s.queuedMessages = s.queuedMessages.map((q) =>
          q.clientId === clientId ? { ...q, status: "sent" } : q
        );
      });
    }
  }, [store, mutateSession]);

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
    prevIsStreamingRef.current = getSession(targetId).isStreaming;
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

  const revertAndResend = useCallback(async (message: string, turns: number): Promise<boolean> => {
    const id = store.getState().viewedId;
    if (!id) return false;
    const s = store.getState().sessions.get(id);
    if (!s || s.isStreaming) return false;

    try {
      await revertSession(configRef.current, id, turns);
      mutateSession(id, (s) => {
        let count = 0;
        let targetIdx = -1;
        for (let i = s.messages.length - 1; i >= 0; i--) {
          if (s.messages[i].role === "user") {
            count++;
            if (count >= turns) {
              targetIdx = i;
              break;
            }
          }
        }
        if (targetIdx >= 0) {
          s.messages = s.messages.slice(0, targetIdx);
        }
      });
      sendMessage(message);
      return true;
    } catch {
      return false;
    }
  }, [store, mutateSession, sendMessage]);

  const deleteSessionState = useCallback((targetId: string) => {
    const conn = connectionsRef.current.get(targetId);
    if (conn) {
      conn.disconnect();
      connectionsRef.current.delete(targetId);
    }
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
    const wasStreaming = prevIsStreamingRef.current;
    prevBgCountRef.current = backgroundTaskCount;
    prevIsStreamingRef.current = isStreaming;

    const shouldTrigger =
      // Task just completed while idle
      (backgroundTaskCount < prev && !isStreaming) ||
      // Streaming just ended — process any tasks that completed during the run
      (wasStreaming && !isStreaming);

    if (!shouldTrigger) return;

    const id = store.getState().viewedId;
    if (!id) return;
    const s = store.getState().sessions.get(id);
    const completed = s?.completedBackgroundTasks ?? [];
    if (completed.length === 0) return;

    const lines = completed.map((c) => `[background task ${c.id} ${c.status}]`).join("\n");
    mutateSession(id, (s) => { s.completedBackgroundTasks = []; });
    sendMessage(lines);
  }, [backgroundTaskCount, isStreaming, sendMessage, store, mutateSession]);

  // Cleanup all connections on unmount
  useEffect(() => {
    return () => {
      for (const { disconnect } of connectionsRef.current.values()) disconnect();
      connectionsRef.current.clear();
    };
  }, []);

  return {
    messages,
    isStreaming,
    status,
    toolChain,
    pendingApproval,
    usage,
    backgroundTaskCount,
    backgroundTasks,
    pendingText,
    sessionStates,
    queuedMessages,
    addMessage,
    clearMessages,
    sendMessage,
    enqueueMessage,
    cancelQueued,
    setStatus: setStatusPublic,
    handleApproval,
    cancel,
    background,
    revert,
    revertAndResend,
    switchToSession,
    deleteSessionState,
  };
}
