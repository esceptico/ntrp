import { type HistoryMessage, type ServerEvent } from "../api";
import { SEMANTIC_KIND_AGENT } from "../lib/agent";
import { getState, setState, type ActivityItem, type QueuedMessage, type UiMessage } from "./index";
import {
  reduceRunCompleted,
  reduceRunFailed,
  reduceRunStarted,
} from "./run-lifecycle";

type EventApplicationMode = "live" | "replay";

export type TranscriptProjectionEffect =
  | { type: "resend_queued_messages"; messages: QueuedMessage[] };

export interface PendingToolCall {
  name: string;
  description: string;
  argsBuffer: string;
  depth: number;
  parentId: string | null;
  semanticKind: string;
  startSeq?: number;
}

export interface TranscriptProjectionState {
  pendingResultPatches: Map<string, Partial<ActivityItem>>;
  pendingToolCalls: Map<string, PendingToolCall>;
  pendingActivityReplaySeqs: Map<string, number>;
  delayedActivityTimers: Set<ReturnType<typeof setTimeout>>;
  activeAssistantMessageId: string | null;
  nextItemRenderAt: number;
}

export interface TranscriptProjectionResult {
  state: TranscriptProjectionState;
  effect?: TranscriptProjectionEffect;
}

export interface TranscriptProjectionRuntime {
  getProjectionState: () => TranscriptProjectionState;
  setProjectionState: (state: TranscriptProjectionState) => void;
}

interface ProjectionContext {
  state: TranscriptProjectionState;
  runtime?: TranscriptProjectionRuntime;
  update: (next: TranscriptProjectionState) => TranscriptProjectionState;
  latest: () => TranscriptProjectionState;
  commit: (next: TranscriptProjectionState) => TranscriptProjectionState;
}

const ITEM_STAGGER_MS = 40;
const MAX_STAGGER_LAG_MS = 120;

export function createInitialTranscriptProjectionState(): TranscriptProjectionState {
  return {
    pendingResultPatches: new Map(),
    pendingToolCalls: new Map(),
    pendingActivityReplaySeqs: new Map(),
    delayedActivityTimers: new Set(),
    activeAssistantMessageId: null,
    nextItemRenderAt: 0,
  };
}

export function resetTranscriptProjectionState(
  state?: TranscriptProjectionState,
): TranscriptProjectionState {
  if (state) clearDelayedActivityTimers(state);
  return createInitialTranscriptProjectionState();
}

export function transientProjectionReplayFloor(
  state: TranscriptProjectionState,
): number | null {
  let replayFromSeq: number | null = null;
  for (const pending of state.pendingToolCalls.values()) {
    if (typeof pending.startSeq !== "number") continue;
    replayFromSeq =
      replayFromSeq === null ? pending.startSeq : Math.min(replayFromSeq, pending.startSeq);
  }
  for (const seq of state.pendingActivityReplaySeqs.values()) {
    replayFromSeq = replayFromSeq === null ? seq : Math.min(replayFromSeq, seq);
  }
  return replayFromSeq;
}

export function clearDelayedActivityTimers(state: TranscriptProjectionState): void {
  for (const timer of state.delayedActivityTimers) clearTimeout(timer);
}

