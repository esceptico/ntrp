export function formatTimeAgo(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks === 1) return "1 week ago";
  if (diffWeeks < 4) return `${diffWeeks} weeks ago`;
  return date.toLocaleDateString();
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "\u2014";

  const date = new Date(iso);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);

  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  if (Math.abs(diffHours) < 24) return `today ${time}`;
  if (diffHours > 0 && diffHours < 48) return `tomorrow ${time}`;
  if (diffHours < 0 && diffHours > -48) return `yesterday ${time}`;

  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

export function shortTime(iso: string): string {
  return formatTimeAgo(iso).replace(" ago", "");
}

export function formatCountdown(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now();
  if (diff < 0) return "now";
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export function triggerLabel(trigger: { type: string; every?: string; at?: string; start?: string; end?: string; days?: string; event_type?: string; lead_minutes?: number }, compact?: boolean): string {
  if (trigger.type === "time") {
    let base = trigger.every ? `every ${trigger.every}` : trigger.at ?? "";
    if (trigger.start && trigger.end) base += ` (${trigger.start}\u2013${trigger.end})`;
    return !compact && trigger.days ? `${base}  ${trigger.days}` : base;
  }
  return trigger.event_type === "event_approaching" && trigger.lead_minutes
    ? `on:${trigger.event_type} (${trigger.lead_minutes}m)`
    : `on:${trigger.event_type}`;
}
