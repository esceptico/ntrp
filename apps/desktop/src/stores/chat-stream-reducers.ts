import {
  createInitialTranscriptProjectionState,
  resetTranscriptProjectionState,
  transientProjectionReplayFloor,
} from "@/stores/transcript-projection";
import type {
  ChatStreamState,
  EventCursorInput,
  TransportDiagnostics,
} from "@/stores/chat-stream-types";

export function createInitialChatStreamState(): ChatStreamState {
  return {
    ...createInitialTranscriptProjectionState(),
    replayGapReloadingSessions: new Map(),
    replayGapBlockedSessions: new Set(),
    lastEventSeqBySession: new Map(),
    transportDiagnosticsBySession: new Map(),
    replayMutationTimer: null,
    replayMutationActive: false,
    connectionPhase: "idle",
    sessionId: null,
    projectionSessionId: null,
  };
}

export function reduceStreamConnecting(
  state: ChatStreamState,
  sessionId: string,
  afterSeq?: number,
): ChatStreamState {
  const connectionPhase =
    state.connectionPhase === "connected" || state.connectionPhase === "reconnecting"
      ? "reconnecting"
      : "connecting";
  return updateTransportDiagnostics(
    {
    ...clearTransientStreamState(state),
    sessionId,
    projectionSessionId: sessionId,
      connectionPhase,
    },
    sessionId,
    { connectionPhase, connectAfterSeq: afterSeq ?? null },
  );
}

export function reduceStreamConnected(
  state: ChatStreamState,
  sessionId: string,
): ChatStreamState {
  return updateTransportDiagnostics(
    {
      ...state,
      sessionId,
      projectionSessionId: sessionId,
      connectionPhase: "connected",
    },
    sessionId,
    { connectionPhase: "connected" },
  );
}

export function reduceStreamReconnecting(
  state: ChatStreamState,
  sessionId: string,
  reason?: string | null,
  error?: string | null,
): ChatStreamState {
  return updateTransportDiagnostics(
    {
      ...clearTransientStreamState(state),
      sessionId,
      projectionSessionId: sessionId,
      connectionPhase: "reconnecting",
    },
    sessionId,
    {
      connectionPhase: "reconnecting",
      ...(reason !== undefined ? { lastClosedReason: reason } : {}),
      ...(error !== undefined ? { lastError: error } : {}),
    },
  );
}

export function reduceStreamDisconnected(
  state: ChatStreamState,
  sessionId: string | null = state.sessionId,
  reason?: string | null,
  error?: string | null,
): ChatStreamState {
  const next: ChatStreamState = {
    ...clearTransientStreamState(state),
    sessionId,
    projectionSessionId: sessionId,
    connectionPhase: "disconnected",
  };
  if (!sessionId) return next;
  return updateTransportDiagnostics(next, sessionId, {
    connectionPhase: "disconnected",
    ...(reason !== undefined ? { lastClosedReason: reason } : {}),
    ...(error !== undefined ? { lastError: error } : {}),
  });
}

export function reduceReplayGap(
  state: ChatStreamState,
  sessionId: string,
): ChatStreamState {
  const resetSeq = state.lastEventSeqBySession.get(sessionId);
  const cleared = clearTransientStreamState(state);
  let lastEventSeqBySession = cleared.lastEventSeqBySession;
  const clearedSeq = lastEventSeqBySession.get(sessionId);
  if (resetSeq !== undefined && (clearedSeq === undefined || clearedSeq < resetSeq)) {
    lastEventSeqBySession = new Map(lastEventSeqBySession);
    lastEventSeqBySession.set(sessionId, resetSeq);
  }
  const replayGapBlockedSessions = new Set(state.replayGapBlockedSessions);
  replayGapBlockedSessions.add(sessionId);

  return {
    ...cleared,
    lastEventSeqBySession,
    sessionId,
    projectionSessionId: sessionId,
    replayGapBlockedSessions,
  };
}

export function reduceEventCursor(
  state: ChatStreamState,
  event: EventCursorInput,
): { state: ChatStreamState; accepted: boolean } {
  if (typeof event.seq !== "number" || !event.session_id) {
    return { state, accepted: true };
  }
  if (event.type === "stream_reset") {
    const lastEventSeqBySession = new Map(state.lastEventSeqBySession);
    lastEventSeqBySession.set(event.session_id, event.seq);
    return {
      state: recordTransportEventDiagnostics({ ...state, lastEventSeqBySession }, event),
      accepted: true,
    };
  }
  if (state.replayGapBlockedSessions.has(event.session_id)) {
    return { state, accepted: false };
  }

  const lastSeq = state.lastEventSeqBySession.get(event.session_id);
  if (lastSeq !== undefined && event.seq <= lastSeq) {
    return { state, accepted: false };
  }

  const lastEventSeqBySession = new Map(state.lastEventSeqBySession);
  lastEventSeqBySession.set(event.session_id, event.seq);
  return {
    state: recordTransportEventDiagnostics({ ...state, lastEventSeqBySession }, event),
    accepted: true,
  };
}

function updateTransportDiagnostics(
  state: ChatStreamState,
  sessionId: string,
  patch: Partial<TransportDiagnostics>,
): ChatStreamState {
  const transportDiagnosticsBySession = new Map(state.transportDiagnosticsBySession);
  const current = transportDiagnosticsBySession.get(sessionId);
  const diagnostics = {
    connectionPhase: state.connectionPhase,
    lastClosedReason: null,
    lastError: null,
    ...current,
    ...patch,
    updatedAt: Date.now(),
  };
  transportDiagnosticsBySession.set(sessionId, diagnostics);
  return { ...state, transportDiagnosticsBySession };
}

export function recordTransportEventDiagnostics(state: ChatStreamState, event: EventCursorInput): ChatStreamState {
  if (!event.session_id || typeof event.seq !== "number") return state;
  return updateTransportDiagnostics(state, event.session_id, {
    lastSeq: event.seq,
    ...(event.type === "stream_keepalive"
      ? { lastKeepaliveSeq: event.latest_seq ?? event.seq }
      : {}),
  });
}

export function clearReplayBlock(
  state: ChatStreamState,
  sessionId: string,
): ChatStreamState {
  if (!state.replayGapBlockedSessions.has(sessionId)) return state;
  const replayGapBlockedSessions = new Set(state.replayGapBlockedSessions);
  replayGapBlockedSessions.delete(sessionId);
  return { ...state, replayGapBlockedSessions };
}

function clearTransientStreamState(state: ChatStreamState): ChatStreamState {
  if (state.replayMutationTimer !== null) clearTimeout(state.replayMutationTimer);
  const lastEventSeqBySession = rewindCursorForTransientProjection(state);
  const projection = resetTranscriptProjectionState(state);
  return {
    ...state,
    ...projection,
    lastEventSeqBySession,
    replayMutationTimer: null,
    replayMutationActive: false,
  };
}

function rewindCursorForTransientProjection(state: ChatStreamState): Map<string, number> {
  if (!state.sessionId) return state.lastEventSeqBySession;

  const replayFromSeq = transientProjectionReplayFloor(state);
  if (replayFromSeq === null) return state.lastEventSeqBySession;

  const nextCursor = Math.max(0, replayFromSeq - 1);
  if (state.lastEventSeqBySession.get(state.sessionId) === nextCursor) {
    return state.lastEventSeqBySession;
  }
  const lastEventSeqBySession = new Map(state.lastEventSeqBySession);
  lastEventSeqBySession.set(state.sessionId, nextCursor);
  return lastEventSeqBySession;
}