export function applyChatEventToTranscript(
  state: TranscriptProjectionState,
  event: ServerEvent,
  runtime?: TranscriptProjectionRuntime,
): TranscriptProjectionResult {
  const context = createProjectionContext(state, runtime);

  const s = getState();
  const ts = event.timestamp ?? Date.now();
  const mode: EventApplicationMode = event.replay ? "replay" : "live";
  let effect: TranscriptProjectionEffect | undefined;

  switch (event.type) {
    case "RUN_STARTED":
      endActivity(s);
      setActiveAssistantMessageId(context, null);
      setState((state) => ({
        ...reduceRunStarted(state, { runId: event.run_id, sessionId: event.session_id }),
        error: null,
      }));
      if (event.is_meta_run) {
        if (event.meta_client_id?.startsWith("goal:")) {
          s.appendMessage({
            id: `goal-nudge-${event.run_id}`,
            role: "status",
            content: "Goal nudge",
          });
        }
        s.appendMessage({
          id: `meta-user-${event.run_id}`,
          role: "user",
          content: "",
          isMeta: true,
        });
      }
      break;

    case "RUN_FINISHED":
      if (s.currentRunId && s.currentRunId !== event.run_id) break;
      if (event.usage) {
        s.accumulateUsage({
          ...event.usage,
          contextInputTokens: event.context_input_tokens,
          messageCount: event.message_count,
        });
      }
      endActivity(s);
      endTurn(s, ts);
      setActiveAssistantMessageId(context, null);
      setState((state) =>
        reduceRunCompleted(state, { runId: event.run_id, sessionId: event.session_id }),
      );
      s.resetCancellingQueuedMessages();
      break;

    case "token_usage":
      if (s.currentRunId && s.currentRunId !== event.run_id) break;
      s.updateLiveUsage({
        ...event.usage,
        cost: event.cost,
        messageCount: event.message_count ?? undefined,
        scope: event.scope,
      });
      break;

    case "run_cancelled":
      if (s.currentRunId && s.currentRunId !== event.run_id) break;
      effect = runCancelledEffect(s.queuedMessages);
      endActivity(s);
      endTurn(s, ts);
      setActiveAssistantMessageId(context, null);
      setState((state) =>
        reduceRunCompleted(state, {
          runId: event.run_id,
          sessionId: event.session_id,
          clearApprovals: true,
        }),
      );
      s.clearQueuedMessages();
      break;

    case "RUN_ERROR":
      if (s.currentRunId && s.currentRunId !== event.run_id) break;
      endActivity(s);
      s.appendMessage({ id: crypto.randomUUID(), role: "error", content: event.message });
      endTurn(s, ts);
      setActiveAssistantMessageId(context, null);
      setState((state) =>
        reduceRunFailed(state, { runId: event.run_id, sessionId: event.session_id }),
      );
      s.resetCancellingQueuedMessages();
      break;

    case "message_ingested": {
      const queued = s.queuedMessages.find((q) => q.clientId === event.client_id);
      if (!queued) break;
      s.removeQueuedMessage(event.client_id);
      s.appendMessage({
        id: event.client_id,
        role: "user",
        content: queued.text,
        turn: { startedAt: ts, endedAt: null, durationMs: null },
        images: queued.images,
      });
      break;
    }

    case "TEXT_MESSAGE_START":
      if (!event.depth) ensureAssistantMessage(context, assistantIdFrom(event), ts);
      break;

    case "TEXT_MESSAGE_CONTENT":
      if (!event.depth) appendAssistantDelta(context, assistantIdFrom(event), event.delta, ts);
      break;

    case "TEXT_MESSAGE_END":
      if (!event.depth && event.content !== undefined) {
        reconcileAssistantContent(context, assistantIdFrom(event), event.content, ts);
      }
      break;
    case "REASONING_START":
    case "REASONING_MESSAGE_END":
    case "REASONING_END":
      break;

    case "REASONING_MESSAGE_START":
      if (!event.depth) {
        s.appendMessage({ id: event.message_id, role: "reasoning", title: "Reasoning", content: "" });
      }
      break;

    case "REASONING_MESSAGE_CONTENT": {
      if (event.depth) break;
      const message = s.messages.get(event.message_id);
      if (message) {
        s.mutateMessage(event.message_id, { content: message.content + event.delta });
      } else {
        s.appendMessage({
          id: event.message_id,
          role: "reasoning",
          title: "Reasoning",
          content: event.delta,
        });
      }
      break;
    }

    case "TOOL_CALL_START": {
      const pendingToolCalls = new Map(context.state.pendingToolCalls);
      pendingToolCalls.set(event.tool_call_id, {
        name: event.tool_call_name,
        description: event.description ?? "",
        argsBuffer: "",
        depth: event.depth ?? 0,
        parentId: event.parent_id ?? null,
        semanticKind: event.kind ?? "tool",
        startSeq: typeof event.seq === "number" ? event.seq : undefined,
      });
      context.update({ ...context.state, pendingToolCalls });
      break;
    }

    case "TOOL_CALL_ARGS": {
      const pending = context.state.pendingToolCalls.get(event.tool_call_id);
      if (!pending) break;
      const pendingToolCalls = new Map(context.state.pendingToolCalls);
      pendingToolCalls.set(event.tool_call_id, {
        ...pending,
        argsBuffer: pending.argsBuffer + event.delta,
      });
      context.update({ ...context.state, pendingToolCalls });
      break;
    }

    case "TOOL_CALL_END": {
      const pending = context.state.pendingToolCalls.get(event.tool_call_id);
      const pendingToolCalls = new Map(context.state.pendingToolCalls);
      pendingToolCalls.delete(event.tool_call_id);
      let pendingActivityReplaySeqs = context.state.pendingActivityReplaySeqs;
      if (typeof pending?.startSeq === "number") {
        pendingActivityReplaySeqs = new Map(pendingActivityReplaySeqs);
        pendingActivityReplaySeqs.set(event.tool_call_id, pending.startSeq);
      }
      context.update({ ...context.state, pendingToolCalls, pendingActivityReplaySeqs });
      if (!pending) break;

      const target = pending.description || formatCallTarget(pending.name, pending.argsBuffer || "{}");
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
      const pendingPatch = takePendingResultPatch(context, item.id);
      if (pendingPatch) Object.assign(item, pendingPatch);
      const activityId = s.activeActivityId;
      if (!activityId) {
        const newId = crypto.randomUUID();
        s.insertMessageBefore(
          {
            id: newId,
            role: "activity",
            content: "",
            activity: { items: [item], label: "Calling", done: false },
          },
          activityInsertAnchor(context),
        );
        s.setActiveActivityId(newId);
        const nextPendingActivityReplaySeqs = new Map(context.state.pendingActivityReplaySeqs);
        nextPendingActivityReplaySeqs.delete(item.id);
        context.update({
          ...context.state,
          pendingActivityReplaySeqs: nextPendingActivityReplaySeqs,
          nextItemRenderAt: Date.now(),
        });
      } else {
        enqueueActivityItem(context, activityId, item, mode);
      }
      break;
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
      const data = event.data as { usage?: ActivityItem["usage"]; cost?: number } | null;
      if (data?.usage) patch.usage = data.usage;
      if (typeof data?.cost === "number") patch.cost = data.cost;
      if (!s.mergeActivityItem(event.tool_call_id, patch)) {
        bufferActivityPatch(context, event.tool_call_id, patch);
      }
      break;
    }

    case "task_started": {
      const patch: Partial<ActivityItem> = {
        taskStatus: "running",
        progress: event.summary ?? "running",
      };
      if (!s.mergeActivityItem(event.task_id, patch)) {
        bufferActivityPatch(context, event.task_id, patch);
      }
      break;
    }

    case "task_progress": {
      const taskStatus =
        event.status === "failed" || event.status === "cancelled" ? event.status : "running";
      const patch: Partial<ActivityItem> = {
        taskStatus,
        progress: event.summary ?? event.status ?? "running",
      };
      if (!s.mergeActivityItem(event.task_id, patch)) {
        bufferActivityPatch(context, event.task_id, patch);
      }
      break;
    }

    case "task_finished": {
      const patch: Partial<ActivityItem> = {
        taskStatus: event.status,
        progress: event.summary ?? event.status,
      };
      if (!s.mergeActivityItem(event.task_id, patch)) {
        bufferActivityPatch(context, event.task_id, patch);
      }
      break;
    }

    default:
      break;
  }

  return { state: context.state, effect };
}

