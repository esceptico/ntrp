import { useEffect } from "react";
import { type AppConfig, type ServerEvent } from "../api";
import { enqueueMessage } from "../actions";
import { getState, setState, useStore, type ActivityItem, type QueuedMessage } from "../store";
import { previewArgs } from "../lib/format";
import { SEMANTIC_KIND_AGENT } from "../lib/agent";

/** End the active activity (if any) and clear the marker. */
function endActivity(s: ReturnType<typeof getState>) {
  if (s.activeActivityId) {
    s.finalizeActivity(s.activeActivityId);
    s.setActiveActivityId(null);
  }
}

/** Mark the most recent unfinished user message's turn as ended. */
function endTurn(s: ReturnType<typeof getState>, endedAt: number) {
  for (let i = s.order.length - 1; i >= 0; i--) {
    const id = s.order[i];
    const msg = s.messages.get(id);
    if (msg?.role !== "user") continue;
    if (!msg.turn || msg.turn.endedAt != null) return;
    s.mutateMessage(id, {
      turn: { ...msg.turn, endedAt, durationMs: Math.max(0, endedAt - msg.turn.startedAt) },
    });
    return;
  }
}

/** Stagger activity-item insertions so a burst of tool calls in one stream
 *  chunk rolls in one-by-one rather than as a single chord.
 *
 *  Sub-agents can fire tens of nested tools nearly simultaneously, so we
 *  also cap how far the queue can fall behind real time — without the cap a
 *  burst of 30 items would visibly drip out over 3+ seconds. */
const ITEM_STAGGER_MS = 40;
const MAX_STAGGER_LAG_MS = 120;
let nextItemRenderAt = 0;

const pendingResultPatches = new Map<string, Partial<ActivityItem>>();
const replayGapReloadingSessions = new Map<string, Promise<boolean>>();
const replayGapBlockedSessions = new Set<string>();

function bufferActivityPatch(itemId: string, patch: Partial<ActivityItem>) {
  pendingResultPatches.set(itemId, {
    ...pendingResultPatches.get(itemId),
    ...patch,
  });
}

function enqueueActivityItem(aid: string, item: ActivityItem) {
  const now = Date.now();
  const queued = nextItemRenderAt + ITEM_STAGGER_MS;
  const ceiling = now + MAX_STAGGER_LAG_MS;
  const renderAt = Math.max(now, Math.min(queued, ceiling));
  nextItemRenderAt = renderAt;
  const delay = renderAt - now;
  const apply = () => {
    const state = getState();
    if (!state.messages.get(aid)?.activity) return;
    const pendingPatch = pendingResultPatches.get(item.id);
    if (pendingPatch) {
      pendingResultPatches.delete(item.id);
      state.appendActivityItem(aid, { ...item, ...pendingPatch });
    } else {
      state.appendActivityItem(aid, item);
    }
  };
  if (delay === 0) apply();
  else setTimeout(apply, delay);
}

/** Buffer in-flight tool calls so we can hand a complete item to the
 *  activity once TOOL_CALL_END arrives. */
const pendingToolCalls = new Map<
  string,
  {
    name: string;
    description: string;
    argsBuffer: string;
    depth: number;
    parentId: string | null;
    semanticKind: string;
  }
>();

let activeAssistantMessageId: string | null = null;
const lastEventSeqBySession = new Map<string, number>();

type ServerEventEffect = { type: "replay_gap"; sessionId: string };
type HistoryReloader = (sessionId: string) => Promise<void>;

export function lastEventSeqForSession(sessionId: string): number | undefined {
  return lastEventSeqBySession.get(sessionId);
}

export function forgetEventSeqForSession(sessionId: string): void {
  lastEventSeqBySession.delete(sessionId);
}

export function clearReplayGapBlockForSession(sessionId: string): void {
  replayGapBlockedSessions.delete(sessionId);
}

