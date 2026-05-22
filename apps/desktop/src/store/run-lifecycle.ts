import type {
  ApprovalState,
  QueuedMessage,
  QueuedMessageStatus,
  State,
} from "./types";

type RunLifecyclePatch = Partial<
  Pick<
    State,
    | "running"
    | "currentRunId"
    | "activeRunSessionIds"
    | "unreadDoneSessionIds"
    | "pendingApprovals"
    | "reviewingApprovalToolId"
    | "queuedMessages"
    | "pendingResume"
    | "stoppingRunId"
    | "terminalRunIds"
  >
>;

export interface RunStatusSnapshot {
  runId?: string | null;
  sessionId: string;
  status?: string | null;
}

export function reduceRunStarted(
  state: State,
  input: { runId: string | null; sessionId: string },
): RunLifecyclePatch {
  if (input.runId && state.terminalRunIds.has(input.runId)) {
    return state.stoppingRunId === input.runId ? { stoppingRunId: null } : {};
  }

  const appliesToCurrentSession =
    state.currentSessionId === null || state.currentSessionId === input.sessionId;
  const activeRunSessionIds = new Set(state.activeRunSessionIds);
  activeRunSessionIds.add(input.sessionId);

  return {
    running: appliesToCurrentSession ? true : state.running,
    currentRunId: appliesToCurrentSession ? input.runId : state.currentRunId,
    activeRunSessionIds,
    pendingResume: null,
    stoppingRunId: input.runId && state.stoppingRunId === input.runId ? null : state.stoppingRunId,
  };
}

export function reduceRunStatus(
  state: State,
  input: { activeRuns: RunStatusSnapshot[] },
): RunLifecyclePatch {
  let terminalRunIds = state.terminalRunIds;
  const activeRuns: RunStatusSnapshot[] = [];
  let terminalCurrentRun: RunStatusSnapshot | null = null;

  for (const run of input.activeRuns) {
    if (run.runId && isTerminalStatus(run.status)) {
      terminalRunIds = addTerminalRunId(terminalRunIds, run.runId);
      const appliesToCurrentSession =
        !state.currentSessionId || state.currentSessionId === run.sessionId;
      const isOptimisticCurrentRun =
        state.running &&
        state.currentRunId === null &&
        state.activeRunSessionIds.has(run.sessionId);
      if (
        appliesToCurrentSession &&
        (state.currentRunId === run.runId || isOptimisticCurrentRun)
      ) {
        terminalCurrentRun = run;
      }
      continue;
    }
    if (run.runId && terminalRunIds.has(run.runId)) continue;
    activeRuns.push(run);
  }

  const activeRunSessionIds = new Set(activeRuns.map((run) => run.sessionId));
  const unreadDoneSessionIds = unreadAfterActiveSetChange(
    state,
    activeRunSessionIds,
  );
  const current = state.currentSessionId
    ? activeRuns.find((run) => run.sessionId === state.currentSessionId)
    : undefined;

  if (terminalCurrentRun) {
    return {
      activeRunSessionIds,
      unreadDoneSessionIds,
      running: false,
      currentRunId: null,
      pendingResume: null,
      stoppingRunId:
        terminalCurrentRun.runId && state.stoppingRunId === terminalCurrentRun.runId
          ? null
          : state.stoppingRunId,
      ...(terminalRunIds !== state.terminalRunIds ? { terminalRunIds } : {}),
    };
  }

  if (
    state.currentSessionId &&
    state.running &&
    state.currentRunId &&
    !current
  ) {
    return {
      activeRunSessionIds,
      unreadDoneSessionIds,
      running: false,
      currentRunId: null,
      pendingResume: null,
      stoppingRunId:
        state.stoppingRunId === state.currentRunId ? null : state.stoppingRunId,
      ...(terminalRunIds !== state.terminalRunIds ? { terminalRunIds } : {}),
    };
  }

  return {
    activeRunSessionIds,
    unreadDoneSessionIds,
    ...(current
      ? {
          running: true,
          currentRunId: current.runId ?? state.currentRunId,
        }
      : {}),
    ...(terminalRunIds !== state.terminalRunIds ? { terminalRunIds } : {}),
  };
}

export function reduceRunCompleted(
  state: State,
  input: { runId: string | null; sessionId?: string | null; clearApprovals?: boolean },
): RunLifecyclePatch {
  return reduceTerminalRun(state, input, "completed");
}

export function reduceRunFailed(
  state: State,
  input: { runId: string | null; sessionId?: string | null },
): RunLifecyclePatch {
  return reduceTerminalRun(state, input, "failed");
}

export function reduceApprovalRequested(
  state: State,
  approval: ApprovalState,
): RunLifecyclePatch {
  const pendingApprovals = state.pendingApprovals.filter(
    (item) => item.toolId !== approval.toolId,
  );
  pendingApprovals.push(approval);
  return { pendingApprovals };
}

