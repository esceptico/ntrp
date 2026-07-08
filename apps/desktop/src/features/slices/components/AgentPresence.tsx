import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { resultSnippet, formatRelative } from "@/lib/agentRun";
import { ICON } from "@/lib/icons";

export interface AgentInfo {
  task_id?: string;
  thread_id?: string | null;
  last_result?: string | null;
  last_run_at?: string | null;
  running_since?: string | null;
  next_run_at?: string | null;
}

/** Live elapsed clock while an agent runs (mm:ss), ticking each second. */
function useElapsed(since: string | null | undefined): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!since) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [since]);
  if (!since) return "";
  const s = Math.max(0, Math.floor((now - new Date(since).getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The slice's standing agent as ONE quiet line, not a block: a state dot,
 *  "Agent · swept 2h ago", the last run's summary inline (when there is a
 *  real one), and Run now. The line is the door to the agent's channel.
 *  Deliberately understated — the ask below is the focal element; this is
 *  just the pulse that says "something is watching this, and it's fresh." */
export function AgentPresence({
  agent,
  onRunNow,
  onOpenChannel,
}: {
  agent: AgentInfo;
  onRunNow: () => void;
  onOpenChannel: () => void;
}) {
  const running = agent.running_since != null;
  const elapsed = useElapsed(agent.running_since);
  const rawSummary = resultSnippet(agent.last_result);
  // Guard the run-id-slug bug: channel automations record their run_id (a
  // coolname like "amazing-angelfish") as last_result. A real report has
  // spaces/capitals; a bare kebab slug is noise, so drop it.
  const summary = rawSummary && !/^[a-z]+(-[a-z]+)+$/.test(rawSummary) ? rawSummary : null;

  const status = running
    ? `Working… ${elapsed}`
    : agent.last_run_at
      ? `Agent · swept ${formatRelative(agent.last_run_at)}`
      : "Agent · hasn't run yet";

  return (
    <div className="flex min-w-0 items-center gap-2">
      <button
        type="button"
        onClick={onOpenChannel}
        title="Open the agent's channel — every run's full transcript"
        className="app-row group/agent -mx-1.5 flex min-w-0 flex-1 items-center gap-2 rounded-md px-1.5 py-1 text-left focus-visible:shadow-[0_0_0_2px_var(--color-accent-soft)] focus-visible:outline-none"
      >
        <span
          aria-hidden
          className={`size-1.5 shrink-0 rounded-full ${running ? "animate-pulse bg-accent" : "bg-muted"}`}
        />
        <span className="shrink-0 text-xs font-medium text-muted group-hover/agent:text-ink-soft">{status}</span>
        {summary && <span className="min-w-0 truncate text-xs text-faint">— {summary}</span>}
      </button>
      {!running && agent.task_id && (
        <button
          type="button"
          onClick={onRunNow}
          title="Run the agent now"
          className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-muted transition-colors hover:bg-surface-soft hover:text-ink"
        >
          <Play size={ICON.XS} strokeWidth={2} />
          Run now
        </button>
      )}
    </div>
  );
}
