export function formatLoopCountdown(nextRunAt: number, now = Date.now()): string {
  const remainingMs = Math.max(0, nextRunAt - now);
  // Show seconds up to 119s so a 1m loop reads as "60s … 1s" cleanly
  // instead of flipping to "1m" (or "2m" on a stale `now` paint) at the
  // 60s boundary. Above 2 minutes, switch to minute-granularity.
  if (remainingMs < 120_000) {
    const seconds = Math.ceil(remainingMs / 1_000);
    return `${seconds}s`;
  }
  const minutes = Math.ceil(remainingMs / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  if (hours < 24) return rem ? `${hours}h ${rem}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}
