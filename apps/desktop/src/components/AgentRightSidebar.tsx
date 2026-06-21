import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CheckCircle2,
  Circle,
  CircleDot,
  MoreHorizontal,
  Plus,
  X,
} from "lucide-react";
import {
  cancelChildAgentApi,
  clearTodoOverrideApi,
  getChildAgentResultApi,
  getTodoOverrideApi,
  pinToMemoryApi,
  sendToChildAgentApi,
  setTodoOverrideApi,
  type Automation,
  type TodoListItem,
  type TodoStatus,
} from "../api";
import { nextTodoStatus, todoSignature } from "../lib/todoOverride";
import { isInternalAutomation, isIterationLoop } from "../lib/automationFilters";
import {
  DURATION_RIGHT_PANEL_HIDE,
  EASE_EMPHASIZED,
  EASE_OUT,
  MOTION,
  originFromEvent,
  RISE_IN,
  RISE_SETTLED,
  ROW_EXIT,
  SPRING_ROW_ENTRY,
} from "../lib/tokens/motion";
import { ICON } from "../lib/icons";
import { getState, useStore, type BackgroundAgent, type TodoListState, type UiMessage } from "../store";
import {
  agentRunFromAutomation,
  agentRunFromBackgroundAgent,
  isActiveAgentStatus,
  isAgentSessionId,
  parentSessionIdOf,
  resultSnippet,
} from "../lib/agentRun";
import { createSession, refreshChildAgents, sendMessage, switchSession } from "../actions";
import { useWorkflows } from "../hooks/useWorkflows";
import { isActiveWorkflow, workflowKey } from "../store/workflow-domain";
import { ExpandableWorkflowCard } from "./workflow/WorkflowDetail";
import { ScrollFadeTop } from "./ScrollBlur";
import { BlurSwap } from "./BlurSwap";
import { StatusDot } from "./StatusDot";
import { AgentRunRow } from "./agents/AgentRunRow";
import { Collapse } from "./ui/Collapse";
import { Tooltip } from "./ui/Tooltip";
export { isActiveBackgroundAgent } from "../store/background-agent-domain";
export { StatusDot } from "./StatusDot";

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
// Short rightward drift on hide — enough to give the fade/blur a direction
// without it reading as a full slide-back.
const RIGHT_PANEL_HIDE_DRIFT = 48;

const RECENT_AGENT_LIMIT = 6;

// One list-motion recipe for every roster section (todos, agents, workflows,
// automations): under popLayout the removed row dissolves out of flow while
// siblings FLIP up on SPRING_ROW_ENTRY. Spread onto the keyed motion.div.
const rosterRowMotion = {
  layout: true,
  initial: { opacity: 0, y: -4 },
  animate: { opacity: 1, y: 0 },
  exit: { ...ROW_EXIT, transition: { duration: MOTION.fast, ease: EASE_OUT } },
  transition: { layout: SPRING_ROW_ENTRY, duration: MOTION.row, ease: EASE_OUT },
} as const;

