import type { ConnectionPhase } from "@/stores/domains";
import type { TranscriptProjectionState } from "@/stores/transcript-projection";

export const REPLAY_MUTATION_HOLD_MS = 160;

export interface ChatStreamState extends TranscriptProjectionState {
  replayGapReloadingSessions: Map<string, Promise<boolean>>;
  replayGapBlockedSessions: Set<string>;
  lastEventSeqBySession: Map<string, number>;
  transportDiagnosticsBySession: Map<string, TransportDiagnostics>;
  replayMutationTimer: ReturnType<typeof setTimeout> | null;
  replayMutationActive: boolean;
  connectionPhase: ConnectionPhase;
  sessionId: string | null;
  projectionSessionId: string | null;
}

export interface EventCursorInput {
  session_id?: string | null;
  seq?: number;
  type?: string;
  latest_seq?: number;
}

export interface TransportDiagnostics {
  connectionPhase: ConnectionPhase;
  lastSeq?: number;
  lastKeepaliveSeq?: number;
  connectAfterSeq?: number | null;
  lastClosedReason?: string | null;
  lastError?: string | null;
  updatedAt: number;
}
