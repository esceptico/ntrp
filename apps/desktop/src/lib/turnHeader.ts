export function formatTurnDuration(ms: number): string {
  if (ms < 1000) return "less than a second";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const remS = s % 60;
  if (m < 60) return remS === 0 ? `${m}m` : `${m}m ${remS}s`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return remM === 0 ? `${h}h` : `${h}h ${remM}m`;
}

export function turnHeaderLabel(
  durationMs: number | null | undefined,
  wasStopped: boolean,
): string {
  if (durationMs != null) {
    return `${wasStopped ? "Stopped after" : "Worked for"} ${formatTurnDuration(durationMs)}`;
  }
  return wasStopped ? "Stopped" : "Worked";
}