function shouldDropServerEvent(event: ServerEvent): boolean {
  if (typeof event.seq !== "number" || !event.session_id) return false;

  const lastSeq = lastEventSeqBySession.get(event.session_id);
  if (lastSeq !== undefined && event.seq <= lastSeq) return true;

  lastEventSeqBySession.set(event.session_id, event.seq);
  return false;
}

function assistantIdFrom(event: { message_id?: string }): string {
  return event.message_id || crypto.randomUUID();
}

function ensureAssistantMessage(id: string, startedAt: number): void {
  const state = getState();
  activeAssistantMessageId = id;
  const existing = state.messages.get(id);
  if (existing?.role === "assistant") return;

  endActivity(state);
  state.appendMessage({
    id,
    role: "assistant",
    content: "",
    turn: { startedAt, endedAt: null, durationMs: null },
  });
}

function appendAssistantDelta(id: string, delta: string, startedAt: number): void {
  const state = getState();
  activeAssistantMessageId = id;
  const existing = state.messages.get(id);
  if (existing?.role === "assistant") {
    state.mutateMessage(id, { content: existing.content + delta });
    return;
  }

  endActivity(state);
  state.appendMessage({
    id,
    role: "assistant",
    content: delta,
    turn: { startedAt, endedAt: null, durationMs: null },
  });
}

function activityInsertAnchor(): string | null {
  if (!activeAssistantMessageId) return null;
  const state = getState();
  const message = state.messages.get(activeAssistantMessageId);
  if (message?.role !== "assistant") return null;
  // Keep a bare TEXT_MESSAGE_START placeholder behind tool activity, but
  // preserve the actual stream order once assistant text has appeared.
  return message.content.trim().length === 0 ? activeAssistantMessageId : null;
}

async function defaultReplayGapHistoryReload(sessionId: string): Promise<void> {
  const { loadHistory } = await import("../actions");
  await loadHistory(sessionId);
}

export function reloadHistoryAfterReplayGap(
  sessionId: string,
  reload: HistoryReloader = defaultReplayGapHistoryReload,
): Promise<void> | null {
  if (replayGapReloadingSessions.has(sessionId)) return null;
  replayGapBlockedSessions.delete(sessionId);
  const task = reload(sessionId)
    .then(() => true)
    .catch((error) => {
      setState({ error: error instanceof Error ? error.message : String(error) });
      replayGapBlockedSessions.add(sessionId);
      return false;
    })
    .finally(() => {
      replayGapReloadingSessions.delete(sessionId);
    });
  replayGapReloadingSessions.set(sessionId, task);
  return task.then(() => undefined);
}

export function handleIncomingServerEvent(
  event: ServerEvent,
  reload?: HistoryReloader,
): Promise<void> | null {
  const sessionId = event.session_id ?? getState().currentSessionId;
  const activeSessionId = getState().currentSessionId;
  if (event.session_id && activeSessionId !== event.session_id) return null;

  const pendingReload =
    event.type === "stream_reset" || !sessionId
      ? undefined
      : replayGapReloadingSessions.get(sessionId);
  if (pendingReload) {
    return pendingReload.then(async (loaded) => {
      if (!loaded) return;
      if (getState().currentSessionId !== sessionId) return;
      await handleIncomingServerEvent(event, reload);
    });
  }
  if (event.type !== "stream_reset" && sessionId && replayGapBlockedSessions.has(sessionId)) {
    return null;
  }

  const effect = handleServerEvent(event);
  if (effect?.type !== "replay_gap") return null;
  return reloadHistoryAfterReplayGap(effect.sessionId, reload);
}

