import { type HistoryMessage, type ServerEvent } from "../api";
import { SEMANTIC_KIND_AGENT } from "../lib/agent";
import { isActivityContinuationMessage } from "../lib/messageVisibility";
import { getState, setState, type ActivityItem, type QueuedMessage, type TodoListState, type UiMessage } from "./index";
import {
  reduceRunCompleted,
  reduceRunFailed,
  reduceRunStarted,
} from "./run-lifecycle";

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

const TODO_TOOL_NAME = "update_todos";

export function isTodoToolName(name: string | null | undefined): boolean {
  return name === TODO_TOOL_NAME;
}

interface ProjectionContext {
  state: TranscriptProjectionState;
  runtime?: TranscriptProjectionRuntime;
  update: (next: TranscriptProjectionState) => TranscriptProjectionState;
  latest: () => TranscriptProjectionState;
  commit: (next: TranscriptProjectionState) => TranscriptProjectionState;
}

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
  const suppressEntryMotion = event.replay === true;
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
            suppressEntryMotion,
          });
        }
        s.appendMessage({
          id: `meta-user-${event.run_id}`,
          role: "user",
          content: "",
          isMeta: true,
          suppressEntryMotion,
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
        suppressEntryMotion,
      });
      break;
    }

    case "TEXT_MESSAGE_START":
      if (!event.depth) ensureAssistantMessage(context, assistantIdFrom(event), ts, suppressEntryMotion);
      break;

    case "TEXT_MESSAGE_CONTENT":
      if (!event.depth) appendAssistantDelta(context, assistantIdFrom(event), event.delta, ts, suppressEntryMotion);
      break;

    case "TEXT_MESSAGE_END":
      if (!event.depth && event.content !== undefined) {
        reconcileAssistantContent(context, assistantIdFrom(event), event.content, ts, suppressEntryMotion);
      }
      break;
    case "REASONING_START":
    case "REASONING_MESSAGE_END":
    case "REASONING_END":
      break;

    case "REASONING_MESSAGE_START":
      if (!event.depth) {
        s.appendMessage({
          id: event.message_id,
          role: "reasoning",
          title: "Reasoning",
          content: "",
          suppressEntryMotion,
        });
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
          suppressEntryMotion,
        });
      }
      break;
    }

    case "TOOL_CALL_START": {
      if (isTodoToolName(event.tool_call_name)) break;
      const pending: PendingToolCall = {
        name: event.tool_call_name,
        description: event.description ?? "",
        argsBuffer: "",
        depth: event.depth ?? 0,
        parentId: event.parent_id ?? null,
        semanticKind: event.kind ?? "tool",
        startSeq: typeof event.seq === "number" ? event.seq : undefined,
      };
      const pendingToolCalls = new Map(context.state.pendingToolCalls);
      pendingToolCalls.set(event.tool_call_id, pending);
      context.update({ ...context.state, pendingToolCalls });
      appendActivityItemImmediately(context, activityItemFromPending(event.tool_call_id, pending), suppressEntryMotion);
      break;
    }

    case "TOOL_CALL_ARGS": {
      const pending = context.state.pendingToolCalls.get(event.tool_call_id);
      if (!pending) break;
      if (isTodoToolName(pending.name)) break;
      const argsBuffer = pending.argsBuffer + event.delta;
      const pendingToolCalls = new Map(context.state.pendingToolCalls);
      pendingToolCalls.set(event.tool_call_id, {
        ...pending,
        argsBuffer,
      });
      context.update({ ...context.state, pendingToolCalls });
      s.mergeActivityItem(event.tool_call_id, {
        args: argsBuffer,
        target: pending.description || formatCallTarget(pending.name, argsBuffer || "{}"),
      });
      break;
    }

    case "TOOL_CALL_END": {
      const pending = context.state.pendingToolCalls.get(event.tool_call_id);
      if (isTodoToolName(pending?.name)) {
        const pendingToolCalls = new Map(context.state.pendingToolCalls);
        pendingToolCalls.delete(event.tool_call_id);
        context.update({ ...context.state, pendingToolCalls });
        break;
      }
      const pendingToolCalls = new Map(context.state.pendingToolCalls);
      pendingToolCalls.delete(event.tool_call_id);
      context.update({ ...context.state, pendingToolCalls });
      if (!pending) break;

      const item = activityItemFromPending(event.tool_call_id, pending);
      const pendingPatch = takePendingResultPatch(context, item.id);
      const patch = pendingPatch
        ? { ...activityPatchFromPending(pending), ...pendingPatch }
        : activityPatchFromPending(pending);
      if (!s.mergeActivityItem(item.id, patch)) {
        appendActivityItemImmediately(context, pendingPatch ? { ...item, ...pendingPatch } : item, suppressEntryMotion);
      }
      break;
    }

    case "TOOL_CALL_RESULT": {
      if (isTodoToolName(event.name)) break;
      const result = event.content ?? event.preview ?? "";
      const patch: Partial<ActivityItem> = { result, status: "executed" };
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

    case "todo_updated": {
      if (s.currentRunId && s.currentRunId !== event.run_id) break;
      s.upsertTodoList(
        {
          id: `todo-${event.run_id}`,
          role: "todo",
          content: "",
          todo: {
            items: normalizeTodoItems(event.items),
            explanation: event.explanation ?? null,
          },
          suppressEntryMotion,
        },
        activityInsertAnchor(context),
      );
      break;
    }

    case "task_started": {
      const patch: Partial<ActivityItem> = {
        runId: event.run_id,
        status: "ongoing",
        taskStatus: "running",
        progress: event.summary ?? "running",
      };
      mergeOrBufferActivityPatch(context, [event.parent_tool_call_id, event.task_id], patch);
      break;
    }

    case "task_progress": {
      const taskStatus =
        event.status === "failed" || event.status === "cancelled" ? event.status : "running";
      const patch: Partial<ActivityItem> = {
        runId: event.run_id,
        status: taskStatus === "running" ? "ongoing" : "executed",
        taskStatus,
        progress: event.summary ?? event.status ?? "running",
      };
      mergeOrBufferActivityPatch(context, [event.parent_tool_call_id, event.task_id], patch);
      break;
    }

    case "task_finished": {
      const patch: Partial<ActivityItem> = {
        runId: event.run_id,
        status: "executed",
        taskStatus: event.status,
        progress: event.summary ?? event.status,
        cancelRequested: false,
      };
      mergeOrBufferActivityPatch(context, [event.parent_tool_call_id, event.task_id], patch);
      break;
    }

    case "compaction_started": {
      if (!event.parent_tool_call_id) break;
      mergeOrBufferActivityPatch(context, [event.parent_tool_call_id], {
        status: "ongoing",
        taskStatus: "running",
        progress: "compacting",
      });
      break;
    }

    case "compaction_finished": {
      if (!event.parent_tool_call_id) break;
      mergeOrBufferActivityPatch(context, [event.parent_tool_call_id], {
        progress: `compacted ${event.messages_before} -> ${event.messages_after} messages`,
      });
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
  let activeTodoId: string | null = null;

  const findActivity = (id: string) =>
    items.find((it) => it.id === id && it.role === "activity")?.activity;

  messages.forEach((msg, index) => {
    const sourceIndex = msg.seq ?? index;
    const sourceMessageId = msg.message_id ?? msg.id;
    const stableId = msg.id ?? msg.message_id ?? `history-${sourceIndex}`;
    const stampedAt = msg.created_at ? Date.parse(msg.created_at) : 0;

    if (msg.role === "user") {
      const hasVisibleMetaMarker = Boolean(msg.is_meta && stableId.startsWith("goal:"));
      if (!msg.is_meta || hasVisibleMetaMarker) {
        activeActivityId = null;
        activeTodoId = null;
      }
      if (hasVisibleMetaMarker) {
        items.push({
          id: `${stableId}-nudge`,
          role: "status",
          sourceIndex,
          sourceMessageId,
          suppressEntryMotion: true,
          content: "Goal nudge",
        });
      }
      items.push({
        id: stableId,
        role: "user",
        sourceIndex,
        sourceMessageId,
        suppressEntryMotion: true,
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
        suppressEntryMotion: true,
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
        suppressEntryMotion: true,
        content: msg.content,
        turn: stampedAt
          ? { startedAt: stampedAt, endedAt: stampedAt, durationMs: null }
          : undefined,
      });
    }

    if (msg.tool_calls && msg.tool_calls.length > 0) {
      const todoCalls = msg.tool_calls.filter((toolCall) => isTodoToolName(toolCall.name));
      const activityCalls = msg.tool_calls.filter((toolCall) => !isTodoToolName(toolCall.name));

      for (const toolCall of todoCalls) {
        const todo = todoStateFromArgs(toolCall.arguments || "");
        if (!todo) continue;
        if (!activeTodoId) {
          activeTodoId = `${stableId}-todo`;
          items.push({
            id: activeTodoId,
            role: "todo",
            sourceIndex,
            sourceMessageId,
            suppressEntryMotion: true,
            content: "",
            todo,
          });
        } else {
          const existing = items.find((it) => it.id === activeTodoId);
          if (existing) existing.todo = todo;
        }
      }

      if (activityCalls.length === 0) return;

      if (!activeActivityId) {
        activeActivityId = `${stableId}-activity`;
        items.push({
          id: activeActivityId,
          role: "activity",
          sourceIndex,
          sourceMessageId,
          suppressEntryMotion: true,
          content: "",
          activity: { items: [], label: "Called", done: true },
        });
      }
      const activity = findActivity(activeActivityId);
      if (activity) {
        for (const toolCall of activityCalls) {
          const args = toolCall.arguments || "";
          activity.items.push({
            id: toolCall.id,
            kind: toolCall.name,
            semanticKind:
              toolCall.kind === SEMANTIC_KIND_AGENT ? SEMANTIC_KIND_AGENT : undefined,
            target: formatCallTarget(toolCall.name, args || "{}"),
            args,
            result: resultsById.get(toolCall.id),
            status: "executed",
          });
        }
      }
    }
  });

  return items;
}

function todoStateFromArgs(argsJson: string): TodoListState | null {
  try {
    const parsed = JSON.parse(argsJson || "{}");
    if (!parsed || typeof parsed !== "object") return null;
    const items = normalizeTodoItems((parsed as { items?: unknown }).items);
    if (items.length === 0) return null;
    const explanation = (parsed as { explanation?: unknown }).explanation;
    return {
      items,
      explanation: typeof explanation === "string" ? explanation : null,
    };
  } catch {
    return null;
  }
}

function normalizeTodoItems(rawItems: unknown): TodoListState["items"] {
  if (!Array.isArray(rawItems)) return [];
  return rawItems.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const content = (item as { content?: unknown }).content;
    const status = (item as { status?: unknown }).status;
    if (typeof content !== "string" || content.trim().length === 0) return [];
    if (status !== "pending" && status !== "in_progress" && status !== "completed") return [];
    return [{ content, status }];
  });
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

