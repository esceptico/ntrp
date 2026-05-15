import type { CachedSessionState, SessionUsage, State } from "./types";

export const initialUsage: SessionUsage = {
  lastPrompt: 0,
  totalTokens: 0,
  totalCost: 0,
};

export function blankSessionView(): CachedSessionState {
  return {
    messages: new Map(),
    order: [],
    historyLoadedFor: null,
    historyHasMoreBefore: false,
    historyHasMoreAfter: false,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
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
  };
}

export function snapshotSession(s: State): CachedSessionState {
  return {
    messages: s.messages,
    order: s.order,
    historyLoadedFor: s.historyLoadedFor,
    historyHasMoreBefore: s.historyHasMoreBefore,
    historyHasMoreAfter: s.historyHasMoreAfter,
    historyLoadingBefore: s.historyLoadingBefore,
    historyLoadingAfter: s.historyLoadingAfter,
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
  };
}
