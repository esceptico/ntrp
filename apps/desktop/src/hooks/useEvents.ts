import { useEffect } from "react";
import { type AppConfig, type ServerEvent } from "../api";
import { getState, setState, useStore, type ActivityItem } from "../store";
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

function enqueueActivityItem(aid: string, item: ActivityItem) {
  const now = Date.now();
  const queued = nextItemRenderAt + ITEM_STAGGER_MS;
  const ceiling = now + MAX_STAGGER_LAG_MS;
  const renderAt = Math.max(now, Math.min(queued, ceiling));
  nextItemRenderAt = renderAt;
  const delay = renderAt - now;
  const apply = () => {
    const state = getState();
    if (state.messages.get(aid)?.activity) {
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
  return state.messages.get(activeAssistantMessageId)?.role === "assistant"
    ? activeAssistantMessageId
    : null;
}

export function handleServerEvent(event: ServerEvent) {
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
      if (event.usage) s.accumulateUsage(event.usage);
      endActivity(s);
      endTurn(s, ts);
      activeAssistantMessageId = null;
      setState({ running: false, currentRunId: null });
      // We deliberately do NOT call loadHistory here. Refreshing the
      // history map mid-stream caused two visible bugs: (1) a flicker
      // where every message remounts as the UUID-keyed live items get
      // swapped for fresh history-${idx}-keyed ones; (2) the just-
      // finished assistant turn occasionally vanishing because the
      // server's save raced the history fetch. The cost is that
      // branching from the *most recent* turn doesn't light up until
      // the user navigates away and back — a fair trade.
      return;
    case "RUN_ERROR":
      endActivity(s);
      s.appendMessage({ id: crypto.randomUUID(), role: "error", content: event.message });
      endTurn(s, ts);
      activeAssistantMessageId = null;
      setState({ running: false, currentRunId: null });
      return;

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
      endActivity(s);
      s.appendMessage({ id: event.message_id, role: "reasoning", title: "Reasoning", content: "" });
      return;
    case "REASONING_MESSAGE_CONTENT": {
      if (event.depth) return;
      const m = s.messages.get(event.message_id);
      if (m) s.mutateMessage(event.message_id, { content: m.content + event.delta });
      else {
        endActivity(s);
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
      const aid = s.activeActivityId;
      if (!aid) {
        const newId = crypto.randomUUID();
        s.insertMessageBefore({
          id: newId,
          role: "activity",
          content: "",
          activity: { items: [item], label: "Calling", done: false },
        }, activityInsertAnchor());
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
      s.mergeActivityItem(event.tool_call_id, patch);
      return;
    }

    // ─── ntrp-specific (non-AG-UI) ───────────────────────────────────
    case "approval_needed":
      s.appendMessage({
        id: `approval-${event.tool_id}`,
        role: "approval",
        content: "",
        approval: {
          toolId: event.tool_id,
          toolName: event.name,
          path: event.path ?? undefined,
          diff: event.diff ?? undefined,
          preview: event.content_preview ?? undefined,
          status: "pending",
        },
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
        if (payload.event) handleServerEvent(payload.event as ServerEvent);
      });

      void desktopEvents
        .connect(config, sessionId)
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
          const response = await fetch(
            `${config.serverUrl}/chat/events/${encodeURIComponent(sessionId)}?stream=true`,
            { headers: headersFor(config), signal: controller.signal },
          );
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
                handleServerEvent(JSON.parse(line.slice(6)) as ServerEvent);
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
  activeAssistantMessageId = null;
  nextItemRenderAt = 0;
}

export const resetStreamStateForTest = resetStreamState;
