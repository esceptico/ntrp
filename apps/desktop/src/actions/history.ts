import { apiWithConfig, type HistoryMessage, type HistoryPage } from "../api";
import { getState, type UiMessage } from "../store";
import { SEMANTIC_KIND_AGENT } from "../lib/agent";
import { clearReplayGapBlockForSession, forgetEventSeqForSession } from "../hooks/useEvents";
import { formatCall } from "./_shared";

type HistoryLoadMode = "replace" | "prepend" | "append";

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
  // Pre-index tool results so we can attach them to their calls regardless
  // of ordering between the assistant message and its `tool` follow-ups.
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
    // Prefer the stable server-issued id; fall back to a positional id for
    // older sessions whose messages were saved before id-based persistence.
    const sourceIndex = msg.seq ?? index;
    const sourceMessageId = msg.message_id ?? msg.id;
    const stableId = msg.id ?? msg.message_id ?? `history-${sourceIndex}`;
    const stampedAt = msg.created_at ? Date.parse(msg.created_at) : 0;

    if (msg.role === "user") {
      activeActivityId = null;
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

    if (msg.role === "tool") {
      // Already folded into the matching activity item via resultsById.
      return;
    }

    // assistant
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
        for (const tc of msg.tool_calls) {
          const args = tc.arguments || "";
          activity.items.push({
            id: tc.id,
            kind: tc.name,
            semanticKind:
              tc.kind === SEMANTIC_KIND_AGENT ? SEMANTIC_KIND_AGENT : undefined,
            target: formatCall(tc.name, args || "{}"),
            args,
            result: resultsById.get(tc.id),
          });
        }
      }
    }
  });

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
  const { messages, active_run_id, page } = await apiWithConfig<{
    messages: HistoryMessage[];
    active_run_id: string | null;
    page?: HistoryPage;
  }>(s.config, historyPath(sessionId, options));

  if (getState().currentSessionId !== sessionId) return;
  const mode = options.mode ?? "replace";
  if (mode === "replace") {
    forgetEventSeqForSession(sessionId);
    clearReplayGapBlockForSession(sessionId);
  }

  const items = historyMessagesToUi(messages, active_run_id);
  if (mode === "prepend") {
    s.prependHistory(items, page);
  } else if (mode === "append") {
    s.appendHistoryPage(items, page);
  } else {
    s.setHistory(items, page);
  }
  if (active_run_id) {
    s.setRunning(true);
    s.setCurrentRunId(active_run_id);
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
