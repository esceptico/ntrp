import {
  apiWithConfig,
  type HistoryMessage,
  type HistoryPage,
  type SessionRuntimeSnapshot,
} from "../api";
import { getState, setState, type UiMessage } from "../store";
import { clearReplayGapBlockForSession, setEventCursorForSession } from "../store/chat-stream";
import {
  isCurrentHistoryReplaceRequestVersion,
  nextHistoryReplaceRequestVersion,
  reduceHistoryLoadFailed,
  reduceHistoryLoadStarted,
} from "../store/session-view";
import {
  reduceForegroundRunCleared,
  reduceRunCompleted,
  reduceRunStarted,
} from "../store/run-lifecycle";
import {
  isTodoToolName,
  newestHistoryActivityId,
  rebuildTranscriptFromHistory,
} from "../store/transcript-projection";
import { normalizeActivityGroups } from "../store/session-cache";
import { isForegroundRunStatus } from "../lib/runStatus";

type HistoryLoadMode = "replace" | "prepend" | "append";
const pendingHistoryToolResultsBySession = new Map<string, Map<string, string>>();

export interface LoadHistoryOptions {
  mode?: HistoryLoadMode;
  before?: string;
  after?: string;
  around?: string;
  aroundSeq?: number;
  limit?: number;
}

function historyPath(sessionId: string, options: LoadHistoryOptions): string {
  const params = new URLSearchParams({ session_id: sessionId });
  if (options.limit) params.set("limit", String(options.limit));
  if (options.before) params.set("before", options.before);
  if (options.after) params.set("after", options.after);
  if (options.around) params.set("around", options.around);
  if (options.aroundSeq !== undefined) params.set("around_seq", String(options.aroundSeq));
  return `/session/history?${params.toString()}`;
}

function historyBoundaryId(
  s: ReturnType<typeof getState>,
  edge: "first" | "last",
): string | null {
  const cursor = edge === "first" ? s.sessionView.historyBeforeCursor : s.sessionView.historyAfterCursor;
  if (cursor) return cursor;
  const order = edge === "first" ? s.order : [...s.order].reverse();
  for (const id of order) {
    const msg = s.messages.get(id);
    if (msg?.sourceMessageId) return msg.sourceMessageId;
  }
  return null;
}

export function historyMessagesToUi(
  messages: HistoryMessage[],
  activeRunId: string | null,
  options: { isNewestPage?: boolean } = {},
): UiMessage[] {
  const isNewestPage = options.isNewestPage ?? true;
  const items = rebuildTranscriptFromHistory(messages, { activeRunId, isNewestPage });

  // If the server has an active run for this session, the latest user
  // turn is still in flight. Clear its `endedAt` so TurnGroup doesn't
  // collapse it under "Worked for Xs" — the SSE replay + live events
  // build the in-flight UI on top of the history.
  if (activeRunId && isNewestPage) {
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      if (it.role === "user" && it.turn) {
        it.turn = { ...it.turn, endedAt: null, durationMs: null };
        break;
      }
    }
  }

  return items;
}

function normalizeHistoryItems(
  items: UiMessage[],
  activeActivityId: string | null,
): { items: UiMessage[]; activeActivityId: string | null } {
  const map = new Map<string, UiMessage>();
  const order: string[] = [];
  for (const item of items) {
    map.set(item.id, item);
    order.push(item.id);
  }
  const normalized = normalizeActivityGroups(map, order, activeActivityId);
  return {
    items: normalized.order.flatMap((id) => {
      const item = normalized.messages.get(id);
      return item ? [item] : [];
    }),
    activeActivityId: normalized.activeActivityId,
  };
}

function applyHistoryToolResults(sessionId: string, messages: HistoryMessage[]): void {
  const state = getState();
  const todoToolCallIds = new Set<string>();
  for (const msg of messages) {
    for (const toolCall of msg.tool_calls ?? []) {
      if (isTodoToolName(toolCall.name)) todoToolCallIds.add(toolCall.id);
    }
  }
  for (const msg of messages) {
    if (msg.role !== "tool" || !msg.tool_call_id) continue;
    if (todoToolCallIds.has(msg.tool_call_id)) continue;
    if (state.mergeActivityItem(msg.tool_call_id, { result: msg.content, status: "executed" })) continue;
    let pending = pendingHistoryToolResultsBySession.get(sessionId);
    if (!pending) {
      pending = new Map();
      pendingHistoryToolResultsBySession.set(sessionId, pending);
    }
    pending.set(msg.tool_call_id, msg.content);
  }
}

function applyPendingHistoryToolResults(sessionId: string): void {
  const pending = pendingHistoryToolResultsBySession.get(sessionId);
  if (!pending) return;
  const state = getState();
  for (const [toolCallId, result] of pending) {
    if (state.mergeActivityItem(toolCallId, { result, status: "executed" })) {
      pending.delete(toolCallId);
    }
  }
  if (pending.size === 0) pendingHistoryToolResultsBySession.delete(sessionId);
}

function foregroundActiveRunId(
  activeRunId: string | null,
  runtime: SessionRuntimeSnapshot | undefined,
): string | null {
  if (!runtime) return activeRunId;
  return isForegroundRunStatus(runtime.active_run?.status) ? activeRunId : null;
}

function syncAutoForActiveRun(sessionId: string, value: boolean): void {
  const { config } = getState();
  void apiWithConfig(config, `/sessions/${sessionId}/auto`, {
    method: "POST",
    body: JSON.stringify({ value }),
  }).catch(() => {
    // Best-effort reconnect repair. The next user message still carries the
    // client-owned Auto value, so a transient sync miss is not fatal.
  });
}

