import { type AppConfig, type ServerEvent } from "../api";
import { getState, setState, type QueuedMessage } from "./index";
import type { ConnectionPhase } from "./domains";
import {
  applyChatEventToTranscript,
  createInitialTranscriptProjectionState,
  resetTranscriptProjectionState,
  transientProjectionReplayFloor,
  type TranscriptProjectionEffect,
  type TranscriptProjectionState,
} from "./transcript-projection";

export { runCancelledEffect } from "./transcript-projection";

type ServerEventEffect =
  | { type: "replay_gap"; sessionId: string }
  | TranscriptProjectionEffect;
type HistoryReloader = (sessionId: string) => Promise<void>;
interface ServerEventCallbacks {
  resendQueuedMessage?: (text: string, images: QueuedMessage["images"]) => void | Promise<void>;
}

export interface ChatStreamState extends TranscriptProjectionState {
  replayGapReloadingSessions: Map<string, Promise<boolean>>;
  replayGapBlockedSessions: Set<string>;
  lastEventSeqBySession: Map<string, number>;
  replayMutationTimer: ReturnType<typeof setTimeout> | null;
  replayMutationActive: boolean;
  connectionPhase: ConnectionPhase;
  sessionId: string | null;
  projectionSessionId: string | null;
}

interface EventCursorInput {
  session_id?: string | null;
  seq?: number;
  type?: string;
}

export function createInitialChatStreamState(): ChatStreamState {
  return {
    ...createInitialTranscriptProjectionState(),
    replayGapReloadingSessions: new Map(),
    replayGapBlockedSessions: new Set(),
    lastEventSeqBySession: new Map(),
    replayMutationTimer: null,
    replayMutationActive: false,
    connectionPhase: "idle",
    sessionId: null,
    projectionSessionId: null,
  };
}

let chatStreamState = createInitialChatStreamState();

export function getChatStreamState(): ChatStreamState {
  return chatStreamState;
}

export function reduceStreamConnecting(
  state: ChatStreamState,
  sessionId: string,
): ChatStreamState {
  return {
    ...clearTransientStreamState(state),
    sessionId,
    projectionSessionId: sessionId,
    connectionPhase:
      state.connectionPhase === "connected"
        ? "reconnecting"
        : "connecting",
  };
}

export function reduceStreamConnected(
  state: ChatStreamState,
  sessionId: string,
): ChatStreamState {
  return {
    ...state,
    sessionId,
    projectionSessionId: sessionId,
    connectionPhase: "connected",
  };
}

export function reduceStreamDisconnected(
  state: ChatStreamState,
  sessionId: string | null = state.sessionId,
): ChatStreamState {
  return {
    ...clearTransientStreamState(state),
    sessionId,
    projectionSessionId: sessionId,
    connectionPhase: "disconnected",
  };
}