export function rebuildTranscriptFromHistory(messages: HistoryMessage[]): UiMessage[] {
  const resultsById = new Map<string, string>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.tool_call_id) {
      resultsById.set(msg.tool_call_id, msg.content);
    }
  }

  const items: UiMessage[] = [];
  let activeActivityId: string | null = null;

  const findActivity = (id: string) =>
    items.find((it) => it.id === id && it.role === "activity")?.activity;

  messages.forEach((msg, index) => {
    const sourceIndex = msg.seq ?? index;
    const sourceMessageId = msg.message_id ?? msg.id;
    const stableId = msg.id ?? msg.message_id ?? `history-${sourceIndex}`;
    const stampedAt = msg.created_at ? Date.parse(msg.created_at) : 0;

    if (msg.role === "user") {
      activeActivityId = null;
      if (msg.is_meta && stableId.startsWith("goal:")) {
        items.push({
          id: `${stableId}-nudge`,
          role: "status",
          sourceIndex,
          sourceMessageId,
          content: "Goal nudge",
        });
      }
      items.push({
        id: stableId,
        role: "user",
        sourceIndex,
        sourceMessageId,
        content: msg.content,
        turn: { startedAt: stampedAt, endedAt: stampedAt, durationMs: null },
        images: msg.images,
        isMeta: msg.is_meta,
      });
      return;
    }

    if (msg.role === "tool") return;

    if (msg.reasoning_content) {
      items.push({
        id: `${stableId}-reasoning`,
        role: "reasoning",
        sourceIndex,
        sourceMessageId,
        title: "Reasoning",
        content: msg.reasoning_content,
      });
    }

    if (msg.content && msg.content.trim().length > 0) {
      activeActivityId = null;
      items.push({
        id: stableId,
        role: "assistant",
        sourceIndex,
        sourceMessageId,
        content: msg.content,
        turn: stampedAt
          ? { startedAt: stampedAt, endedAt: stampedAt, durationMs: null }
          : undefined,
      });
    }

    if (msg.tool_calls && msg.tool_calls.length > 0) {
      if (!activeActivityId) {
        activeActivityId = `${stableId}-activity`;
        items.push({
          id: activeActivityId,
          role: "activity",
          sourceIndex,
          sourceMessageId,
          content: "",
          activity: { items: [], label: "Called", done: true },
        });
      }
      const activity = findActivity(activeActivityId);
      if (activity) {
        for (const toolCall of msg.tool_calls) {
          const args = toolCall.arguments || "";
          activity.items.push({
            id: toolCall.id,
            kind: toolCall.name,
            semanticKind:
              toolCall.kind === SEMANTIC_KIND_AGENT ? SEMANTIC_KIND_AGENT : undefined,
            target: formatCallTarget(toolCall.name, args || "{}"),
            args,
            result: resultsById.get(toolCall.id),
          });
        }
      }
    }
  });

  return items;
}