export function reduceApprovalResolved(
  state: State,
  toolId: string,
): RunLifecyclePatch {
  return {
    pendingApprovals: state.pendingApprovals.filter((item) => item.toolId !== toolId),
    reviewingApprovalToolId:
      state.reviewingApprovalToolId === toolId ? null : state.reviewingApprovalToolId,
  };
}

export function reduceQueuedMessageAdded(
  state: State,
  message: QueuedMessage,
): RunLifecyclePatch {
  return { queuedMessages: [...state.queuedMessages, message] };
}

export function reduceQueuedMessageStatus(
  state: State,
  clientId: string,
  status: QueuedMessageStatus,
): RunLifecyclePatch {
  return {
    queuedMessages: state.queuedMessages.map((message) =>
      message.clientId === clientId ? { ...message, status } : message,
    ),
  };
}

export function reduceQueuedMessageRemoved(
  state: State,
  clientId: string,
): RunLifecyclePatch {
  return {
    queuedMessages: state.queuedMessages.filter((message) => message.clientId !== clientId),
  };
}

export function reduceQueuedMessagesCleared(): RunLifecyclePatch {
  return { queuedMessages: [] };
}

export function reduceQueuedMessagesPersisted(
  state: State,
  persistedIds: Set<string>,
): RunLifecyclePatch {
  return {
    queuedMessages: state.queuedMessages.filter(
      (message) => !persistedIds.has(message.clientId),
    ),
  };
}

export function reduceCancellingQueuedMessagesReset(state: State): RunLifecyclePatch {
  return {
    queuedMessages: state.queuedMessages.map((message) =>
      message.status === "cancelling" ? { ...message, status: "pending" } : message,
    ),
  };
}

export function reduceRunStopRequested(
  state: State,
  runId: string,
): RunLifecyclePatch {
  if (state.currentRunId && state.currentRunId !== runId) return {};
  return { stoppingRunId: runId };
}

export function reduceRunStopCleared(
  state: State,
  runId: string,
): RunLifecyclePatch {
  if (state.stoppingRunId !== runId) return {};
  return { stoppingRunId: null };
}

function reduceTerminalRun(
  state: State,
  input: { runId: string | null; sessionId?: string | null; clearApprovals?: boolean },
  _phase: "completed" | "failed",
): RunLifecyclePatch {
  if (
    !input.runId &&
    input.sessionId &&
    state.currentSessionId &&
    input.sessionId !== state.currentSessionId
  ) {
    const activeRunSessionIds = new Set(state.activeRunSessionIds);
    activeRunSessionIds.delete(input.sessionId);
    return {
      activeRunSessionIds,
      unreadDoneSessionIds: unreadAfterActiveSetChange(state, activeRunSessionIds),
    };
  }

  if (input.runId && state.currentRunId && state.currentRunId !== input.runId) {
    const terminalRunIds = addTerminalRunId(state.terminalRunIds, input.runId);
    if (!input.sessionId || input.sessionId === state.currentSessionId) {
      return terminalRunIds !== state.terminalRunIds ? { terminalRunIds } : {};
    }

    const activeRunSessionIds = new Set(state.activeRunSessionIds);
    activeRunSessionIds.delete(input.sessionId);
    return {
      activeRunSessionIds,
      unreadDoneSessionIds: unreadAfterActiveSetChange(state, activeRunSessionIds),
      terminalRunIds,
    };
  }

  const sessionId = input.sessionId ?? state.currentSessionId;
  const activeRunSessionIds = new Set(state.activeRunSessionIds);
  if (sessionId) activeRunSessionIds.delete(sessionId);

  const unreadDoneSessionIds = unreadAfterActiveSetChange(state, activeRunSessionIds);
  const terminalRunIds = input.runId
    ? addTerminalRunId(state.terminalRunIds, input.runId)
    : state.terminalRunIds;

  return {
    running: false,
    currentRunId: null,
    activeRunSessionIds,
    unreadDoneSessionIds,
    pendingResume: null,
    stoppingRunId:
      input.runId && state.stoppingRunId === input.runId ? null : state.stoppingRunId,
    ...(terminalRunIds !== state.terminalRunIds ? { terminalRunIds } : {}),
    ...(input.clearApprovals
      ? { pendingApprovals: [], reviewingApprovalToolId: null }
      : {}),
  };
}

function unreadAfterActiveSetChange(
  state: State,
  nextActive: Set<string>,
): Set<string> {
  let unread = state.unreadDoneSessionIds;
  for (const prev of state.activeRunSessionIds) {
    if (!nextActive.has(prev) && prev !== state.currentSessionId) {
      if (unread === state.unreadDoneSessionIds) unread = new Set(unread);
      unread.add(prev);
    }
  }
  return unread;
}

function addTerminalRunId(previous: Set<string>, runId: string): Set<string> {
  const next = new Set(previous);
  next.add(runId);
  while (next.size > 200) {
    const oldest = next.values().next().value;
    if (!oldest) break;
    next.delete(oldest);
  }
  return next;
}

function isTerminalStatus(status: string | null | undefined): boolean {
  return (
    status === "completed" ||
    status === "cancelled" ||
    status === "error" ||
    status === "failed" ||
    status === "interrupted"
  );
}
