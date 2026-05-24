import type {
  HistoryMessage,
  HistoryPage,
  SessionRuntimeSnapshot,
} from "../api";
import { isForegroundRunStatus } from "../lib/runStatus";
import {
  newestHistoryActivityId,
  rebuildTranscriptFromHistory,
} from "./transcript-projection";
import {
  blankSessionView,
  initialUsage,
  normalizeActivityGroups,
} from "./session-cache";
import {
  createInitialSessionViewState,
  reduceHistoryLoadSucceeded,
} from "./session-view";
import type {
  ApprovalState,
  CachedSessionState,
  QueuedMessage,
  UiMessage,
} from "./types";

export interface HistoryResponse {
  messages: HistoryMessage[];
  active_run_id: string | null;
  runtime?: SessionRuntimeSnapshot;
  page?: HistoryPage;
  usage?: { last_input_tokens: number; message_count: number };
}

export interface HistoryProjection {
  activeForegroundRunId: string | null;
  activeActivityId: string | null;
  items: UiMessage[];
}

export interface RuntimeView {
  hasForegroundRun: boolean;
  currentRunId: string | null;
  activeRunId: string | null;
  markBackgrounded: boolean;
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

export function projectHistoryResponse(
  history: HistoryResponse,
  isNewestPage: boolean,
): HistoryProjection {
  const activeForegroundRunId = foregroundActiveRunId(history.active_run_id, history.runtime);
  const rawItems = historyMessagesToUi(history.messages, activeForegroundRunId, { isNewestPage });
  const rawActiveActivityId = activeForegroundRunId ? newestHistoryActivityId(rawItems) : null;
  const { items, activeActivityId } = normalizeHistoryItems(rawItems, rawActiveActivityId);
  return { activeForegroundRunId, activeActivityId, items };
}

export function runtimeView(
  activeForegroundRunId: string | null,
  runtime: SessionRuntimeSnapshot | undefined,
): RuntimeView {
  const activeRun = runtime?.active_run;
  const hasForegroundRun = runtime
    ? isForegroundRunStatus(activeRun?.status)
    : Boolean(activeForegroundRunId);
  return {
    hasForegroundRun,
    currentRunId: hasForegroundRun ? activeRun?.run_id ?? activeForegroundRunId : null,
    activeRunId: activeRun?.run_id ?? activeForegroundRunId,
    markBackgrounded: activeRun?.status === "backgrounded",
  };
}

export function pendingApprovalsFromRuntime(
  runtime: SessionRuntimeSnapshot | undefined,
  hasForegroundRun: boolean,
  skipApprovals: boolean,
): ApprovalState[] {
  if (!runtime || skipApprovals || !hasForegroundRun) return [];
  return runtime.pending_approvals.map((approval) => ({
    toolId: approval.tool_id,
    toolName: approval.tool_name,
    preview: approval.preview ?? undefined,
    diff: approval.diff ?? undefined,
    status: "pending" as const,
  }));
}

export function queuedMessagesFromRuntime(
  runtime: SessionRuntimeSnapshot | undefined,
  hasForegroundRun: boolean,
): QueuedMessage[] {
  if (!runtime || !hasForegroundRun) return [];
  return runtime.queued_messages.map((message) => ({
    clientId: message.client_id,
    text: message.text,
    images: message.images,
    status: message.status,
    enqueuedAt: message.enqueued_at ? Date.parse(message.enqueued_at) : Date.now(),
  }));
}

export function cachedSessionFromHistory(
  sessionId: string,
  history: HistoryResponse,
  existing: CachedSessionState | undefined,
  skipApprovals: boolean,
): CachedSessionState {
  const base = existing ?? blankSessionView();
  const { runtime, page, usage } = history;
  const { activeForegroundRunId, activeActivityId, items } = projectHistoryResponse(
    history,
    page?.has_more_after !== true,
  );
  const view = runtimeView(activeForegroundRunId, runtime);
  const map = new Map<string, UiMessage>();
  const order: string[] = [];
  for (const item of items) {
    map.set(item.id, { ...item, suppressEntryMotion: true });
    order.push(item.id);
  }

  const sessionView = reduceHistoryLoadSucceeded(
    { ...createInitialSessionViewState(), currentSessionId: sessionId },
    sessionId,
    page,
  );

  return {
    ...base,
    sessionView,
    messages: map,
    order,
    running: view.hasForegroundRun,
    currentRunId: view.currentRunId,
    usage: usage
      ? {
          ...(base.usage ?? initialUsage),
          lastPrompt: usage.last_input_tokens,
          messageCount: usage.message_count,
        }
      : base.usage,
    activeActivityId,
    compacting: false,
    pendingApprovals: pendingApprovalsFromRuntime(runtime, view.hasForegroundRun, skipApprovals),
    reviewingApprovalToolId: null,
    queuedMessages: queuedMessagesFromRuntime(runtime, view.hasForegroundRun),
  };
}

function foregroundActiveRunId(
  activeRunId: string | null,
  runtime: SessionRuntimeSnapshot | undefined,
): string | null {
  if (!runtime) return activeRunId;
  return isForegroundRunStatus(runtime.active_run?.status) ? activeRunId : null;
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
