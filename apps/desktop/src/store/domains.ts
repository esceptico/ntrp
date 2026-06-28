import {
  createAutomationStreamDomainState,
  type AutomationStreamDomainState,
} from "@/store/automation-domain";
import {
  createBackgroundAgentsDomainState,
  type BackgroundAgentsDomainState,
} from "@/store/background-agent-domain";

export type HistoryPhase =
  | "idle"
  | "cached-preview"
  | "loading-history"
  | "live-tail"
  | "replay-gap";

export type ConnectionPhase =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "failed";

export type RunPhase =
  | "idle"
  | "queued"
  | "running"
  | "waiting-approval"
  | "completed"
  | "failed"
  | "cancelled";

export interface SessionViewDomainState {
  sessionId: string | null;
  historyPhase: HistoryPhase;
  serverHistoryLoadedFor: string | null;
  canonicalHistoryRequired: boolean;
}

export interface ChatStreamDomainState {
  sessionId: string | null;
  connectionPhase: ConnectionPhase;
  sseRenderingEnabled: boolean;
  replayedTailBlocked: boolean;
}

export interface RunLifecycleDomainState {
  phase: RunPhase;
  activeRunId: string | null;
  activeSessionId: string | null;
}

export interface UiShellDomainState {
  connectionPhase: ConnectionPhase;
  activeSessionId: string | null;
}

export interface DomainState {
  sessionView: SessionViewDomainState;
  chatStream: ChatStreamDomainState;
  runLifecycle: RunLifecycleDomainState;
  automationStream: AutomationStreamDomainState;
  backgroundAgents: BackgroundAgentsDomainState;
  uiShell: UiShellDomainState;
}

export type DomainAction =
  | { type: "session.cachedPreview"; sessionId: string }
  | { type: "session.loadingHistory"; sessionId: string }
  | { type: "session.serverHistoryLoaded"; sessionId: string }
  | { type: "chatStream.liveTailRequested"; sessionId: string; replayed?: boolean }
  | { type: "chatStream.replayGapDetected"; sessionId: string }
  | { type: "run.queued"; runId: string; sessionId: string }
  | { type: "run.started"; runId: string; sessionId: string }
  | { type: "run.waitingApproval"; runId: string; sessionId: string }
  | { type: "run.terminal"; runId: string; phase: Extract<RunPhase, "completed" | "failed" | "cancelled"> };

export function createDomainState(): DomainState {
  return {
    sessionView: {
      sessionId: null,
      historyPhase: "idle",
      serverHistoryLoadedFor: null,
      canonicalHistoryRequired: false,
    },
    chatStream: {
      sessionId: null,
      connectionPhase: "idle",
      sseRenderingEnabled: false,
      replayedTailBlocked: false,
    },
    runLifecycle: {
      phase: "idle",
      activeRunId: null,
      activeSessionId: null,
    },
    automationStream: createAutomationStreamDomainState(),
    backgroundAgents: createBackgroundAgentsDomainState(),
    uiShell: {
      connectionPhase: "idle",
      activeSessionId: null,
    },
  };
}

export function reduceDomainState(state: DomainState, action: DomainAction): DomainState {
  switch (action.type) {
    case "session.cachedPreview":
      return {
        ...state,
        sessionView: {
          ...state.sessionView,
          sessionId: action.sessionId,
          historyPhase: "cached-preview",
          canonicalHistoryRequired: true,
        },
        chatStream: {
          ...state.chatStream,
          sessionId: action.sessionId,
          sseRenderingEnabled: false,
          replayedTailBlocked: false,
        },
        uiShell: {
          ...state.uiShell,
          activeSessionId: action.sessionId,
        },
      };

    case "session.loadingHistory":
      return {
        ...state,
        sessionView: {
          ...state.sessionView,
          sessionId: action.sessionId,
          historyPhase: "loading-history",
          canonicalHistoryRequired: true,
        },
        chatStream: {
          ...state.chatStream,
          sessionId: action.sessionId,
          sseRenderingEnabled: false,
          replayedTailBlocked: false,
        },
        uiShell: {
          ...state.uiShell,
          activeSessionId: action.sessionId,
        },
      };

    case "session.serverHistoryLoaded":
      return {
        ...state,
        sessionView: {
          ...state.sessionView,
          sessionId: action.sessionId,
          historyPhase: "idle",
          serverHistoryLoadedFor: action.sessionId,
          canonicalHistoryRequired: false,
        },
        chatStream: {
          ...state.chatStream,
          sessionId: action.sessionId,
          replayedTailBlocked: false,
        },
        uiShell: {
          ...state.uiShell,
          activeSessionId: action.sessionId,
        },
      };

    case "chatStream.liveTailRequested": {
      const historyLoaded = state.sessionView.serverHistoryLoadedFor === action.sessionId;
      const blocked =
        !historyLoaded ||
        state.sessionView.historyPhase === "cached-preview" ||
        state.sessionView.historyPhase === "loading-history" ||
        state.sessionView.historyPhase === "replay-gap";

      return {
        ...state,
        sessionView: {
          ...state.sessionView,
          historyPhase: blocked ? state.sessionView.historyPhase : "live-tail",
        },
        chatStream: {
          ...state.chatStream,
          sessionId: action.sessionId,
          sseRenderingEnabled: !blocked,
          replayedTailBlocked: Boolean(action.replayed && blocked),
        },
      };
    }

    case "chatStream.replayGapDetected":
      return {
        ...state,
        sessionView: {
          ...state.sessionView,
          sessionId: action.sessionId,
          historyPhase: "replay-gap",
          canonicalHistoryRequired: true,
        },
        chatStream: {
          ...state.chatStream,
          sessionId: action.sessionId,
          sseRenderingEnabled: false,
          replayedTailBlocked: true,
        },
      };

    case "run.queued":
      return setActiveRun(state, "queued", action.runId, action.sessionId);

    case "run.started":
      return setActiveRun(state, "running", action.runId, action.sessionId);

    case "run.waitingApproval":
      return setActiveRun(state, "waiting-approval", action.runId, action.sessionId);

    case "run.terminal":
      if (state.runLifecycle.activeRunId !== action.runId) {
        return state;
      }

      return {
        ...state,
        runLifecycle: {
          phase: action.phase,
          activeRunId: null,
          activeSessionId: null,
        },
      };
  }
}

function setActiveRun(
  state: DomainState,
  phase: Extract<RunPhase, "queued" | "running" | "waiting-approval">,
  runId: string,
  sessionId: string,
): DomainState {
  return {
    ...state,
    runLifecycle: {
      phase,
      activeRunId: runId,
      activeSessionId: sessionId,
    },
  };
}