export function reduceReplayGap(
  state: ChatStreamState,
  sessionId: string,
): ChatStreamState {
  const replayGapBlockedSessions = new Set(state.replayGapBlockedSessions);
  replayGapBlockedSessions.add(sessionId);

  return {
    ...clearTransientStreamState(state),
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
    return { state: { ...state, lastEventSeqBySession }, accepted: true };
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
  return { state: { ...state, lastEventSeqBySession }, accepted: true };
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

function updateChatStreamState(next: ChatStreamState): ChatStreamState {
  chatStreamState = next;
  return chatStreamState;
}

export function markStreamConnecting(sessionId: string): void {
  updateChatStreamState(reduceStreamConnecting(chatStreamState, sessionId));
}

export function markStreamConnected(sessionId: string): void {
  updateChatStreamState(reduceStreamConnected(chatStreamState, sessionId));
}

export function markStreamDisconnected(sessionId: string | null = chatStreamState.sessionId): void {
  updateChatStreamState(reduceStreamDisconnected(chatStreamState, sessionId));
  clearReplayMutationDomMarker();
}

function acceptEventCursor(event: ServerEvent): boolean {
  const result = reduceEventCursor(chatStreamState, event);
  updateChatStreamState(result.state);
  return result.accepted;
}

export function lastEventSeqForSession(sessionId: string): number | undefined {
  return chatStreamState.lastEventSeqBySession.get(sessionId);
}

export function forgetEventSeqForSession(sessionId: string): void {
  const lastEventSeqBySession = new Map(chatStreamState.lastEventSeqBySession);
  lastEventSeqBySession.delete(sessionId);
  updateChatStreamState({ ...chatStreamState, lastEventSeqBySession });
}

export function clearReplayGapBlockForSession(sessionId: string): void {
  updateChatStreamState(clearReplayBlock(chatStreamState, sessionId));
}

export function reloadHistoryAfterReplayGap(
  sessionId: string,
  reload: HistoryReloader,
): Promise<void> | null {
  if (chatStreamState.replayGapReloadingSessions.has(sessionId)) return null;
  const task = reload(sessionId)
    .then(() => {
      clearReplayGapBlockForSession(sessionId);
      return true;
    })
    .catch((error) => {
      setState({ error: error instanceof Error ? error.message : String(error) });
      return false;
    })
    .finally(() => {
      const replayGapReloadingSessions = new Map(chatStreamState.replayGapReloadingSessions);
      replayGapReloadingSessions.delete(sessionId);
      updateChatStreamState({ ...chatStreamState, replayGapReloadingSessions });
    });

  const replayGapReloadingSessions = new Map(chatStreamState.replayGapReloadingSessions);
  replayGapReloadingSessions.set(sessionId, task);
  updateChatStreamState({ ...chatStreamState, replayGapReloadingSessions });
  return task.then(() => undefined);
}

export function handleIncomingServerEvent(
  event: ServerEvent,
  reload?: HistoryReloader,
  callbacks: ServerEventCallbacks = {},
): Promise<void> | null {
  const sessionId = event.session_id ?? getState().currentSessionId;
  const activeSessionId = getState().currentSessionId;
  if (event.session_id && activeSessionId !== event.session_id) return null;

  const pendingReload =
    event.type === "stream_reset" || !sessionId
      ? undefined
      : chatStreamState.replayGapReloadingSessions.get(sessionId);
  if (pendingReload) {
    return pendingReload.then(async (loaded) => {
      if (!loaded) return;
      if (getState().currentSessionId !== sessionId) return;
      await handleIncomingServerEvent(event, reload, callbacks);
    });
  }

  const effect = event.replay ? handleReplayServerEvent(event) : handleServerEvent(event);
  if (!effect) return null;
  if (effect.type === "replay_gap") {
    if (!reload) {
      setState({ error: "history reload callback is required after replay gap" });
      return null;
    }
    return reloadHistoryAfterReplayGap(effect.sessionId, reload);
  }
  if (effect.type === "resend_queued_messages") {
    for (const message of effect.messages) {
      void callbacks.resendQueuedMessage?.(message.text, message.images);
    }
  }
  return null;
}

export function handleServerEvent(event: ServerEvent): ServerEventEffect | undefined {
  if (!acceptEventCursor(event)) return;
  return applyServerEvent(event);
}

export function handleReplayServerEvent(event: ServerEvent): ServerEventEffect | undefined {
  if (!acceptEventCursor(event)) return;
  markReplayMutation();
  return applyServerEvent({ ...event, replay: true });
}

function markReplayMutation(): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.streamReplaying = "true";
  if (chatStreamState.replayMutationTimer !== null) {
    clearTimeout(chatStreamState.replayMutationTimer);
  }
  const replayMutationTimer = setTimeout(() => {
    updateChatStreamState({
      ...chatStreamState,
      replayMutationTimer: null,
      replayMutationActive: false,
    });
    clearReplayMutationDomMarker();
  }, 0);
  updateChatStreamState({
    ...chatStreamState,
    replayMutationTimer,
    replayMutationActive: true,
  });
}

function clearReplayMutationDomMarker(): void {
  if (typeof document !== "undefined") {
    delete document.documentElement.dataset.streamReplaying;
  }
}

function applyServerEvent(event: ServerEvent): ServerEventEffect | undefined {
  const s = getState();
  const ts = event.timestamp ?? Date.now();

  switch (event.type) {
    case "stream_reset": {
      if (event.reason !== "replay_gap") return;
      s.setActiveActivityId(null);
      const resetSessionId = event.session_id ?? s.currentSessionId;
      if (!resetSessionId) return;
      updateChatStreamState(reduceReplayGap(chatStreamState, resetSessionId));
      clearReplayMutationDomMarker();
      return { type: "replay_gap", sessionId: resetSessionId };
    }
    case "stream_keepalive":
      return;
    case "approval_needed":
      s.addPendingApproval({
        toolId: event.tool_id,
        toolName: event.name,
        path: event.path ?? undefined,
        diff: event.diff ?? undefined,
        preview: event.content_preview ?? undefined,
        status: "pending",
      });
      return;
    case "background_task":
      s.upsertBackgroundAgent({
        taskId: event.task_id,
        sessionId: event.session_id ?? s.currentSessionId ?? "",
        command: event.command,
        status:
          event.status === "completed" || event.status === "failed" || event.status === "cancelled"
            || event.status === "interrupted" || event.status === "cancel_requested"
            ? event.status
            : "running",
        detail: event.detail ?? undefined,
        resultRef: event.result_ref ?? undefined,
        updatedAt: ts,
      });
      return;
    case "compaction_started":
      s.setCompacting(true);
      return;
    case "compaction_finished":
      s.setCompacting(false);
      s.setLastCompaction({
        before: event.messages_before,
        after: event.messages_after,
        at: ts,
      });
      return;
    case "goal_updated":
      s.setGoal(event.session_id, event.goal);
      return;
    case "goal_cleared":
      s.setGoal(event.session_id, null);
      return;
    default: {
      const result = applyChatEventToTranscript(chatStreamState, event, {
        getProjectionState: () => chatStreamState,
        setProjectionState: (projection) => {
          updateChatStreamState({ ...chatStreamState, ...projection });
        },
      });
      updateChatStreamState({ ...chatStreamState, ...result.state });
      return result.effect;
    }
  }
}

export function eventStreamUrl(config: AppConfig, sessionId: string): string {
  const params = new URLSearchParams({ stream: "true" });
  const lastSeq = lastEventSeqForSession(sessionId);
  if (lastSeq !== undefined) params.set("after_seq", String(lastSeq));
  return `${config.serverUrl}/chat/events/${encodeURIComponent(sessionId)}?${params.toString()}`;
}

export function resetStreamStateForTest(): void {
  updateChatStreamState(reduceStreamDisconnected(chatStreamState));
  clearReplayMutationDomMarker();
}

export function resetEventSeqStateForTest(): void {
  updateChatStreamState({
    ...chatStreamState,
    lastEventSeqBySession: new Map(),
  });
}

export function resetReplayGapReloadStateForTest(): void {
  updateChatStreamState({
    ...chatStreamState,
    replayGapReloadingSessions: new Map(),
    replayGapBlockedSessions: new Set(),
  });
}
