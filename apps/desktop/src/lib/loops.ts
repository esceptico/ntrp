export function formatLoopCountdown(nextRunAt: number, now = Date.now()): string {
  const remainingMs = Math.max(0, nextRunAt - now);
  if (remainingMs < 60_000) return "<1m";
  const minutes = Math.ceil(remainingMs / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  if (hours < 24) return rem ? `${hours}h ${rem}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}