function applyRuntimeSnapshot(sessionId: string, runtime: SessionRuntimeSnapshot | undefined): void {
  if (!runtime) return;
  setEventCursorForSession(sessionId, runtime.checkpoint_seq);
  const activeRun = runtime.active_run;
  const hasForegroundRun = isForegroundRunStatus(activeRun?.status);
  if (getState().skipApprovals && hasForegroundRun) {
    syncAutoForActiveRun(sessionId, true);
  }
  setState((state) => {
    const pendingApprovals = state.skipApprovals || !hasForegroundRun ? [] : runtime.pending_approvals;
      const lifecycle =
        activeRun && hasForegroundRun
          ? reduceRunStarted(state, { runId: activeRun.run_id, sessionId })
        : reduceForegroundRunCleared(state, {
            runId: activeRun?.run_id ?? state.currentRunId,
            sessionId,
            markBackgrounded: activeRun?.status === "backgrounded",
          });
    return {
      ...lifecycle,
      pendingApprovals: pendingApprovals.map((approval) => ({
        toolId: approval.tool_id,
        toolName: approval.tool_name,
        preview: approval.preview ?? undefined,
        diff: approval.diff ?? undefined,
        status: "pending" as const,
      })),
      queuedMessages: (hasForegroundRun ? runtime.queued_messages : []).map((message) => ({
        clientId: message.client_id,
        text: message.text,
        images: message.images,
        status: message.status,
        enqueuedAt: message.enqueued_at ? Date.parse(message.enqueued_at) : Date.now(),
      })),
    };
  });
}

export async function loadHistory(sessionId: string, options: LoadHistoryOptions = {}): Promise<void> {
  const s = getState();
  const mode = options.mode ?? "replace";
  let replaceLoadVersion: number | null = null;
  if (mode === "replace") {
    replaceLoadVersion = nextHistoryReplaceRequestVersion(sessionId);
    const sessionView = reduceHistoryLoadStarted(s.sessionView, sessionId);
    setState({ sessionView });
  }

  let history: {
    messages: HistoryMessage[];
    active_run_id: string | null;
    runtime?: SessionRuntimeSnapshot;
    page?: HistoryPage;
    usage?: { last_input_tokens: number; message_count: number };
  };
  try {
    history = await apiWithConfig(s.config, historyPath(sessionId, options));
  } catch (error) {
    if (mode === "replace") {
      if (!isCurrentHistoryReplaceRequestVersion(sessionId, replaceLoadVersion ?? 0)) return;
      const state = getState();
      const sessionView = reduceHistoryLoadFailed(state.sessionView, sessionId);
      setState({ sessionView });
    }
    throw error;
  }

  if (getState().currentSessionId !== sessionId) return;
  if (
    mode === "replace" &&
    !isCurrentHistoryReplaceRequestVersion(sessionId, replaceLoadVersion ?? 0)
  ) {
    return;
  }
  if (mode === "replace") {
    clearReplayGapBlockForSession(sessionId);
    pendingHistoryToolResultsBySession.delete(sessionId);
  }

  const { messages, active_run_id, runtime, page, usage } = history;
  const activeForegroundRunId = foregroundActiveRunId(active_run_id, runtime);
  const isNewestPage = mode !== "prepend" && page?.has_more_after !== true;
  const rawItems = historyMessagesToUi(messages, activeForegroundRunId, { isNewestPage });
  const rawActiveActivityId = activeForegroundRunId ? newestHistoryActivityId(rawItems) : null;
  const { items, activeActivityId } = normalizeHistoryItems(rawItems, rawActiveActivityId);
  if (mode === "prepend") {
    s.prependHistory(items, page);
    applyHistoryToolResults(sessionId, messages);
  } else if (mode === "append") {
    s.appendHistoryPage(items, page, isNewestPage ? activeActivityId : null);
    applyHistoryToolResults(sessionId, messages);
  } else {
    s.setHistory(items, page);
    setState({ activeActivityId });
    // Only hydrate the budget snapshot on a fresh load — paging in older /
    // newer chunks doesn't change "what the agent's current context size
    // looks like" so we leave the dial alone.
    if (usage) {
      s.hydrateUsageSnapshot({
        lastPrompt: usage.last_input_tokens,
        messageCount: usage.message_count,
      });
    }
  }
  applyPendingHistoryToolResults(sessionId);
  if (mode === "replace") {
    if (runtime) {
      applyRuntimeSnapshot(sessionId, runtime);
    } else {
      setState((state) =>
        activeForegroundRunId
          ? reduceRunStarted(state, { runId: activeForegroundRunId, sessionId })
          : reduceRunCompleted(state, { runId: state.currentRunId, sessionId }),
      );
    }
  } else if (activeForegroundRunId) {
    setState((state) => reduceRunStarted(state, { runId: activeForegroundRunId, sessionId }));
  }
}

export async function loadOlderHistory(): Promise<void> {
  const s = getState();
  if (!s.currentSessionId || !s.sessionView.historyHasMoreBefore || s.sessionView.historyLoadingBefore) return;
  const before = historyBoundaryId(s, "first");
  if (!before) return;
  s.setHistoryLoading("before", true);
  try {
    await loadHistory(s.currentSessionId, { mode: "prepend", before });
  } finally {
    getState().setHistoryLoading("before", false);
  }
}

export async function loadNewerHistory(): Promise<void> {
  const s = getState();
  if (!s.currentSessionId || !s.sessionView.historyHasMoreAfter || s.sessionView.historyLoadingAfter) return;
  const after = historyBoundaryId(s, "last");
  if (!after) return;
  s.setHistoryLoading("after", true);
  try {
    await loadHistory(s.currentSessionId, { mode: "append", after });
  } finally {
    getState().setHistoryLoading("after", false);
  }
}
