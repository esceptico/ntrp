import type { ConnectionPhase } from "../store/domains";

export interface TransportDiagnosticsSnapshot {
  connectionPhase: ConnectionPhase;
  lastSeq?: number;
  lastKeepaliveSeq?: number;
  connectAfterSeq?: number | null;
  lastClosedReason?: string | null;
  lastError?: string | null;
  updatedAt: number;
}

export interface FormattedTransportDiagnostics {
  label: string;
  title: string;
}

function valueOrDash(value: number | string | null | undefined): string {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

export function formatTransportDiagnostics(
  diagnostics: TransportDiagnosticsSnapshot,
): FormattedTransportDiagnostics {
  return {
    label: `${diagnostics.connectionPhase} · seq ${valueOrDash(diagnostics.lastSeq)} · keepalive ${valueOrDash(diagnostics.lastKeepaliveSeq)}`,
    title: [
      `phase: ${diagnostics.connectionPhase}`,
      `last seq: ${valueOrDash(diagnostics.lastSeq)}`,
      `last keepalive: ${valueOrDash(diagnostics.lastKeepaliveSeq)}`,
      `after_seq: ${valueOrDash(diagnostics.connectAfterSeq)}`,
      `last close: ${valueOrDash(diagnostics.lastClosedReason)}`,
      `last error: ${valueOrDash(diagnostics.lastError)}`,
    ].join("\n"),
  };
}