function useChildAgentsPoll(sessionId: string | null): void {
  // Live BackgroundTaskEvents already keep the roster current for the session
  // being viewed; this poll is the fallback for the cases events don't cover
  // (agents spawned in the parent while a child is open, terminal status missed
  // while disconnected). Reconnect resync lives in reloadAllCollections.
  useEffect(() => {
    if (!sessionId) return;
    const tick = () => {
      if (document.visibilityState === "visible") void refreshChildAgents(sessionId);
    };
    void refreshChildAgents(sessionId);
    const id = window.setInterval(tick, 5000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [sessionId]);
}

// Lazily fetch a one-line result preview for each terminal agent, once.
// Running agents have no durable result yet, so they're skipped.
function useChildAgentResults(
  sessionId: string | null,
  agents: BackgroundAgent[],
): Record<string, string> {
  const config = useStore((s) => s.config);
  const [snippets, setSnippets] = useState<Record<string, string>>({});
  const done = useRef<Set<string>>(new Set());
  const inflight = useRef<Set<string>>(new Set());

  // The panel mounts once and is reused across navigation, so reset the
  // per-session caches when the roster session changes.
  useEffect(() => {
    done.current = new Set();
    inflight.current = new Set();
    setSnippets({});
  }, [sessionId]);

  // Include resultRef so the effect re-fires when a durable result lands
  // after the agent went terminal (otherwise an empty first fetch never retries).
  const terminalKeys = agents
    .filter((agent) => !isActiveAgentStatus(agent.status))
    .map((agent) => `${agent.taskId}:${agent.resultRef ?? ""}`)
    .join(",");

  useEffect(() => {
    if (!sessionId) return;
    for (const agent of agents) {
      if (isActiveAgentStatus(agent.status)) continue;
      const key = agent.taskId;
      if (done.current.has(key) || inflight.current.has(key)) continue;
      inflight.current.add(key);
      void getChildAgentResultApi(config, sessionId, key)
        .then((result) => {
          const snippet = resultSnippet(result.result ?? undefined);
          // Keyed + idempotent, so it's safe to apply even if the roster
          // changed mid-flight. Only mark done once we actually have a
          // preview, so a result written just after the agent goes terminal
          // still resolves on a later poll instead of staying blank forever.
          if (snippet) {
            done.current.add(key);
            setSnippets((prev) => ({ ...prev, [key]: snippet }));
          }
        })
        .catch(() => {})
        .finally(() => {
          inflight.current.delete(key);
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, config, terminalKeys]);

  return snippets;
}

// One agent row in the hub: the unified AgentRunRow, plus the per-row
// cancel state and open-session wiring.
function SidebarAgentRow({
  agent,
  resultPreview,
  active,
}: {
  agent: BackgroundAgent;
  resultPreview?: string;
  active?: boolean;
}) {
  const config = useStore((s) => s.config);
  const upsertBackgroundAgent = useStore((s) => s.upsertBackgroundAgent);
  const setDraft = useStore((s) => s.setDraft);
  const pushToast = useStore((s) => s.pushToast);
  // The server's `command` is a generic "Agent" placeholder until an async
  // labeler runs; the child session's own name (the task) is the better title.
  const childName = useStore((s) =>
    agent.childSessionId
      ? s.sessions.find((session) => session.session_id === agent.childSessionId)?.name ?? null
      : null,
  );
  const [cancelling, setCancelling] = useState(false);

  const stop = async () => {
    if (agent.status !== "running" || cancelling) return;
    setCancelling(true);
    try {
      await cancelChildAgentApi(config, agent.sessionId, agent.taskId);
      upsertBackgroundAgent({ ...agent, status: "cancel_requested", updatedAt: Date.now() });
    } catch {
      setCancelling(false);
    }
  };

  const open = agent.childSessionId
    ? () => void switchSession(agent.childSessionId as string)
    : undefined;

  // Return the promise (don't `void` it) so the composer can await delivery
  // and restore the draft if the agent finished between render and send.
  const send =
    agent.status === "running"
      ? (message: string) => sendToChildAgentApi(config, agent.sessionId, agent.taskId, message)
      : undefined;

  // Finished agents get handoff actions: drop the full result into the
  // parent composer (reply), or seed a fresh session with it (route). The
  // full result is fetched on demand — the row only caches a one-line preview.
  const fetchResult = async (): Promise<string> => {
    const r = await getChildAgentResultApi(config, agent.sessionId, agent.taskId);
    return (r.result ?? "").trim();
  };
  const handoff = !isActiveAgentStatus(agent.status)
    ? {
        onReply: async () => {
          const text = await fetchResult();
          if (!text) return;
          const prev = getState().draft;
          setDraft(prev.trim() ? `${prev}\n\n${text}` : text);
        },
        onPin: async () => {
          const text = await fetchResult();
          if (!text) return;
          try {
            const outcome = await pinToMemoryApi(config, text);
            pushToast({
              id: crypto.randomUUID(),
              title: outcome.written ? "Pinned to memory" : "Already in memory",
              status: "completed",
              target: { kind: "session", sessionId: agent.sessionId },
            });
          } catch (error) {
            pushToast({
              id: crypto.randomUUID(),
              title: "Couldn't pin to memory",
              detail: error instanceof Error ? error.message : String(error),
              status: "failed",
              target: { kind: "session", sessionId: agent.sessionId },
            });
          }
        },
        onRoute: async () => {
          const text = await fetchResult();
          if (!text) return;
          await createSession();
          await sendMessage(text);
        },
      }
    : undefined;

  const run = agentRunFromBackgroundAgent(agent, resultPreview);
  const named = childName?.trim() ? { ...run, name: childName.trim() } : run;

  return (
    <AgentRunRow
      run={named}
      onOpen={open}
      onStop={agent.status === "running" ? stop : undefined}
      stopping={cancelling}
      active={active}
      onSend={send}
      handoff={handoff}
    />
  );
}

// A running automation in the hub — the SAME agent body as a sub-agent run.
// An automation is the same abstraction as a parent/child agent, so it flows
// through the shared view-model and renders via AgentRunRow. The live stream
// status (if any) overrides the default progress line.
function SidebarAutomationRow({
  automation,
  streamStatus,
}: {
  automation: Automation;
  streamStatus: string | undefined;
}) {
  const openAutomations = useStore((s) => s.openAutomations);
  const sessions = useStore((s) => s.sessions);
  const closeAutomations = useStore((s) => s.closeAutomations);
  const channel =
    sessions.find((sx) => sx.origin_automation_id === automation.task_id) ?? null;

  const base = agentRunFromAutomation(automation);
  const run = streamStatus ? { ...base, progress: streamStatus } : base;

  const open = channel
    ? () => {
        void switchSession(channel.session_id);
        closeAutomations();
      }
    : () => openAutomations();

  return <AgentRunRow run={run} onOpen={open} />;
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

// Inline single-line editor for a todo (edit existing or add new). Commits on
// Enter/blur, cancels on Escape; the ref guards against the blur-after-unmount
// double-fire (Enter -> commit -> unmount -> blur).
function TodoEditInput({
  initial,
  placeholder,
  onCommit,
  onCancel,
}: {
  initial: string;
  placeholder?: string;
  onCommit: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const done = useRef(false);
  const commit = () => {
    if (done.current) return;
    done.current = true;
    onCommit(value);
  };
  const cancel = () => {
    if (done.current) return;
    done.current = true;
    onCancel();
  };
  return (
    <input
      autoFocus
      value={value}
      placeholder={placeholder}
      spellCheck={false}
      aria-label={placeholder ?? "Edit task"}
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          commit();
        } else if (event.key === "Escape") {
          event.preventDefault();
          cancel();
        }
      }}
      onBlur={commit}
      className="min-w-0 flex-1 bg-transparent border-0 p-0 text-xs leading-[1.35] text-ink-soft placeholder:text-muted outline-none"
    />
  );
}

interface EditableTodo {
  key: string;
  content: string;
  status: TodoStatus;
}

// Todos carry no server id, so mint a stable key per item — editing text then
// doesn't remount the row (no flash) and deleting animates the right row.
let todoKeySeq = 0;
const withTodoKeys = (items: TodoListItem[]): EditableTodo[] =>
  items.map((item) => ({ key: `todo-${todoKeySeq++}`, content: item.content, status: item.status }));

// Editable todo list. Agent-produced todos are the base; the user's manual
// edits persist server-side (so the agent sees them on its next run) and last
// until the agent emits a different list, which supersedes them.
function useEditableTodo(sessionId: string | null, todo: TodoListState) {
  const config = useStore((s) => s.config);
  const agentItems = todo.items;
  const agentSig = useMemo(() => todoSignature(agentItems), [agentItems]);
  const [items, setItems] = useState<EditableTodo[]>(() => withTodoKeys(agentItems));
  const [edited, setEdited] = useState(false);
  const lastSig = useRef(agentSig);

  // Load any persisted override on mount (the section remounts per session).
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void getTodoOverrideApi(config, sessionId)
      .then((override) => {
        if (!cancelled && override) {
          setItems(withTodoKeys(override.items));
          setEdited(true);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessionId, config]);

  // The agent emitted a new list — it supersedes the manual edit (the server
  // already cleared the override when update_todos ran).
  useEffect(() => {
    if (lastSig.current === agentSig) return;
    lastSig.current = agentSig;
    setItems(withTodoKeys(agentItems));
    setEdited(false);
  }, [agentSig, agentItems]);

  const commit = (next: EditableTodo[]) => {
    setItems(next);
    setEdited(true);
    if (sessionId) {
      void setTodoOverrideApi(
        config,
        sessionId,
        next.map(({ content, status }) => ({ content, status })),
      ).catch(() => {});
    }
  };

  return {
    items,
    edited,
    add: (content: string) => commit([...items, { key: `todo-${todoKeySeq++}`, content, status: "pending" }]),
    edit: (key: string, content: string) =>
      commit(items.map((item) => (item.key === key ? { ...item, content } : item))),
    remove: (key: string) => commit(items.filter((item) => item.key !== key)),
    cycle: (key: string) =>
      commit(items.map((item) => (item.key === key ? { ...item, status: nextTodoStatus(item.status) } : item))),
    reset: () => {
      setItems(withTodoKeys(agentItems));
      setEdited(false);
      if (sessionId) void clearTodoOverrideApi(config, sessionId).catch(() => {});
    },
  };
}

function TodoSidebarSection({ todo, sessionId }: { todo: TodoListState; sessionId: string | null }) {
  const { items, edited, add, edit, remove, cycle, reset } = useEditableTodo(sessionId, todo);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const completed = items.filter((item) => item.status === "completed").length;

  return (
    <section>
      <div className="flex items-center justify-between gap-2 px-0.5 pt-0.5 pb-1.5">
        <span className="text-2xs font-medium uppercase tracking-[0.08em] text-muted">Tasks</span>
        <div className="flex items-center gap-1.5">
          {edited && (
            <Tooltip label="Reset to the agent's list">
              <button
                type="button"
                onClick={reset}
                className="text-2xs text-faint hover:text-ink transition-colors duration-row ease-out"
              >
                reset
              </button>
            </Tooltip>
          )}
          <span className="text-2xs tabular-nums text-faint">
            {completed}/{items.length}
          </span>
          <Tooltip label="Add a task">
            <button
              type="button"
              onClick={() => setAdding(true)}
              aria-label="Add a task"
              className="grid place-items-center w-4 h-4 rounded text-faint hover:text-ink hover:bg-surface-soft/70 transition-[color,background-color,scale] duration-check ease-out active:scale-[0.97]"
            >
              <Plus size={ICON.XS} strokeWidth={2} />
            </button>
          </Tooltip>
        </div>
      </div>
      <div className="relative flex flex-col gap-0.5">
        <AnimatePresence initial={false} mode="popLayout">
          {items.map((item) => (
            <motion.div
              key={item.key}
              {...rosterRowMotion}
              className="group/todo flex min-w-0 items-start gap-1.5 rounded px-1 -mx-1 hover:bg-surface-soft/40"
            >
              <Tooltip label="Cycle status">
                <button
                  type="button"
                  onClick={() => cycle(item.key)}
                  aria-label="Cycle status"
                  className="mt-[1px] shrink-0 rounded transition-[scale] duration-check ease-out active:scale-[0.97]"
                >
                  {todoStatusIcon(item.status)}
                </button>
              </Tooltip>
              {editingKey === item.key ? (
                <TodoEditInput
                  initial={item.content}
                  onCommit={(value) => {
                    if (value.trim()) edit(item.key, value.trim());
                    setEditingKey(null);
                  }}
                  onCancel={() => setEditingKey(null)}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setEditingKey(item.key)}
                  title="Edit"
                  className={clsx(
                    "min-w-0 flex-1 break-words text-left text-xs leading-[1.35] transition-colors duration-row ease-out hover:text-ink",
                    item.status === "completed" && "text-faint line-through",
                    item.status === "in_progress" && "font-medium text-ink-soft",
                    item.status === "pending" && "text-muted",
                  )}
                >
                  {item.content}
                </button>
              )}
              <Tooltip label="Delete task">
                <button
                  type="button"
                  onClick={() => remove(item.key)}
                  aria-label="Delete task"
                  className="mt-[1px] shrink-0 grid place-items-center w-4 h-4 rounded text-faint opacity-0 group-hover/todo:opacity-100 hover:text-bad transition-[opacity,color,scale] duration-row ease-out active:scale-[0.97]"
                >
                  <X size={ICON.XS} strokeWidth={2} />
                </button>
              </Tooltip>
            </motion.div>
          ))}
        </AnimatePresence>
        {adding && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: MOTION.row, ease: EASE_OUT }}
            className="flex min-w-0 items-start gap-1.5 px-1 -mx-1"
          >
            <Circle size={ICON.XS} strokeWidth={2} className="mt-[2px] shrink-0 text-faint" />
            <TodoEditInput
              initial=""
              placeholder="New task…"
              onCommit={(value) => {
                if (value.trim()) add(value.trim());
                setAdding(false);
              }}
              onCancel={() => setAdding(false)}
            />
          </motion.div>
        )}
      </div>
    </section>
  );
}

function SectionHeader({ label, count }: { label: string; count?: number }) {
  return (
    <div className="flex items-baseline justify-between px-0.5 pt-0.5 pb-1">
      <span className="text-2xs font-medium uppercase tracking-[0.08em] text-muted">
        {label}
      </span>
      {count != null && count > 0 && (
        <span className="text-2xs text-faint tabular-nums">{count}</span>
      )}
    </div>
  );
}

// The single load-bearing "needs you" signal: a run is paused waiting on
// an approval. One amber row that opens the review modal.
function ApprovalsRow() {
  const count = useStore((s) => s.pendingApprovals.length);
  const firstToolId = useStore((s) => s.pendingApprovals[0]?.toolId);
  const review = useStore((s) => s.setReviewingApproval);

  return (
    <AnimatePresence initial={false}>
      {count > 0 && firstToolId && (
        <motion.div
          key="approvals"
          initial={{ ...RISE_IN, y: -4 }}
          animate={RISE_SETTLED}
          exit={{ opacity: 0, scale: 0.97, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
          transition={{ duration: MOTION.row, ease: EASE_OUT }}
        >
          <button
            type="button"
            onClick={(e) => review(firstToolId, originFromEvent(e.currentTarget))}
            className="flex w-full items-center gap-2 rounded-[8px] bg-warn/10 px-2.5 py-2 text-left transition-[background-color,scale] duration-row ease-out hover:bg-warn/15 active:scale-[0.985]"
          >
            <span className="inline-block w-1.5 h-1.5 rounded-full shrink-0 bg-warn" aria-hidden />
            <span className="flex-1 text-xs text-ink-soft">
              {count} awaiting approval
            </span>
            <span className="shrink-0 text-2xs text-warn">Review →</span>
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Back-to-parent chip shown while viewing a child agent session — turns the
// hub into the agent's breadcrumb + sibling switcher.
function ParentBreadcrumb({
  parentId,
  parentName,
}: {
  parentId: string;
  parentName: string | null;
}) {
  return (
    <button
      type="button"
      onClick={() => void switchSession(parentId)}
      title={parentName ? `Back to ${parentName}` : "Back to parent session"}
      className="group/bc flex w-full items-center gap-1.5 rounded-[8px] px-1.5 py-1 text-left text-xs text-muted transition-[background-color,color,scale] duration-row ease-out hover:bg-surface-soft/60 hover:text-ink active:scale-[0.985]"
    >
      <ArrowLeft
        size={ICON.SM}
        strokeWidth={2}
        className="shrink-0 text-faint transition-colors duration-row ease-out group-hover/bc:text-ink"
      />
      <span className="truncate">{parentName ?? "Parent session"}</span>
    </button>
  );
}

export function AgentRightSidebar() {
  const currentSessionId = useStore((s) => s.currentSessionId);
  const sessions = useStore((s) => s.sessions);
  const automations = useStore((s) => s.automations);
  const automationStatuses = useStore((s) => s.automationStream.statuses);
  const backgroundAgentRows = useStore((s) => s.backgroundAgents.rows);
  const openAutomations = useStore((s) => s.openAutomations);
  const todo = useStore((s) => latestTodoListFromMessages(s.order, s.messages));
  // Shared (in prefs) so the chat area can reflow to dock the panel.
  const collapsed = useStore((s) => s.prefs.rightPanelCollapsed);
  const setPref = useStore((s) => s.setPref);

  const toggleCollapsed = () => setPref("rightPanelCollapsed", !collapsed);

  // When viewing a child agent session, the roster is the *parent's* agents
  // (so the hub shows siblings + a back breadcrumb). Prefer the server's
  // immediate `parent_session_id`; fall back to parsing the child id
  // (`${parentId}::${hex}`, nestable) when the record isn't loaded yet.
  const currentSession = sessions.find((s) => s.session_id === currentSessionId);
  const inAgentSession =
    currentSession?.session_type === "agent" || isAgentSessionId(currentSessionId);
  const parentId = inAgentSession
    ? currentSession?.parent_session_id ?? parentSessionIdOf(currentSessionId)
    : null;
  const rosterSessionId = inAgentSession ? parentId : currentSessionId;
  const parentName = sessions.find((s) => s.session_id === parentId)?.name ?? null;

  useChildAgentsPoll(rosterSessionId);

  const workflows = useWorkflows(rosterSessionId);
  const dismissWorkflow = useStore((s) => s.dismissWorkflow);
  // A workflow's leaf agents are spawned with parent_id = the workflow's tool
  // call, so they share its parentToolCallId. They belong INSIDE the workflow
  // (its drill-in), not the top-level roster.
  const workflowParentIds = useMemo(
    () => new Set(workflows.map((w) => w.parentToolCallId).filter(Boolean)),
    [workflows],
  );

  const agents = useMemo(() => {
    const all = Object.values(backgroundAgentRows).filter(
      (agent) =>
        agent.sessionId === rosterSessionId &&
        !(agent.parentToolCallId && workflowParentIds.has(agent.parentToolCallId)),
    );
    const active = all
      .filter((agent) => isActiveAgentStatus(agent.status))
      .sort((a, b) => b.updatedAt - a.updatedAt);
    const terminal = all
      .filter((agent) => !isActiveAgentStatus(agent.status))
      .sort((a, b) => b.updatedAt - a.updatedAt);
    const recent = terminal.slice(0, RECENT_AGENT_LIMIT);
    // Always include the agent whose session we're viewing, even past the
    // recent cap — hoist it to the top of recent so the highlighted row isn't
    // stranded at the bottom.
    if (inAgentSession) {
      const current = terminal.find((agent) => agent.childSessionId === currentSessionId);
      if (current && !recent.includes(current)) recent.unshift(current);
    }
    return [...active, ...recent];
  }, [backgroundAgentRows, rosterSessionId, inAgentSession, currentSessionId, workflowParentIds]);

  const resultSnippets = useChildAgentResults(rosterSessionId, agents);

  // Dismissed keys (persisted in prefs) hide cards from the hub only — the
  // domain rows live on so the chat-trace card keeps its data, and the
  // UNfiltered `workflows` above still contains leaf agents via
  // workflowParentIds (a dismissed workflow's agents must not resurface as
  // roster orphans).
  const dismissedWorkflows = useStore((s) => s.prefs.dismissedWorkflows);
  const visibleWorkflows = useMemo(() => {
    const dismissed = new Set(dismissedWorkflows);
    return workflows.filter((w) => !dismissed.has(workflowKey(w.sessionId, w.workflowId)));
  }, [workflows, dismissedWorkflows]);

  const sortedWorkflows = useMemo(() => {
    const active = visibleWorkflows.filter(isActiveWorkflow).sort((a, b) => b.updatedAt - a.updatedAt);
    const done = visibleWorkflows
      .filter((w) => !isActiveWorkflow(w))
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, RECENT_AGENT_LIMIT);
    return [...active, ...done];
  }, [visibleWorkflows]);
  const runningWorkflowCount = visibleWorkflows.filter(isActiveWorkflow).length;

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

  const approvalCount = useStore((s) => s.pendingApprovals.length);

  const runningAgentCount = agents.filter((agent) =>
    isActiveAgentStatus(agent.status),
  ).length;
  const hasBreadcrumb = inAgentSession && !!parentId;
  const hasTodo = todo != null;
  const hasAgents = agents.length > 0;
  const hasWorkflows = sortedWorkflows.length > 0;
  const hasAutomations = runningAutomations.length > 0;
  const sectionCount = [hasTodo, hasAgents, hasWorkflows, hasAutomations].filter(Boolean).length;
  const visible = hasTodo || hasAgents || hasWorkflows || hasAutomations;

  const todoOpenCount = todo?.items.filter((item) => item.status !== "completed").length ?? 0;
  const totalCount =
    agents.length + sortedWorkflows.length + runningAutomations.length + (todo?.items.length ?? 0);
  const activeCount =
    runningAgentCount + runningWorkflowCount + runningAutomations.length + todoOpenCount;

  return (
    <>
      {/* Fixed-position toggle — the single open/close control for the
          agent hub (mirror of `.sidebar-toggle`). Stays in viewport-fixed
          coords regardless of panel state; when open it floats over the
          panel header's right edge (z-60 > panel z-40). The glyph swaps
          from dots (open me) to a right arrow (close → push the panel
          off-edge) so the control reads as a direct action. A running-
          status dot rides alongside when the panel is collapsed and work
          is active. Aligned with the macOS traffic lights (center y=25). */}
      <button
        type="button"
        onClick={toggleCollapsed}
        title={collapsed ? "Show active" : "Hide active"}
        aria-label={collapsed ? `Show active${totalCount > 0 ? ` (${totalCount})` : ""}` : "Hide active"}
        className="right-sidebar-toggle inline-flex items-center gap-1.5 h-[22px] px-1 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-row ease-out active:scale-[0.96]"
      >
        {collapsed && activeCount > 0 && <StatusDot status="running" pulse />}
        <BlurSwap swapKey={collapsed ? "open" : "close"}>
          {collapsed ? (
            <MoreHorizontal size={ICON.MD} strokeWidth={2} />
          ) : (
            <ArrowRight size={ICON.MD} strokeWidth={2} />
          )}
        </BlurSwap>
      </button>

      {/* Panel — always rendered (preserves internal state). Asymmetric
          motion:
          • OPEN slides in from the right edge (x: off-edge → 0) with the
            same MOTION.route/EASE_EMPHASIZED recipe as App.tsx's left
            sidebar; opacity/blur are reset instantly while still off-edge so
            the entrance is a clean slide, not a fade.
          • HIDE keeps it an opaque card that fades + blurs out while drifting
            a short distance right (direction without a full slide-back). The
            chat reflows on the SAME duration (DURATION_RIGHT_PANEL_HIDE), so
            the fading card crossfades to reveal the expanding content rather
            than overlapping it or pausing. */}
      <motion.aside
        initial={false}
        animate={
          collapsed
            ? { x: RIGHT_PANEL_HIDE_DRIFT, opacity: 0, filter: "blur(6px)" }
            : { x: [RIGHT_PANEL_WIDTH, 0], opacity: 1, filter: "blur(0px)" }
        }
        transition={
          collapsed
            ? { duration: DURATION_RIGHT_PANEL_HIDE, ease: EASE_OUT }
            : {
                x: { duration: MOTION.route, ease: EASE_EMPHASIZED },
                opacity: { duration: 0 },
                filter: { duration: 0 },
              }
        }
        style={{
          width: RIGHT_PANEL_BODY_WIDTH,
          pointerEvents: collapsed ? "none" : "auto",
        }}
        aria-hidden={collapsed}
        className="surface-panel surface-radius-md absolute top-2 bottom-2 right-2 z-40 flex flex-col overflow-hidden"
      >
        {/* Drag region height tuned so the "Active" label's vertical
            center sits at viewport y=25 — same eye-line as the fixed dots
            toggle and the macOS traffic-light center. (panel top-2 = 8px,
            label centered in h-[34px] → 8 + 17 = 25.) The dots toggle
            (z-60, fixed right-14) floats over this header's right edge and
            is the single open/close control — no redundant in-panel X. */}
        <div className="drag-spacer flex items-center px-3 h-[34px] shrink-0">
          <span className="text-2xs font-medium uppercase tracking-[0.08em] text-muted">
            Active
          </span>
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 min-h-0 overflow-y-auto scroll-thin px-3 pb-3 pt-1">
            <ScrollFadeTop />
            <div className="space-y-3">
              <Collapse open={hasBreadcrumb}>
                {parentId && <ParentBreadcrumb parentId={parentId} parentName={parentName} />}
              </Collapse>
              <ApprovalsRow />
              {todo && (
                <TodoSidebarSection
                  key={currentSessionId ?? "none"}
                  todo={todo}
                  sessionId={currentSessionId}
                />
              )}

              {hasAgents && (
                <section>
                  {(sectionCount > 1 || hasBreadcrumb) && (
                    <SectionHeader
                      label={hasBreadcrumb ? "Agents in this run" : "Agents"}
                      count={agents.length}
                    />
                  )}
                  <div className="relative">
                    <AnimatePresence initial={false} mode="popLayout">
                      {agents.map((agent) => (
                        <motion.div key={`${agent.sessionId}:${agent.taskId}`} {...rosterRowMotion}>
                          <SidebarAgentRow
                            agent={agent}
                            resultPreview={resultSnippets[agent.taskId]}
                            active={inAgentSession && agent.childSessionId === currentSessionId}
                          />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </section>
              )}

              {hasWorkflows && (
                <section>
                  {(sectionCount > 1 || hasBreadcrumb) && (
                    <SectionHeader label="Workflows" count={sortedWorkflows.length} />
                  )}
                  <div className="relative">
                    <AnimatePresence initial={false} mode="popLayout">
                      {sortedWorkflows.map((wf) => (
                        <motion.div key={wf.workflowId} {...rosterRowMotion}>
                          <div className="group/wfrow relative py-0.5">
                            <ExpandableWorkflowCard workflow={wf} />
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                dismissWorkflow(wf.sessionId, wf.workflowId);
                              }}
                              title="Dismiss"
                              className="absolute -right-1 -top-1 grid place-items-center w-5 h-5 rounded-full border border-line-soft bg-surface text-faint opacity-0 transition-[opacity,color,scale] duration-row ease-out hover:text-bad active:scale-[0.97] group-hover/wfrow:opacity-100"
                            >
                              <X size={ICON.XS} strokeWidth={2} />
                            </button>
                          </div>
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </section>
              )}

              {hasBreadcrumb && !hasAgents && (
                <p className="px-3 py-2 text-center text-xs text-muted">
                  No other agents in this run.
                </p>
              )}

              {hasAutomations && (
                <section>
                  {sectionCount > 1 ? (
                    <button
                      type="button"
                      onClick={(e) => openAutomations(originFromEvent(e.currentTarget))}
                      className="block w-full text-left hover:text-ink transition-colors duration-row ease-out"
                      title="Open automations"
                    >
                      <SectionHeader
                        label="Automations"
                        count={runningAutomations.length}
                      />
                    </button>
                  ) : null}
                  <div className="relative">
                    <AnimatePresence initial={false} mode="popLayout">
                      {runningAutomations.map((automation) => (
                        <motion.div key={automation.task_id} {...rosterRowMotion}>
                          <SidebarAutomationRow
                            automation={automation}
                            streamStatus={automationStatuses[automation.task_id]}
                          />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </section>
              )}

              <AnimatePresence initial={false}>
                {!visible && approvalCount === 0 && !hasBreadcrumb && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, filter: "blur(3px)", transition: { duration: MOTION.fast, ease: EASE_OUT } }}
                    transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
                    className="grid place-items-center gap-2.5 min-h-[120px] px-3 text-center"
                  >
                    <span
                      aria-hidden
                      className="grid place-items-center w-9 h-9 rounded-xl bg-surface-soft text-faint"
                    >
                      <Bot size={ICON.MD} strokeWidth={2} />
                    </span>
                    <p className="text-xs text-muted leading-relaxed">
                      No agents yet.
                      <br />
                      Background agents you start appear here.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </motion.aside>
    </>
  );
}
