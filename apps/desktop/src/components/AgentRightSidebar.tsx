import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  CheckCircle2,
  Circle,
  CircleDot,
  ListChecks,
  PanelRightClose,
  PanelRightOpen,
  X,
} from "lucide-react";
import clsx from "clsx";
import { cancelBackgroundTaskApi, listBackgroundTasksApi, type TodoStatus } from "../api";
import { isInternalAutomation, isIterationLoop } from "../lib/automationFilters";
import { EASE_EMPHASIZED, MOTION, originFromEvent, SPRING_ROW_ENTRY } from "../lib/tokens/motion";
import { ICON } from "../lib/icons";
import { useStore, type BackgroundAgent, type TodoListState, type UiMessage } from "../store";
import { ScrollBlurTop } from "./ScrollBlur";

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
  // Both bg-* and text-* so the breathing-glow box-shadow (which uses
  // `currentColor`) tints to the same hue as the dot fill.
  switch (status) {
    case "completed":
      return "bg-ok text-ok";
    case "failed":
      return "bg-bad text-bad";
    case "cancelled":
      return "bg-faint text-faint";
    default:
      return "bg-accent text-accent";
  }
}

export function isActiveBackgroundAgent(agent: BackgroundAgent): boolean {
  return agent.status === "running" || agent.status === "cancel_requested";
}

export function StatusDot({
  status,
  pulse = false,
}: {
  status: BackgroundAgent["status"] | "running";
  pulse?: boolean;
}) {
  const breathing = pulse && status === "running";
  return (
    <span
      className={clsx(
        "inline-block w-1.5 h-1.5 rounded-full shrink-0",
        statusDotClass(status),
        breathing && "status-dot-breathe",
      )}
      aria-hidden
    />
  );
}

export function latestTodoListFromMessages(
  order: string[],
  messages: Map<string, UiMessage>,
): TodoListState | null {
  for (let i = order.length - 1; i >= 0; i -= 1) {
    const message = messages.get(order[i]);
    if (message?.role === "todo" && message.todo?.items.length) return message.todo;
  }
  return null;
}

export const RIGHT_PANEL_WIDTH = 320;
export const RIGHT_PANEL_BODY_WIDTH = 304;

