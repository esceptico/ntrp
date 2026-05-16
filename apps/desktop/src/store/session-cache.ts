import type { CachedSessionState, SessionUsage, State } from "./types";
import { createInitialSessionViewState } from "./session-view";

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
    usage: initialUsage,
    editingId: null,
    activeActivityId: null,
    compacting: false,
    lastCompaction: null,
    sourceFocus: null,
    pendingApprovals: [],
    reviewingApprovalToolId: null,
    queuedMessages: [],
    pendingResume: null,
    stoppingRunId: null,
  };
}

export function snapshotSession(s: State): CachedSessionState {
  return {
    sessionView: s.sessionView,
    messages: s.messages,
    order: s.order,
    running: s.running,
    currentRunId: s.currentRunId,
    usage: s.usage,
    editingId: s.editingId,
    activeActivityId: s.activeActivityId,
    compacting: s.compacting,
    lastCompaction: s.lastCompaction,
    sourceFocus: s.sourceFocus,
    pendingApprovals: s.pendingApprovals,
    reviewingApprovalToolId: s.reviewingApprovalToolId,
    queuedMessages: s.queuedMessages,
    pendingResume: s.pendingResume,
    stoppingRunId: s.stoppingRunId,
  };
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
