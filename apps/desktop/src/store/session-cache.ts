import type { CachedSessionState, SessionUsage, State, UiMessage } from "./types";
import { createInitialSessionViewState } from "./session-view";
import { isActivityContinuationMessage } from "../lib/messageVisibility";

export const initialUsage: SessionUsage = {
  lastPrompt: 0,
  totalTokens: 0,
  totalCost: 0,
  messageCount: 0,
};

export function blankSessionView(): CachedSessionState {
  return {
    sessionView: createInitialSessionViewState(),
    messages: new Map(),
    order: [],
    running: false,
    currentRunId: null,
    thinkingRunId: null,
    thinkingStatus: null,
    usage: initialUsage,
    editingId: null,
    activeActivityId: null,
    compacting: false,
    sourceFocus: null,
    pendingApprovals: [],
    reviewingApprovalToolId: null,
    queuedMessages: [],
    pendingResume: null,
    stoppingRunId: null,
  };
}

export function snapshotSession(s: State): CachedSessionState {
  const transcript = normalizeActivityGroups(s.messages, s.order, s.activeActivityId);
  return {
    sessionView: s.sessionView,
    messages: transcript.messages,
    order: transcript.order,
    running: s.running,
    currentRunId: s.currentRunId,
    thinkingRunId: s.thinkingRunId,
    thinkingStatus: s.thinkingStatus,
    usage: s.usage,
    editingId: s.editingId,
    activeActivityId: transcript.activeActivityId,
    compacting: false,
    sourceFocus: s.sourceFocus,
    pendingApprovals: s.pendingApprovals,
    reviewingApprovalToolId: s.reviewingApprovalToolId,
    queuedMessages: s.queuedMessages,
    pendingResume: s.pendingResume,
    stoppingRunId: s.stoppingRunId,
  };
}

export function normalizeCachedSessionState(view: CachedSessionState): CachedSessionState {
  const transcript = normalizeActivityGroups(view.messages, view.order, view.activeActivityId);
  return {
    ...view,
    messages: suppressEntryMotion(transcript.messages),
    order: transcript.order,
    activeActivityId: transcript.activeActivityId,
    thinkingRunId: view.running ? view.thinkingRunId ?? null : null,
    thinkingStatus: view.running ? view.thinkingStatus ?? null : null,
    compacting: false,
  };
}

function suppressEntryMotion(messages: Map<string, UiMessage>): Map<string, UiMessage> {
  const next = new Map<string, UiMessage>();
  for (const [id, message] of messages) {
    next.set(id, { ...message, suppressEntryMotion: true });
  }
  return next;
}

export function normalizeActivityGroups(
  sourceMessages: Map<string, UiMessage>,
  sourceOrder: string[],
  activeActivityId: string | null,
): { messages: Map<string, UiMessage>; order: string[]; activeActivityId: string | null } {
  const messages = new Map<string, UiMessage>();
  const order: string[] = [];
  const activityRedirects = new Map<string, string>();
  let openActivityId: string | null = null;

  for (const id of sourceOrder) {
    const message = sourceMessages.get(id);
    if (!message) continue;

    if (message.role === "activity" && message.activity) {
      if (openActivityId) {
        mergeActivity(messages, openActivityId, message);
        activityRedirects.set(id, openActivityId);
        continue;
      }
      openActivityId = id;
    } else if (isVisibleActivityBoundary(message)) {
      openActivityId = null;
    }

    messages.set(id, message);
    order.push(id);
  }

  return {
    messages,
    order,
    activeActivityId: activeActivityId ? (activityRedirects.get(activeActivityId) ?? activeActivityId) : null,
  };
}

function mergeActivity(messages: Map<string, UiMessage>, targetId: string, source: UiMessage): void {
  const target = messages.get(targetId);
  if (!target?.activity || !source.activity) return;
  const done = target.activity.done && source.activity.done;
  messages.set(targetId, {
    ...target,
    activity: {
      items: [...target.activity.items, ...source.activity.items],
      done,
      label: done ? source.activity.label : "Calling",
    },
  });
}

function isVisibleActivityBoundary(message: UiMessage): boolean {
  return !isActivityContinuationMessage(message);
}

export function clearCachedStoppingRun(
  s: State,
  sessionId: string | null,
  runId: string,
): Pick<State, "sessionCache"> | {} {
  if (!sessionId) return {};
  const cached = s.sessionCache.get(sessionId);
  if (!cached || cached.stoppingRunId !== runId) return {};
  const sessionCache = new Map(s.sessionCache);
  sessionCache.set(sessionId, { ...cached, stoppingRunId: null });
  return { sessionCache };
}
