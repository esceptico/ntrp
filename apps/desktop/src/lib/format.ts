/** Compact relative-past label ("12m", "3h", "2d", "5mo"). */
export function formatRelativePast(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}

/** Locale-formatted absolute timestamp: "May 4, 2026, 11:03 PM". */
export function formatAbs(value: string): string {
  const d = new Date(value);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Best-effort one-line preview of a tool-call's JSON args. Returns the
 *  first key:value pair (truncated) or a flattened JSON snippet, matching
 *  what we show in the activity trace before TOOL_CALL_END resolves. */
export function previewArgs(argsJson: string): string {
  try {
    const parsed = JSON.parse(argsJson || "{}");
    if (parsed && typeof parsed === "object") {
      const entries = Object.entries(parsed as Record<string, unknown>);
      if (entries.length === 0) return "";
      const [k, v] = entries[0];
      const valueStr = typeof v === "string" ? v : JSON.stringify(v);
      const head = `${k}: ${valueStr}`;
      return head.length > 120 ? `${head.slice(0, 117)}…` : head;
    }
    const flat = JSON.stringify(parsed);
    return flat.length > 120 ? `${flat.slice(0, 117)}…` : flat;
  } catch {
    return argsJson.length > 120 ? `${argsJson.slice(0, 117)}…` : argsJson;
  }
}
