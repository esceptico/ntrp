import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Play, Radio } from "lucide-react";
import { resultSnippet, formatRelative } from "@/lib/agentRun";
import { ICON } from "@/lib/icons";
import { RISE_IN, RISE_SETTLED, MOTION, EASE_OUT } from "@/lib/tokens/motion";

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

function nextRunLabel(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "next sweep due";
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `next sweep in ${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `next sweep in ${hrs}h`;
  return `next sweep in ${Math.round(hrs / 24)}d`;
}

/** The standing agent as a first-class presence in the room, not a faint
 *  footnote. Three honest states:
 *   • running  → live pulse + mm:ss elapsed, a real "it's working" signal
 *                (no fake progress bar — the run's length is unknown).
 *   • ran      → the report's first line, when it swept, next sweep, and the
 *                Run now / Open channel doors. When a run just COMPLETED
 *                (running true→false), the fresh summary reveals out of blur
 *                and the accent edge charges then releases — the
 *                FocusProgress "settle", fired only at the real moment work
 *                lands (rare, so it earns the motion).
 *   • idle     → hasn't run yet, offer Run now.
 *  The whole block is a door to the agent's channel transcript. */
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
  const summary = resultSnippet(agent.last_result);
  const edgeRef = useRef<HTMLDivElement | null>(null);
  const wasRunning = useRef(running);
  const [justSettled, setJustSettled] = useState(false);

  // Fire the settle (edge charge → release) exactly when a run finishes.
  useEffect(() => {
    if (wasRunning.current && !running) {
      setJustSettled(true);
      const edge = edgeRef.current;
      if (edge && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
        edge.style.transition = "none";
        edge.style.opacity = "1";
        requestAnimationFrame(() => {
          edge.style.transition = "opacity 600ms cubic-bezier(0.22, 1, 0.36, 1)";
          edge.style.opacity = "0";
        });
      }
      const t = setTimeout(() => setJustSettled(false), 700);
      return () => clearTimeout(t);
    }
    wasRunning.current = running;
  }, [running]);

  const next = nextRunLabel(agent.next_run_at);

  return (
    <button
      type="button"
      onClick={onOpenChannel}
      title="Open the agent's channel — every run's full transcript"
      className="group/agent relative w-full overflow-hidden rounded-[12px] bg-surface-soft px-4 py-3 text-left"
    >
      {/* Settle edge — a hairline accent border that releases when a run
          lands. Opacity is driven imperatively; starts hidden. */}
      <div
        ref={edgeRef}
        aria-hidden
        className="pointer-events-none absolute rounded-[13px] border-[1.5px] border-accent opacity-0"
        style={{ inset: -1 }}
      />
      <div className="flex min-w-0 items-center gap-2">
        <span
          aria-hidden
          className={`size-1.5 shrink-0 rounded-full ${running ? "animate-pulse bg-ink" : "bg-muted"}`}
        />
        <span className="text-2xs font-semibold uppercase tracking-wide text-faint">Agent</span>
        {running ? (
          <span className="ml-auto font-mono text-2xs tabular-nums text-muted">{elapsed}</span>
        ) : (
          agent.last_run_at && (
            <span className="ml-auto text-2xs text-whisper tabular-nums">
              swept {formatRelative(agent.last_run_at)}
            </span>
          )
        )}
      </div>

      <div className="mt-1.5 min-w-0">
        <AnimatePresence mode="wait" initial={false}>
          {running ? (
            <motion.p
              key="running"
              initial={RISE_IN}
              animate={RISE_SETTLED}
              exit={{ opacity: 0, filter: "blur(3px)", transition: { duration: MOTION.fast, ease: EASE_OUT } }}
              className="m-0 text-sm text-ink-soft"
            >
              Working now…
            </motion.p>
          ) : summary ? (
            <motion.p
              key={`summary:${agent.last_run_at}`}
              // Fresh report writes itself out of blur only when it just
              // landed; an existing summary on mount is already resolved.
              initial={justSettled ? RISE_IN : false}
              animate={RISE_SETTLED}
              className="m-0 text-sm leading-snug text-ink-soft line-clamp-2 [overflow-wrap:anywhere]"
            >
              {summary}
            </motion.p>
          ) : (
            <p className="m-0 text-sm text-faint">Hasn't run yet.</p>
          )}
        </AnimatePresence>
      </div>

      <div className="mt-2 flex items-center gap-3 text-2xs text-whisper">
        <span className="inline-flex items-center gap-1">
          <Radio size={ICON.XS} strokeWidth={2} />
          open channel
        </span>
        {!running && next && <span className="text-faint">{next}</span>}
        {!running && agent.task_id && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              onRunNow();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                e.stopPropagation();
                onRunNow();
              }
            }}
            className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-muted hover:bg-surface-2 hover:text-ink"
          >
            <Play size={ICON.XS} strokeWidth={2} />
            Run now
          </span>
        )}
      </div>
    </button>
  );
}