export function handleServerEvent(event: ServerEvent): ServerEventEffect | undefined {
  if (shouldDropServerEvent(event)) return;

  const s = getState();
  const ts = event.timestamp ?? Date.now();

  switch (event.type) {
    // ─── Run lifecycle ───────────────────────────────────────────────
    case "RUN_STARTED":
      endActivity(s);
      activeAssistantMessageId = null;
      setState({ running: true, error: null, currentRunId: event.run_id });
      return;
    case "RUN_FINISHED":
      if (s.currentRunId && s.currentRunId !== event.run_id) return;
      if (event.usage) s.accumulateUsage(event.usage);
      endActivity(s);
      endTurn(s, ts);
      activeAssistantMessageId = null;
      setState({ running: false, currentRunId: null });
      s.resetCancellingQueuedMessages();
      // We deliberately do NOT call loadHistory here. Refreshing the
      // history map mid-stream caused two visible bugs: (1) a flicker
      // where every message remounts as the UUID-keyed live items get
      // swapped for fresh history-${idx}-keyed ones; (2) the just-
      // finished assistant turn occasionally vanishing because the
      // server's save raced the history fetch. The cost is that
      // branching from the *most recent* turn doesn't light up until
      // the user navigates away and back — a fair trade.
      return;
    case "run_cancelled": {
      // Server cancelled the run (user clicked Stop). Mirror RUN_FINISHED's
      // teardown but without accumulating usage — the run was cut short.
      //
      // The server's cancel branch silently drops inject_queue, so any
      // queued messages would otherwise hang stuck in the UI. Instead
      // of discarding them, re-fire each pending entry as a fresh
      // request: the first POST starts a new run, the rest queue into
      // it. The user's typed-ahead work survives Stop.
      if (s.currentRunId && s.currentRunId !== event.run_id) return;
      const toResend: QueuedMessage[] = s.queuedMessages.filter((q) => q.status === "pending");
      endActivity(s);
      endTurn(s, ts);
      activeAssistantMessageId = null;
      setState({ running: false, currentRunId: null });
      s.clearQueuedMessages();
      for (const msg of toResend) {
        void enqueueMessage(msg.text, msg.images ?? []);
      }
      return;
    }
    case "RUN_ERROR":
      if (s.currentRunId && s.currentRunId !== event.run_id) return;
      endActivity(s);
      s.appendMessage({ id: crypto.randomUUID(), role: "error", content: event.message });
      endTurn(s, ts);
      activeAssistantMessageId = null;
      setState({ running: false, currentRunId: null });
      s.resetCancellingQueuedMessages();
      return;
    case "message_ingested": {
      // The queued message was just consumed by the agent. Move the
      // bubble from the queue card into the chat as a real user message.
      const queued = s.queuedMessages.find((q) => q.clientId === event.client_id);
      if (!queued) return;
      s.removeQueuedMessage(event.client_id);
      s.appendMessage({
        id: event.client_id,
        role: "user",
        content: queued.text,
        turn: { startedAt: ts, endedAt: null, durationMs: null },
        images: queued.images,
      });
      return;
    }
    case "stream_reset": {
      if (event.reason !== "replay_gap") return;
      resetStreamState();
      s.setActiveActivityId(null);
      const resetSessionId = event.session_id ?? s.currentSessionId;
      if (!resetSessionId) return;
      forgetEventSeqForSession(resetSessionId);
      return { type: "replay_gap", sessionId: resetSessionId };
    }

    // ─── Text messages ───────────────────────────────────────────────
    // Sub-agent text (depth > 0) is the inner agent's output — the parent
    // tool call's result captures it, so we drop it from the top-level
    // chat to avoid bleed-through.
    case "TEXT_MESSAGE_START":
      if (event.depth) return;
      ensureAssistantMessage(assistantIdFrom(event), ts);
      return;
    case "TEXT_MESSAGE_CONTENT": {
      if (event.depth) return;
      appendAssistantDelta(assistantIdFrom(event), event.delta, ts);
      return;
    }
    case "TEXT_MESSAGE_END":
      return;

    // ─── Reasoning ───────────────────────────────────────────────────
    // Same depth filter as text — sub-agent reasoning belongs to the
    // sub-agent's run, not the parent chat.
    case "REASONING_START":
      return;
    case "REASONING_MESSAGE_START":
      if (event.depth) return;
      s.appendMessage({ id: event.message_id, role: "reasoning", title: "Reasoning", content: "" });
      return;
    case "REASONING_MESSAGE_CONTENT": {
      if (event.depth) return;
      const m = s.messages.get(event.message_id);
      if (m) s.mutateMessage(event.message_id, { content: m.content + event.delta });
      else {
        s.appendMessage({
          id: event.message_id,
          role: "reasoning",
          title: "Reasoning",
          content: event.delta,
        });
      }
      return;
    }
    case "REASONING_MESSAGE_END":
    case "REASONING_END":
      return;

    // ─── Tool calls ──────────────────────────────────────────────────
    case "TOOL_CALL_START":
      pendingToolCalls.set(event.tool_call_id, {
        name: event.tool_call_name,
        description: event.description ?? "",
        argsBuffer: "",
        depth: event.depth ?? 0,
        parentId: event.parent_id ?? null,
        semanticKind: event.kind ?? "tool",
      });
      return;
    case "TOOL_CALL_ARGS": {
      const pending = pendingToolCalls.get(event.tool_call_id);
      if (pending) pending.argsBuffer += event.delta;
      return;
    }
    case "TOOL_CALL_END": {
      const pending = pendingToolCalls.get(event.tool_call_id);
      pendingToolCalls.delete(event.tool_call_id);
      if (!pending) return;

      const target = pending.description || previewArgs(pending.argsBuffer);
      const item: ActivityItem = {
        id: event.tool_call_id,
        kind: pending.name,
        semanticKind:
          pending.semanticKind === SEMANTIC_KIND_AGENT ? SEMANTIC_KIND_AGENT : undefined,
        target,
        args: pending.argsBuffer,
        depth: pending.depth || undefined,
        parentToolId: pending.parentId ?? undefined,
      };
      const pendingPatch = pendingResultPatches.get(item.id);
      if (pendingPatch) {
        pendingResultPatches.delete(item.id);
        Object.assign(item, pendingPatch);
      }
      const aid = s.activeActivityId;
      if (!aid) {
        const newId = crypto.randomUUID();
        s.insertMessageBefore(
          {
            id: newId,
            role: "activity",
            content: "",
            activity: { items: [item], label: "Calling", done: false },
          },
          activityInsertAnchor(),
        );
        s.setActiveActivityId(newId);
        nextItemRenderAt = Date.now();
      } else {
        enqueueActivityItem(aid, item);
      }
      return;
    }
    case "TOOL_CALL_RESULT": {
      const result = event.content ?? event.preview ?? "";
      const patch: Partial<ActivityItem> = { result };
      if (event.parent_id) patch.parentToolId = event.parent_id;
      if (event.depth != null) patch.depth = event.depth || undefined;
      if (event.is_error) patch.error = true;
      if (typeof event.duration_ms === "number" && event.duration_ms > 0) {
        patch.durationMs = event.duration_ms;
      }
      const merged = s.mergeActivityItem(event.tool_call_id, patch);
      if (!merged) bufferActivityPatch(event.tool_call_id, patch);
      return;
    }

    // ─── Sub-agent task lifecycle ───────────────────────────────────
    case "task_started": {
      const patch: Partial<ActivityItem> = {
        taskStatus: "running",
        progress: event.summary ?? "running",
      };
      if (!s.mergeActivityItem(event.task_id, patch)) bufferActivityPatch(event.task_id, patch);
      return;
    }
    case "task_progress": {
      const taskStatus =
        event.status === "failed" || event.status === "cancelled" ? event.status : "running";
      const patch: Partial<ActivityItem> = {
        taskStatus,
        progress: event.summary ?? event.status ?? "running",
      };
      if (!s.mergeActivityItem(event.task_id, patch)) bufferActivityPatch(event.task_id, patch);
      return;
    }
    case "task_finished": {
      const patch: Partial<ActivityItem> = {
        taskStatus: event.status,
        progress: event.summary ?? event.status,
      };
      if (!s.mergeActivityItem(event.task_id, patch)) bufferActivityPatch(event.task_id, patch);
      return;
    }

    // ─── ntrp-specific (non-AG-UI) ───────────────────────────────────
    case "approval_needed":
      s.addPendingApproval({
        toolId: event.tool_id,
        toolName: event.name,
        path: event.path ?? undefined,
        diff: event.diff ?? undefined,
        preview: event.content_preview ?? undefined,
        status: "pending",
      });
      return;
    case "background_task":
      s.appendMessage({
        id: crypto.randomUUID(),
        role: "status",
        title: event.command,
        content: event.detail ? `${event.status}: ${event.detail}` : event.status,
      });
      return;
    case "compaction_started":
      s.setCompacting(true);
      return;
    case "compaction_finished":
      s.setCompacting(false);
      s.setLastCompaction({
        before: event.messages_before,
        after: event.messages_after,
        at: ts,
      });
      return;
  }
}