export function runCancelledEffect(queuedMessages: QueuedMessage[]): TranscriptProjectionEffect | undefined {
  const messages = queuedMessages.filter((q) => q.status === "pending");
  if (messages.length === 0) return undefined;
  return { type: "resend_queued_messages", messages };
}

function createProjectionContext(
  state: TranscriptProjectionState,
  runtime?: TranscriptProjectionRuntime,
): ProjectionContext {
  const context: ProjectionContext = {
    state: selectTranscriptProjectionState(state),
    runtime,
    update(next) {
      context.state = selectTranscriptProjectionState(next);
      return context.state;
    },
    latest() {
      return selectTranscriptProjectionState(runtime?.getProjectionState() ?? context.state);
    },
    commit(next) {
      context.state = selectTranscriptProjectionState(next);
      runtime?.setProjectionState(context.state);
      return context.state;
    },
  };
  return context;
}

function selectTranscriptProjectionState(state: TranscriptProjectionState): TranscriptProjectionState {
  return {
    pendingResultPatches: state.pendingResultPatches,
    pendingToolCalls: state.pendingToolCalls,
    pendingActivityReplaySeqs: state.pendingActivityReplaySeqs,
    delayedActivityTimers: state.delayedActivityTimers,
    activeAssistantMessageId: state.activeAssistantMessageId,
    nextItemRenderAt: state.nextItemRenderAt,
  };
}

function assistantIdFrom(event: { message_id?: string }): string {
  return event.message_id || crypto.randomUUID();
}

function setActiveAssistantMessageId(
  context: ProjectionContext,
  activeAssistantMessageId: string | null,
): void {
  context.update({ ...context.state, activeAssistantMessageId });
}