function useBackgroundTasksPoll(sessionId: string | null): void {
  const config = useStore((s) => s.config);
  const setBackgroundAgentsForSession = useStore((s) => s.setBackgroundAgentsForSession);
  const backgroundAgentsRefreshStarted = useStore((s) => s.backgroundAgentsRefreshStarted);
  const backgroundAgentsRefreshFailed = useStore((s) => s.backgroundAgentsRefreshFailed);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const tick = async () => {
      backgroundAgentsRefreshStarted();
      try {
        const tasks = await listBackgroundTasksApi(config, sessionId);
        if (!cancelled) {
          setBackgroundAgentsForSession(
            sessionId,
            tasks.map((task) => {
              const status =
                task.status === "completed" ||
                task.status === "failed" ||
                task.status === "cancelled" ||
                task.status === "interrupted" ||
                task.status === "cancel_requested"
                  ? task.status
                  : "running";
              return {
                taskId: task.task_id,
                command: task.command,
                status,
                detail: task.detail ?? undefined,
                resultRef: task.result_ref ?? undefined,
              };
            }),
          );
        }
      } catch (error) {
        if (!cancelled) {
          backgroundAgentsRefreshFailed(
            error instanceof Error ? error.message : String(error),
          );
        }
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
  }, [
    backgroundAgentsRefreshFailed,
    backgroundAgentsRefreshStarted,
    config,
    sessionId,
    setBackgroundAgentsForSession,
  ]);
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
      upsertBackgroundAgent({ ...agent, status: "cancel_requested", updatedAt: Date.now() });
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

function todoStatusIcon(status: TodoStatus) {
  if (status === "completed") {
    return <CheckCircle2 size={ICON.XS} strokeWidth={2.2} className="mt-[2px] shrink-0 text-ok" />;
  }
  if (status === "in_progress") {
    return <CircleDot size={ICON.XS} strokeWidth={2.2} className="mt-[2px] shrink-0 text-info" />;
  }
  return <Circle size={ICON.XS} strokeWidth={2} className="mt-[2px] shrink-0 text-faint" />;
}

function TodoSidebarSection({ todo }: { todo: TodoListState }) {
  const completed = todo.items.filter((item) => item.status === "completed").length;

  return (
    <section>
      <SectionHeader label="Tasks" count={todo.items.length} />
      <div className="rounded-[8px] border border-line-soft bg-surface-soft/45 px-2.5 py-2">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="inline-flex min-w-0 items-center gap-1.5">
            <ListChecks size={ICON.XS} strokeWidth={2} className="shrink-0 text-muted" />
            <span className="truncate text-xs font-medium text-ink-soft">Todo</span>
          </div>
          <span className="shrink-0 text-2xs tabular-nums text-faint">
            {completed}/{todo.items.length}
          </span>
        </div>
        <div className="flex flex-col gap-1.5">
          <AnimatePresence initial={false}>
            {todo.items.map((item, index) => (
              <motion.div
                key={`${index}-${item.content}`}
                layout
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{
                  layout: SPRING_ROW_ENTRY,
                  opacity: { duration: MOTION.row },
                  y: { duration: MOTION.fast },
                  height: { duration: MOTION.row },
                }}
                className="flex min-w-0 items-start gap-1.5 overflow-hidden"
              >
                {todoStatusIcon(item.status)}
                <span
                  className={clsx(
                    "min-w-0 flex-1 break-words text-xs leading-[1.35] transition-colors",
                    item.status === "completed" && "text-faint line-through",
                    item.status === "in_progress" && "font-medium text-ink-soft",
                    item.status === "pending" && "text-muted",
                  )}
                >
                  {item.content}
                </span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </section>
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
  const automationStatuses = useStore((s) => s.automationStream.statuses);
  const backgroundAgentRows = useStore((s) => s.backgroundAgents.rows);
  const openAutomations = useStore((s) => s.openAutomations);
  const todo = useStore((s) => latestTodoListFromMessages(s.order, s.messages));
  const [collapsed, setCollapsed] = useState(true);

  useBackgroundTasksPoll(currentSessionId);

  const agents = useMemo(
    () =>
      Object.values(backgroundAgentRows)
        .filter((agent) => !currentSessionId || agent.sessionId === currentSessionId)
        .filter(isActiveBackgroundAgent)
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, 8),
    [backgroundAgentRows, currentSessionId],
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

  const hasTodo = todo != null;
  const hasAgents = agents.length > 0;
  const hasAutomations = runningAutomations.length > 0;
  const sectionCount = [hasTodo, hasAgents, hasAutomations].filter(Boolean).length;
  const visible = hasTodo || hasAgents || hasAutomations;

  const todoOpenCount = todo?.items.filter((item) => item.status !== "completed").length ?? 0;
  const totalCount = agents.length + runningAutomations.length + (todo?.items.length ?? 0);
  const activeCount = agents.length + runningAutomations.length + todoOpenCount;

  // Right panel runs at a fixed width — it used to share the
  // `--sidebar-width` CSS var with the left rail, so dragging the left
  // resize-handle would visibly stretch this one too. Hard-coded so the
  // two are independent. Bump alongside RIGHT_PANEL_WIDTH below if you
  // want to make it adjustable later.
  const panelTranslateWidth = RIGHT_PANEL_WIDTH;

  return (
    <>
      {/* Fixed-position toggle button — mirror of `.sidebar-toggle` for
          the left panel. Stays in viewport-fixed coords regardless of
          panel state; icon flips between Open/Close. Aligned vertically
          with the macOS traffic lights (light center y = 25). */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        title={collapsed ? "Show active" : "Hide active"}
        aria-label={collapsed ? `Show active${totalCount > 0 ? ` (${totalCount})` : ""}` : "Hide active"}
        className="right-sidebar-toggle inline-flex items-center gap-1.5 h-[22px] px-1 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
      >
        {collapsed && activeCount > 0 && <StatusDot status="running" pulse />}
        {collapsed && totalCount > 0 && (
          <span className="text-xs tabular-nums text-faint">{totalCount}</span>
        )}
        {collapsed ? (
          <PanelRightOpen size={ICON.MD} strokeWidth={2} />
        ) : (
          <PanelRightClose size={ICON.MD} strokeWidth={2} />
        )}
      </button>

      {/* Panel — always rendered, slides via `x` transform (GPU-
          composited, preserves internal state). Same animation shape as
          App.tsx's left sidebar so the two feel like one system. */}
      <motion.aside
        initial={false}
        animate={{ x: collapsed ? panelTranslateWidth : 0 }}
        transition={{ duration: MOTION.route, ease: EASE_EMPHASIZED }}
        style={{ width: RIGHT_PANEL_BODY_WIDTH }}
        className="glass-surface glass-radius-md absolute top-2 right-2 z-40 flex max-h-[calc(100vh-var(--chat-bottom-h,96px)-24px)] flex-col overflow-hidden"
      >
        {/* Drag region height tuned so the "Active" label's vertical
            center sits at viewport y=25 — same eye-line as the toggle
            icon and the macOS traffic-light center. (panel top-2 = 8px,
            label centered in h-[34px] → 8 + 17 = 25.) */}
        <div className="drag-spacer flex items-center justify-between gap-2 px-3 h-[34px] shrink-0">
          <span className="text-2xs font-medium uppercase tracking-[0.08em] text-faint">
            Active{totalCount > 0 ? ` · ${totalCount}` : ""}
          </span>
        </div>
        <div className="flex min-h-0 flex-col">
          <div className="min-h-0 overflow-y-auto scroll-thin px-3 pb-3 pt-1">
            <ScrollBlurTop />
            {todo && <TodoSidebarSection todo={todo} />}

            {hasAgents && (
              <section className={hasTodo ? "mt-3" : undefined}>
                {sectionCount > 1 && <SectionHeader label="Agents" count={agents.length} />}
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
              <section className={hasTodo || hasAgents ? "mt-3" : undefined}>
                {sectionCount > 1 ? (
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
    </>
  );
}