function headersFor(config: AppConfig): HeadersInit {
  return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
}

export function eventStreamUrl(config: AppConfig, sessionId: string): string {
  const params = new URLSearchParams({ stream: "true" });
  const lastSeq = lastEventSeqForSession(sessionId);
  if (lastSeq !== undefined) params.set("after_seq", String(lastSeq));
  return `${config.serverUrl}/chat/events/${encodeURIComponent(sessionId)}?${params.toString()}`;
}

export function useEvents(sessionId: string | null) {
  const config = useStore((s) => s.config);
  const historyLoadedFor = useStore((s) => s.historyLoadedFor);
  // Wait until loadHistory has populated the store for this session.
  // Otherwise setHistory() landing after the first live deltas would
  // wipe what we just rebuilt from streaming.
  const ready = sessionId !== null && historyLoadedFor === sessionId;

  useEffect(() => {
    if (!sessionId || !ready) return;
    let disposed = false;

    const desktopEvents = window.ntrpDesktop?.events;
    if (desktopEvents) {
      let connectionId: string | null = null;
      const dispose = desktopEvents.onData((payload) => {
        if (!connectionId || payload.connectionId !== connectionId) return;
        if (payload.error) {
          setState({ error: payload.error });
          return;
        }
        if (payload.event) void handleIncomingServerEvent(payload.event as ServerEvent);
      });

      void desktopEvents
        .connect(config, sessionId, lastEventSeqForSession(sessionId))
        .then((id) => {
          if (disposed) {
            void desktopEvents.disconnect(id);
            return;
          }
          connectionId = id;
        })
        .catch((error) => {
          if (!disposed) setState({ error: error instanceof Error ? error.message : String(error) });
        });

      return () => {
        disposed = true;
        dispose();
        if (connectionId) void desktopEvents.disconnect(connectionId);
        resetStreamState();
      };
    }

    const controller = new AbortController();
    void (async () => {
      while (!disposed && !controller.signal.aborted) {
        try {
          const response = await fetch(eventStreamUrl(config, sessionId), {
            headers: headersFor(config),
            signal: controller.signal,
          });
          if (!response.ok || !response.body) throw new Error(`event stream failed: ${response.status}`);

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (!disposed && !controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                void handleIncomingServerEvent(JSON.parse(line.slice(6)) as ServerEvent);
              } catch {
                /* keep-alive */
              }
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          setState({ error: error instanceof Error ? error.message : String(error) });
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    })();

    return () => {
      disposed = true;
      controller.abort();
      resetStreamState();
    };
  }, [sessionId, config, ready]);
}

/** Reset module-level buffers so a disconnect/reconnect doesn't leave
 *  half-built tool calls or a stale stagger queue behind. */
function resetStreamState(): void {
  pendingToolCalls.clear();
  pendingResultPatches.clear();
  activeAssistantMessageId = null;
  nextItemRenderAt = 0;
}

export const resetStreamStateForTest = resetStreamState;

export function resetEventSeqStateForTest(): void {
  lastEventSeqBySession.clear();
}

export function resetReplayGapReloadStateForTest(): void {
  replayGapReloadingSessions.clear();
  replayGapBlockedSessions.clear();
}
