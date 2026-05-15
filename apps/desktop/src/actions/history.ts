import { apiWithConfig, type HistoryMessage, type HistoryPage } from "../api";
import { getState, setState, type UiMessage } from "../store";
import { clearReplayGapBlockForSession } from "../store/chat-stream";
import {
  legacyFieldsFromSessionView,
  reduceHistoryLoadFailed,
  reduceHistoryLoadStarted,
} from "../store/session-view";
import { reduceRunCompleted, reduceRunStarted } from "../store/run-lifecycle";
import { rebuildTranscriptFromHistory } from "../store/transcript-projection";

type HistoryLoadMode = "replace" | "prepend" | "append";

const replaceHistoryLoadVersions = new Map<string, number>();

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
  const order = edge === "first" ? s.order : [...s.order].reverse();
  for (const id of order) {
    const msg = s.messages.get(id);
    if (msg?.sourceMessageId) return msg.sourceMessageId;
  }
  return null;
}

export function historyMessagesToUi(messages: HistoryMessage[], activeRunId: string | null): UiMessage[] {
  const items = rebuildTranscriptFromHistory(messages);

  // If the server has an active run for this session, the latest user
  // turn is still in flight. Clear its `endedAt` so TurnGroup doesn't
  // collapse it under "Worked for Xs" — the SSE replay + live events
  // build the in-flight UI on top of the history.
  if (activeRunId) {
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

export async function loadHistory(sessionId: string, options: LoadHistoryOptions = {}): Promise<void> {
  const s = getState();
  const mode = options.mode ?? "replace";
  let replaceLoadVersion: number | null = null;
  if (mode === "replace") {
    replaceLoadVersion = (replaceHistoryLoadVersions.get(sessionId) ?? 0) + 1;
    replaceHistoryLoadVersions.set(sessionId, replaceLoadVersion);
    const sessionView = reduceHistoryLoadStarted(s.sessionView, sessionId);
    setState({ sessionView, ...legacyFieldsFromSessionView(sessionView) });
  }

  let history: {
    messages: HistoryMessage[];
    active_run_id: string | null;
    page?: HistoryPage;
    usage?: { last_input_tokens: number; message_count: number };
  };
  try {
    history = await apiWithConfig(s.config, historyPath(sessionId, options));
  } catch (error) {
    if (mode === "replace") {
      if (replaceHistoryLoadVersions.get(sessionId) !== replaceLoadVersion) return;
      const state = getState();
      const sessionView = reduceHistoryLoadFailed(state.sessionView, sessionId);
      setState({ sessionView, ...legacyFieldsFromSessionView(sessionView) });
    }
    throw error;
  }

  if (getState().currentSessionId !== sessionId) return;
  if (
    mode === "replace" &&
    replaceHistoryLoadVersions.get(sessionId) !== replaceLoadVersion
  ) {
    return;
  }
  if (mode === "replace") {
    clearReplayGapBlockForSession(sessionId);
  }

  const { messages, active_run_id, page, usage } = history;
  const items = historyMessagesToUi(messages, active_run_id);
  if (mode === "prepend") {
    s.prependHistory(items, page);
  } else if (mode === "append") {
    s.appendHistoryPage(items, page);
  } else {
    s.setHistory(items, page);
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
  if (mode === "replace") {
    setState((state) =>
      active_run_id
        ? reduceRunStarted(state, { runId: active_run_id, sessionId })
        : reduceRunCompleted(state, { runId: state.currentRunId, sessionId }),
    );
  } else if (active_run_id) {
    setState((state) => reduceRunStarted(state, { runId: active_run_id, sessionId }));
  }
}

export async function loadOlderHistory(): Promise<void> {
  const s = getState();
  if (!s.currentSessionId || !s.historyHasMoreBefore || s.historyLoadingBefore) return;
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
  if (!s.currentSessionId || !s.historyHasMoreAfter || s.historyLoadingAfter) return;
  const after = historyBoundaryId(s, "last");
  if (!after) return;
  s.setHistoryLoading("after", true);
  try {
    await loadHistory(s.currentSessionId, { mode: "append", after });
  } finally {
    getState().setHistoryLoading("after", false);
  }
}
