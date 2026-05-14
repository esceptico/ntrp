import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelRightClose, PanelRightOpen, X } from "lucide-react";
import clsx from "clsx";
import { cancelBackgroundTaskApi, listBackgroundTasksApi } from "../api";
import { isInternalAutomation, isIterationLoop } from "../lib/automationFilters";
import { EASE_EMPHASIZED, MOTION, originFromEvent } from "../lib/motion";
import { ICON } from "../lib/icons";
import { useStore, type BackgroundAgent } from "../store";

// Compact relative-time formatter. Codex's Cloud Tasks TUI uses
// "2m ago" style strings — same idea here, sans the suffix because
// space is tight in a 228px sidebar column.
function formatElapsed(since: number | string): string {
  const started = typeof since === "number" ? since : new Date(since).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h`;
}

// Status palette — only the dot carries color, not the row title.
// Cribbed from Codex's Cloud Tasks (running/completed/failed/cancelled
// map to the same conceptual buckets as their PENDING/READY/ERROR/...).
function statusDotClass(status: BackgroundAgent["status"] | "running"): string {
  switch (status) {
    case "completed":
      return "bg-ok";
    case "failed":
      return "bg-bad";
    case "cancelled":
      return "bg-faint";
    default:
      return "bg-accent";
  }
}

function StatusDot({
  status,
  pulse = false,
}: {
  status: BackgroundAgent["status"] | "running";
  pulse?: boolean;
}) {
  return (
    <span className="relative inline-flex w-1.5 h-1.5 shrink-0" aria-hidden>
      {pulse && status === "running" && (
        <span
          className={clsx(
            "absolute inset-0 rounded-[1px] opacity-60 animate-ping",
            statusDotClass(status),
          )}
        />
      )}
      <span
        className={clsx(
          "relative inline-block w-1.5 h-1.5 rounded-[1px]",
          statusDotClass(status),
        )}
      />
    </span>
  );
}

function useBackgroundTasksPoll(sessionId: string | null): void {
  const config = useStore((s) => s.config);
  const setBackgroundAgentsForSession = useStore((s) => s.setBackgroundAgentsForSession);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const tasks = await listBackgroundTasksApi(config, sessionId);
        if (!cancelled) {
          setBackgroundAgentsForSession(
            sessionId,
            tasks.map((task) => ({ taskId: task.task_id, command: task.command })),
          );
        }
      } catch {
        /* non-critical surface */
      }
    };
    void tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void tick();
    }, 5000);
    const onVis = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [config, sessionId, setBackgroundAgentsForSession]);
}

// Row anatomy (one row = up to two lines):
//   ● Task title              2m
//     subtle command / detail
//
// All weight is carried by the dot color + title text. Time and
// subtitle are dim. No icons in the row itself — Codex's pattern of
// "bracketed status tag as leading token" maps cleanly to a colored
// dot for a graphical UI. Cancel ✕ only on hover for running rows.
function Row({
  title,
  subtitle,
  status,
  elapsed,
  onCancel,
  cancelling,
}: {
  title: string;
  subtitle?: string;
  status: BackgroundAgent["status"] | "running";
  elapsed: string;
  onCancel?: () => void;
  cancelling?: boolean;
}) {
  const isRunning = status === "running";
  return (
    <div className="group/row py-1">
      <div className="flex items-center gap-2 min-w-0">
        <StatusDot status={status} pulse={isRunning} />
        <span className="flex-1 truncate text-sm text-ink-soft tracking-[-0.005em] min-w-0">
          {title}
        </span>
        <span className="text-xs text-faint tabular-nums shrink-0">{elapsed}</span>
        {onCancel && isRunning && (
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelling}
            title="Cancel"
            aria-label="Cancel"
            className="grid place-items-center w-4 h-4 rounded text-faint opacity-0 group-hover/row:opacity-100 hover:text-bad transition-opacity disabled:opacity-40"
          >
            <X size={10} strokeWidth={2.2} />
          </button>
        )}
      </div>
      {subtitle && (
        <div className="pl-[14px] truncate text-xs text-faint min-w-0">{subtitle}</div>
      )}
    </div>
  );
}

function BackgroundAgentRow({ agent }: { agent: BackgroundAgent }) {
  const config = useStore((s) => s.config);
  const upsertBackgroundAgent = useStore((s) => s.upsertBackgroundAgent);
  const [cancelling, setCancelling] = useState(false);

  const cancel = async () => {
    if (agent.status !== "running" || cancelling) return;
    setCancelling(true);
    try {
      await cancelBackgroundTaskApi(config, agent.sessionId, agent.taskId);
      upsertBackgroundAgent({ ...agent, status: "cancelled", updatedAt: Date.now() });
    } catch {
      setCancelling(false);
    }
  };

  // Prefer the command as the human-readable title; fall back to the
  // taskId. Many agents are spawned with a short command like "ml-intern"
  // which reads better than a UUID. Detail line shows the taskId trimmed
  // so users can still see it without it dominating.
  const title = agent.command || agent.taskId;
  const subtitle =
    agent.detail ?? (agent.command ? agent.taskId.slice(0, 12) : undefined);

  return (
    <Row
      title={title}
      subtitle={subtitle}
      status={agent.status}
      elapsed={formatElapsed(agent.createdAt)}
      onCancel={cancel}
      cancelling={cancelling}
    />
  );
}

function AutomationRow({
  name,
  runningSince,
  status,
}: {
  name: string;
  runningSince: string;
  status: string | undefined;
}) {
  return (
    <Row
      title={name}
      subtitle={status}
      status="running"
      elapsed={formatElapsed(runningSince)}
    />
  );
}

function SectionHeader({ label, count }: { label: string; count?: number }) {
  return (
    <div className="flex items-baseline justify-between px-0.5 pt-0.5 pb-1">
      <span className="text-2xs font-medium uppercase tracking-[0.08em] text-faint">
        {label}
      </span>
      {count != null && count > 0 && (
        <span className="text-2xs text-faint tabular-nums">{count}</span>
      )}
    </div>
  );
}

export function AgentRightSidebar() {
  const currentSessionId = useStore((s) => s.currentSessionId);
  const automations = useStore((s) => s.automations);
  const automationStatuses = useStore((s) => s.automationStatuses);
  const backgroundAgents = useStore((s) => s.backgroundAgents);
  const openAutomations = useStore((s) => s.openAutomations);
  const [collapsed, setCollapsed] = useState(true);

  useBackgroundTasksPoll(currentSessionId);

  const agents = useMemo(
    () =>
      Object.values(backgroundAgents)
        .filter((agent) => !currentSessionId || agent.sessionId === currentSessionId)
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, 8),
    [backgroundAgents, currentSessionId],
  );

  const runningAutomations = useMemo(
    () =>
      (automations ?? []).filter(
        (a) =>
          a.running_since != null &&
          !isInternalAutomation(a) &&
          !isIterationLoop(a),
      ),
    [automations],
  );

  const hasAgents = agents.length > 0;
  const hasAutomations = runningAutomations.length > 0;
  const both = hasAgents && hasAutomations;
  const visible = hasAgents || hasAutomations;

  const totalCount = agents.length + runningAutomations.length;

  // Reserve space on the right edge for the expanded panel so the chat
  // doesn't extend behind it. Mirror of the left sidebar's column.
  // - Hidden (no rows): 0 → chat fills to the right edge
  // - Collapsed (small pill): 0 → pill floats over chat corner, fine
  // - Expanded: var(--sidebar-width) → chat shrinks to leave room
  // Written to `--right-sidebar-w` on :root and consumed by `Chat.tsx`
  // via `right-[var(--right-sidebar-w,0px)]`.
  useLayoutEffect(() => {
    const root = document.documentElement;
    if (!collapsed) {
      root.style.setProperty(
        "--right-sidebar-w",
        "var(--sidebar-width, 244px)",
      );
    } else {
      root.style.setProperty("--right-sidebar-w", "0px");
    }
    return () => {
      root.style.removeProperty("--right-sidebar-w");
    };
  }, [collapsed]);

  return (
    <AnimatePresence initial={false}>
      {collapsed ? (
          <motion.button
            key="agent-right-sidebar-collapsed"
            type="button"
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 8 }}
            transition={{ duration: MOTION.route, ease: EASE_EMPHASIZED }}
            onClick={() => setCollapsed(false)}
            title="Show active"
            aria-label={`Show active (${totalCount})`}
            // Slim horizontal pill: dot + count + chevron. Reads as
            // "N active" at a glance without a detached badge — accent
            // splash lives only on the dot, everything else is muted.
            className="absolute top-[13px] right-[19px] z-30 inline-flex items-center gap-1.5 h-7 px-1.5 rounded-md text-muted hover:text-ink hover:bg-surface-soft transition-colors"
          >
            {totalCount > 0 && <StatusDot status="running" pulse />}
            {totalCount > 0 && (
              <span className="text-xs tabular-nums text-ink-soft">{totalCount}</span>
            )}
            <PanelRightOpen size={ICON.MD} strokeWidth={1.7} />
          </motion.button>
        ) : (
          <motion.aside
            key="agent-right-sidebar"
            initial={{ opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 18 }}
            transition={{ duration: MOTION.route, ease: EASE_EMPHASIZED }}
            className="absolute top-2 right-2 z-30 flex max-h-[calc(100vh-var(--chat-bottom-h,96px)-24px)] w-[calc(var(--sidebar-width,244px)-16px)] flex-col overflow-hidden rounded-xl border border-line bg-bg-main shadow-sm will-change-transform"
          >
            {/* Header strip — also serves as the top drag region. Label
                and collapse button sit on the same row so the 38px slot
                isn't just empty space above another row. Matches the
                left sidebar's top height for chrome alignment. */}
            <div className="drag-spacer flex items-center justify-between gap-2 px-3 h-[38px] shrink-0">
              <span className="text-2xs font-medium uppercase tracking-[0.08em] text-faint">
                Active{totalCount > 0 ? ` · ${totalCount}` : ""}
              </span>
              <button
                type="button"
                onClick={() => setCollapsed(true)}
                title="Collapse"
                aria-label="Collapse"
                className="grid place-items-center w-[22px] h-[22px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
              >
                <PanelRightClose size={ICON.MD} strokeWidth={1.7} />
              </button>
            </div>
            <div className="flex min-h-0 flex-col">
              <div className="min-h-0 overflow-y-auto px-3 pb-3 pt-1">
                {hasAgents && (
                  <section>
                    {both && <SectionHeader label="Agents" count={agents.length} />}
                    <div>
                      {agents.map((agent) => (
                        <BackgroundAgentRow
                          key={`${agent.sessionId}:${agent.taskId}`}
                          agent={agent}
                        />
                      ))}
                    </div>
                  </section>
                )}

                {hasAutomations && (
                  <section className={both ? "mt-3" : undefined}>
                    {both ? (
                      <button
                        type="button"
                        onClick={(e) => openAutomations(originFromEvent(e.currentTarget))}
                        className="block w-full text-left hover:text-ink transition-colors"
                        title="Open automations"
                      >
                        <SectionHeader
                          label="Automations"
                          count={runningAutomations.length}
                        />
                      </button>
                    ) : null}
                    <div>
                      {runningAutomations.map((automation) => (
                        <AutomationRow
                          key={automation.task_id}
                          name={automation.name || automation.task_id}
                          runningSince={automation.running_since!}
                          status={automationStatuses[automation.task_id]}
                        />
                      ))}
                    </div>
                  </section>
                )}

                {!visible && (
                  <div className="grid place-items-center min-h-[120px] px-3 text-center">
                    <p className="text-xs text-faint leading-relaxed">
                      No active agents or automations.
                      <br />
                      Background tasks will appear here.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </motion.aside>
        )}
    </AnimatePresence>
  );
}
