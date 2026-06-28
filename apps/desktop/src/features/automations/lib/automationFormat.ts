import {
  Bell,
  Briefcase,
  CalendarClock,
  Clock,
  FileSearch,
  FileText,
  GitPullRequest,
  Inbox,
  Mail,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { AutomationRun } from "@/api/types";
import { formatRelative } from "@/lib/agentRun";

const SUGGESTION_ICONS: Record<string, LucideIcon> = {
  Sparkles,
  Bell,
  Briefcase,
  CalendarClock,
  Clock,
  FileSearch,
  FileText,
  GitPullRequest,
  Inbox,
  Mail,
};

export function suggestionIcon(name: string | null): LucideIcon {
  return (name && SUGGESTION_ICONS[name]) || Sparkles;
}

function _runDuration(start: string, end: string): string {
  const ms = Date.parse(end) - Date.parse(start);
  if (!Number.isFinite(ms) || ms < 0) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m}m` : `${Math.round(m / 60)}h`;
}

/** Recent runs as a markdown digest, shown in the existing markdown viewer. */
export function formatRunsMarkdown(runs: AutomationRun[]): string {
  if (runs.length === 0) return "_No runs recorded yet._";
  return runs
    .map((r) => {
      const mark = r.status === "completed" ? "✓" : r.status === "failed" ? "✗" : "•";
      const dur = r.ended_at ? _runDuration(r.started_at, r.ended_at) : "running";
      const head = `**${mark} ${formatRelative(r.started_at)}** · ${r.status}${dur ? ` · ${dur}` : ""}`;
      const detail = (r.error ?? r.result ?? "").trim();
      const quoted = detail
        ? "\n" + detail.split("\n").slice(0, 6).map((l) => `> ${l}`).join("\n")
        : "";
      return head + quoted;
    })
    .join("\n\n");
}