function ensureAssistantMessage(
  context: ProjectionContext,
  id: string,
  startedAt: number,
  suppressEntryMotion?: boolean,
): void {
  const state = getState();
  setActiveAssistantMessageId(context, id);
  const existing = state.messages.get(id);
  if (existing?.role === "assistant") return;

  state.appendMessage({
    id,
    role: "assistant",
    content: "",
    turn: { startedAt, endedAt: null, durationMs: null },
    suppressEntryMotion,
  });
}

function appendAssistantDelta(
  context: ProjectionContext,
  id: string,
  delta: string,
  startedAt: number,
  suppressEntryMotion?: boolean,
): void {
  const state = getState();
  setActiveAssistantMessageId(context, id);
  const existing = state.messages.get(id);
  if (existing?.role === "assistant") {
    if (existing.content.trim().length === 0 && delta.trim().length > 0) {
      endActivity(state);
    }
    state.mutateMessage(id, { content: existing.content + delta });
    return;
  }

  endActivity(state);
  state.appendMessage({
    id,
    role: "assistant",
    content: delta,
    turn: { startedAt, endedAt: null, durationMs: null },
    suppressEntryMotion,
  });
}

function reconcileAssistantContent(
  context: ProjectionContext,
  id: string,
  content: string,
  startedAt: number,
  suppressEntryMotion?: boolean,
): void {
  const state = getState();
  setActiveAssistantMessageId(context, id);
  const existing = state.messages.get(id);
  if (existing?.role === "assistant") {
    if (existing.content.trim().length === 0 && content.trim().length > 0) {
      endActivity(state);
    }
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
    suppressEntryMotion,
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

function activityItemFromPending(id: string, pending: PendingToolCall): ActivityItem {
  return {
    id,
    kind: pending.name,
    semanticKind: pending.semanticKind === SEMANTIC_KIND_AGENT ? SEMANTIC_KIND_AGENT : undefined,
    target: pending.description || formatCallTarget(pending.name, pending.argsBuffer || "{}"),
    args: pending.argsBuffer,
    status: "ongoing",
    depth: pending.depth || undefined,
    parentToolId: pending.parentId ?? undefined,
  };
}

function activityPatchFromPending(pending: PendingToolCall): Partial<ActivityItem> {
  return {
    target: pending.description || formatCallTarget(pending.name, pending.argsBuffer || "{}"),
    args: pending.argsBuffer,
    depth: pending.depth || undefined,
    parentToolId: pending.parentId ?? undefined,
  };
}

function activityPatchFromItem(item: ActivityItem): Partial<ActivityItem> {
  return {
    target: item.target,
    args: item.args,
    depth: item.depth,
    parentToolId: item.parentToolId,
    semanticKind: item.semanticKind,
  };
}

function appendActivityItemImmediately(
  context: ProjectionContext,
  item: ActivityItem,
  suppressEntryMotion?: boolean,
): void {
  const state = getState();
  const pendingPatch = takePendingResultPatch(context, item.id);
  const nextItem = pendingPatch ? { ...item, ...pendingPatch } : item;
  const mergePatch = pendingPatch
    ? { ...activityPatchFromItem(nextItem), ...pendingPatch }
    : activityPatchFromItem(nextItem);
  if (state.mergeActivityItem(nextItem.id, mergePatch)) {
    return;
  }

  const activityId = activeActivityIdForToolAppend(state.activeActivityId);
  if (!activityId) {
    const newId = crypto.randomUUID();
    state.insertMessageBefore(
      {
        id: newId,
        role: "activity",
        content: "",
        activity: { items: [nextItem], label: "Calling", done: false },
        suppressEntryMotion,
      },
      activityInsertAnchor(context),
    );
    state.setActiveActivityId(newId);
    context.update({ ...context.state, nextItemRenderAt: Date.now() });
    return;
  }

  if (activityId !== state.activeActivityId) state.setActiveActivityId(activityId);
  state.appendActivityItem(activityId, nextItem);
  context.update({ ...context.state, nextItemRenderAt: Date.now() });
}

function activeActivityIdForToolAppend(activeActivityId: string | null): string | null {
  const state = getState();
  const active = activeActivityId ? state.messages.get(activeActivityId) : null;
  if (active?.role === "activity" && active.activity) {
    return activeActivityId;
  }

  for (let i = state.order.length - 1; i >= 0; i -= 1) {
    const message = state.messages.get(state.order[i]);
    if (!message) continue;
    if (message.role === "activity" && message.activity) {
      return message.id;
    }
    if (isActivityContinuationMessage(message)) continue;
    return null;
  }
  return null;
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

function mergeOrBufferActivityPatch(
  context: ProjectionContext,
  itemIds: Array<string | null | undefined>,
  patch: Partial<ActivityItem>,
) {
  const uniqueIds = Array.from(new Set(itemIds.filter((id): id is string => !!id)));
  const state = getState();
  for (const itemId of uniqueIds) {
    if (state.mergeActivityItem(itemId, patch)) return;
  }
  for (const itemId of uniqueIds) bufferActivityPatch(context, itemId, patch);
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