function ensureAssistantMessage(context: ProjectionContext, id: string, startedAt: number): void {
  const state = getState();
  setActiveAssistantMessageId(context, id);
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

function appendAssistantDelta(
  context: ProjectionContext,
  id: string,
  delta: string,
  startedAt: number,
): void {
  const state = getState();
  setActiveAssistantMessageId(context, id);
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

function reconcileAssistantContent(
  context: ProjectionContext,
  id: string,
  content: string,
  startedAt: number,
): void {
  const state = getState();
  setActiveAssistantMessageId(context, id);
  const existing = state.messages.get(id);
  if (existing?.role === "assistant") {
    if (existing.content !== content) state.mutateMessage(id, { content });
    return;
  }
  if (content.length === 0) return;

  endActivity(state);
  state.appendMessage({
    id,
    role: "assistant",
    content,
    turn: { startedAt, endedAt: null, durationMs: null },
  });
}

function activityInsertAnchor(context: ProjectionContext): string | null {
  const state = getState();
  let assistantId = context.state.activeAssistantMessageId;
  if (!assistantId || state.messages.get(assistantId)?.role !== "assistant") {
    assistantId = null;
    for (let i = state.order.length - 1; i >= 0; i--) {
      const id = state.order[i];
      const message = state.messages.get(id);
      if (message?.role !== "assistant") continue;
      assistantId = id;
      break;
    }
  }
  if (!assistantId) return null;
  const message = state.messages.get(assistantId);
  if (message?.role !== "assistant") return null;
  if (message.content.trim().length !== 0) return null;
  setActiveAssistantMessageId(context, assistantId);
  return assistantId;
}

function bufferActivityPatch(
  context: ProjectionContext,
  itemId: string,
  patch: Partial<ActivityItem>,
) {
  const pendingResultPatches = new Map(context.state.pendingResultPatches);
  pendingResultPatches.set(itemId, {
    ...pendingResultPatches.get(itemId),
    ...patch,
  });
  context.update({ ...context.state, pendingResultPatches });
}

function takePendingResultPatch(
  context: ProjectionContext,
  itemId: string,
): Partial<ActivityItem> | undefined {
  const pendingPatch = context.state.pendingResultPatches.get(itemId);
  if (!pendingPatch) return undefined;
  const pendingResultPatches = new Map(context.state.pendingResultPatches);
  pendingResultPatches.delete(itemId);
  context.update({ ...context.state, pendingResultPatches });
  return pendingPatch;
}

function takePendingResultPatchFromState(
  state: TranscriptProjectionState,
  itemId: string,
): { state: TranscriptProjectionState; patch?: Partial<ActivityItem> } {
  const patch = state.pendingResultPatches.get(itemId);
  if (!patch) return { state };
  const pendingResultPatches = new Map(state.pendingResultPatches);
  pendingResultPatches.delete(itemId);
  return { state: { ...state, pendingResultPatches }, patch };
}

function enqueueActivityItem(
  context: ProjectionContext,
  activityId: string,
  item: ActivityItem,
  mode: EventApplicationMode,
) {
  const clearReplaySeq = () => {
    if (!context.state.pendingActivityReplaySeqs.has(item.id)) return;
    const pendingActivityReplaySeqs = new Map(context.state.pendingActivityReplaySeqs);
    pendingActivityReplaySeqs.delete(item.id);
    context.update({ ...context.state, pendingActivityReplaySeqs });
  };

  if (mode === "replay") {
    const state = getState();
    if (!state.messages.get(activityId)?.activity) {
      clearReplaySeq();
      return;
    }
    const pendingPatch = takePendingResultPatch(context, item.id);
    state.appendActivityItem(activityId, pendingPatch ? { ...item, ...pendingPatch } : item);
    clearReplaySeq();
    return;
  }

  const now = Date.now();
  const queued = context.state.nextItemRenderAt + ITEM_STAGGER_MS;
  const ceiling = now + MAX_STAGGER_LAG_MS;
  const renderAt = Math.max(now, Math.min(queued, ceiling));
  context.update({ ...context.state, nextItemRenderAt: renderAt });
  const delay = renderAt - now;
  const apply = () => {
    const state = getState();
    if (!state.messages.get(activityId)?.activity) {
      clearReplaySeq();
      return;
    }
    const { state: withoutPatch, patch } = takePendingResultPatchFromState(
      context.latest(),
      item.id,
    );
    context.commit(withoutPatch);
    const pendingPatch = patch;
    state.appendActivityItem(activityId, pendingPatch ? { ...item, ...pendingPatch } : item);
    clearReplaySeq();
  };
  if (delay === 0) apply();
  else {
    let timer: ReturnType<typeof setTimeout>;
    timer = setTimeout(() => {
      const latest = context.latest();
      const delayedActivityTimers = new Set(latest.delayedActivityTimers);
      delayedActivityTimers.delete(timer);
      context.commit({ ...latest, delayedActivityTimers });
      apply();
    }, delay);
    const delayedActivityTimers = new Set(context.state.delayedActivityTimers);
    delayedActivityTimers.add(timer);
    context.update({ ...context.state, delayedActivityTimers });
  }
}

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

function formatCallTarget(name: string, argsJson: string): string {
  try {
    const parsed = JSON.parse(argsJson || "{}");
    if (parsed && typeof parsed === "object") {
      const entries = Object.entries(parsed as Record<string, unknown>);
      if (entries.length === 0) return `${name}()`;
      const parts = entries.map(([key, value]) => {
        const rendered = typeof value === "string" ? `"${value}"` : JSON.stringify(value);
        return `${key}=${rendered}`;
      });
      const full = `${name}(${parts.join(", ")})`;
      return full.length > 120 ? `${full.slice(0, 117)}...` : full;
    }
  } catch {
    // Fall through to the raw tool name.
  }
  return name;
}
