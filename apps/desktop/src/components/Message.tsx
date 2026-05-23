import { memo, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Box,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleDot,
  Copy,
  GitBranch,
  ListChecks,
  Pencil,
  Target,
  Terminal,
} from "lucide-react";
import clsx from "clsx";
import { useStore, type UiMessage } from "../store";
import { messageInSourceFocus } from "../lib/messageSourceFocus";
import { ActivityHeader, ActivityTail, ActivityTrace } from "./trace/ActivityTrace";
import type { SkillDescriptor, TodoStatus } from "../api";
import { activityTraceStats } from "../lib/agent";
import { branchAtMessage, viewSkill } from "../actions";
import { Markdown } from "./Markdown";
import { MOTION, EASE_EMPHASIZED } from "../lib/motion";
import { ICON } from "../lib/icons";
import { useTimeoutFlag } from "../lib/hooks";
import { useSmoothStreamedContent } from "../lib/useSmoothStream";

const EASE = EASE_EMPHASIZED;
// Background tint only — the previous inset 1px ring stacked
// visually badly when several adjacent messages were focused at once,
// reading as overlapping outlines. The tint alone is enough cue.
const SOURCE_FOCUS_CLASS = "scroll-mt-20 rounded-[10px] bg-accent-soft/35";

export function Message({ id, isFinal = true }: { id: string; isFinal?: boolean }) {
  const role = useStore((s) => s.messages.get(id)?.role);
  if (!role) return null;
  switch (role) {
    case "user": return <UserMessage id={id} />;
    case "assistant": return <AssistantMessage id={id} isFinal={isFinal} />;
    case "reasoning": return <ReasoningMessage id={id} />;
    case "tool": return <ToolMessage id={id} />;
    case "activity": return <ActivityMessage id={id} />;
    case "todo": return <TodoMessage id={id} />;
    case "error": return <ErrorMessage id={id} />;
    case "status": return <StatusMessage id={id} />;
  }
}

function useMessage(id: string): UiMessage | undefined {
  return useStore((s) => s.messages.get(id));
}

function useIsLast(id: string): boolean {
  return useStore((s) => s.order[s.order.length - 1] === id);
}

function useSourceFocused(id: string): boolean {
  return useStore((s) => messageInSourceFocus(s.messages.get(id), s.sourceFocus, s.currentSessionId));
}

function entryAnimation(message: UiMessage, className: string): string | undefined {
  return message.suppressEntryMotion ? undefined : className;
}

function formatMessageTime(ms: number): string {
  const d = new Date(ms);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const time = d.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  if (sameDay) return time;
  const month = d.toLocaleString(undefined, { month: "short" });
  return `${month} ${d.getDate()} · ${time}`;
}

function MessageActions({ id, role }: { id: string; role: "user" | "assistant" }) {
  const [copied, flashCopied] = useTimeoutFlag(1200);
  const [branching, setBranching] = useState(false);
  const startedAt = useStore((s) => s.messages.get(id)?.turn?.startedAt);

  async function copy() {
    const message = useStore.getState().messages.get(id);
    if (!message) return;
    await window.ntrpDesktop?.clipboard?.writeText(message.content);
    flashCopied();
  }

  function edit() {
    const message = useStore.getState().messages.get(id);
    if (!message) return;
    useStore.getState().setEditingId(id);
    useStore.getState().setDraft(message.content);
    requestAnimationFrame(() => {
      const input = document.querySelector<HTMLTextAreaElement>("#message-input");
      if (!input) return;
      input.focus();
      input.setSelectionRange(message.content.length, message.content.length);
    });
  }

  async function branch() {
    if (branching) return;
    setBranching(true);
    try {
      await branchAtMessage(id);
    } finally {
      setBranching(false);
    }
  }

  const timeLabel = startedAt && startedAt > 0 ? formatMessageTime(startedAt) : null;

  return (
    <div
      className={clsx(
        "flex items-center gap-1.5 h-6 mt-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150",
        role === "user" && "justify-end",
      )}
    >
      <button
        type="button"
        onClick={copy}
        title="Copy"
        className={clsx(
          "grid place-items-center w-6 h-6 rounded-md transition-colors",
          copied ? "text-ok" : "text-faint hover:text-ink hover:bg-surface-soft",
        )}
      >
        {copied ? <Check size={ICON.SM} strokeWidth={2.4} /> : <Copy size={ICON.SM} strokeWidth={2} />}
      </button>
      {role === "assistant" && (
        <button
          type="button"
          onClick={() => void branch()}
          disabled={branching}
          title="Branch from this message"
          className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <GitBranch size={ICON.SM} strokeWidth={2} />
        </button>
      )}
      {role === "user" && (
        <button
          type="button"
          onClick={edit}
          title="Edit and resend"
          className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors"
        >
          <Pencil size={ICON.SM} strokeWidth={2} />
        </button>
      )}
      {timeLabel && (
        <span
          className={clsx(
            "text-xs text-faint tracking-[-0.005em] select-none",
            role === "user" ? "order-first mr-0.5" : "ml-0.5",
          )}
        >
          {timeLabel}
        </span>
      )}
    </div>
  );
}

/** Detect a skill invocation in user content. Handles two formats:
 *
 *  1. Live (pre-server-expansion): `/skill-name <prompt>` — what the
 *     composer actually sends.
 *
 *  2. Historic (server-expanded): `<skill name="...">…body…</skill>\n\n
 *     User request: <prompt>` — what `expand_skill_command` writes into
 *     `sessions.messages` before saving.
 *
 *  Returns the matched skill descriptor + the user's actual prompt
 *  (everything after the skill block / slash command), or null. */
function detectSkillPrefix(
  content: string,
  skills: SkillDescriptor[],
): { skill: SkillDescriptor; rest: string } | null {
  // Format 1: /skill-name args
  if (content.startsWith("/")) {
    const slash = content.match(/^\/([\w-]+)\s*([\s\S]*)$/);
    if (slash) {
      const [, name, rest = ""] = slash;
      const skill = skills.find((s) => s.name === name);
      if (skill) return { skill, rest: rest.trimStart() };
    }
  }

  // Format 2: <skill name="..."> ... </skill>[\n\nUser request: ...]
  if (content.startsWith("<skill")) {
    const xml = content.match(
      /^<skill\s+name="([^"]+)"[^>]*>[\s\S]*?<\/skill>\s*(?:User request:\s*([\s\S]*))?$/,
    );
    if (xml) {
      const [, name, rest = ""] = xml;
      const skill = skills.find((s) => s.name === name);
      if (skill) return { skill, rest: rest.trim() };
    }
  }

  return null;
}

function SkillInlineToken({ skill }: { skill: SkillDescriptor }) {
  return (
    <button
      type="button"
      onClick={() => void viewSkill(skill.name)}
      title={skill.path ?? skill.name}
      className="inline-flex max-w-full items-baseline gap-1.5 align-baseline text-info hover:text-accent-strong transition-colors cursor-pointer"
    >
      <Box size={ICON.SM} strokeWidth={2} className="relative top-[1px] shrink-0" />
      <span className="capitalize">{skill.name.replace(/[_-]/g, " ")}</span>
    </button>
  );
}

function GoalMessageBubble({ objective }: { objective: string }) {
  return (
    <div className="glass-surface glass-radius-lg max-w-[75%] px-3.5 py-2 text-left">
      <div className="mb-1 inline-flex items-center gap-1.5 text-[11px] font-medium text-muted">
        <Target size={ICON.XS} strokeWidth={2} />
        <span>Goal</span>
      </div>
      <div className="whitespace-pre-wrap break-words text-base leading-[1.45] text-ink">
        {objective}
      </div>
    </div>
  );
}

const UserMessage = memo(function UserMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const skills = useStore((s) => s.skills);
  const sourceFocused = useSourceFocused(id);
  if (!message) return null;

  const skillMatch = useMemo(
    () => detectSkillPrefix(message.content, skills),
    [message.content, skills],
  );
  const goalMatch = useMemo(() => {
    const match = message.content.match(/^\/goal\s+([\s\S]+)$/);
    return match ? match[1].trim() : null;
  }, [message.content]);

  const visibleText = goalMatch ?? (skillMatch ? skillMatch.rest : message.content);
  const showBubble = visibleText.trim().length > 0 || Boolean(skillMatch);
  const images = message.images ?? [];

  return (
    <article
      className={clsx(
        "group flex flex-col items-end transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-fade-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      {images.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1.5 max-w-[75%] mb-1.5">
          {images.map((img, i) => (
            <img
              key={i}
              src={`data:${img.media_type};base64,${img.data}`}
              alt=""
              className="rounded-lg max-h-[180px] max-w-[220px] object-cover border border-line-soft"
            />
          ))}
        </div>
      )}
      {goalMatch ? (
        <GoalMessageBubble objective={goalMatch} />
      ) : showBubble && (
        <div className="glass-surface glass-radius-lg max-w-[75%] px-3.5 py-2 text-ink text-base leading-[1.45] break-words text-left">
          {skillMatch && (
            <>
              <SkillInlineToken skill={skillMatch.skill} />
              {visibleText.trim().length > 0 ? " " : null}
            </>
          )}
          <span className="whitespace-pre-wrap">{visibleText}</span>
        </div>
      )}
      <MessageActions id={id} role="user" />
    </article>
  );
});

const AssistantMessage = memo(function AssistantMessage({ id, isFinal = true }: { id: string; isFinal?: boolean }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  const running = useStore((s) => s.running);
  const isStreaming = Boolean(message && running && message.turn?.endedAt === null);
  // Hook order rule: call before any conditional return below.
  const smoothContent = useSmoothStreamedContent(message?.content ?? "", isStreaming);
  if (!message) return null;
  // Drop intermediate assistant messages that finished empty — the model
  // opens TEXT_MESSAGE_START before deciding to tool-call instead, leaving
  // a zero-content article that would otherwise stack ~30px of phantom
  // padding inside the work block.
  if (!isFinal && !isStreaming && !message.content.trim()) return null;
  return (
    <article
      className={clsx(
        "assistant-message group grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-fade-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-streaming={isStreaming ? "true" : undefined}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <Markdown
        content={smoothContent}
        streaming={isStreaming}
        className="text-base leading-[1.45] text-ink break-words [&_p]:m-0"
      />
      {isFinal && <MessageActions id={id} role="assistant" />}
    </article>
  );
});

const ReasoningMessage = memo(function ReasoningMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const isLast = useIsLast(id);
  const running = useStore((s) => s.running);
  const sourceFocused = useSourceFocused(id);
  const [expanded, setExpanded] = useState(false);
  const isStreaming = isLast && running;
  // Only run the rAF loop when the user can actually see it (expanded).
  const smoothContent = useSmoothStreamedContent(message?.content ?? "", isStreaming && expanded);
  if (!message) return null;

  return (
    <article
      className={clsx(
        "grid grid-cols-[minmax(0,1fr)] min-w-0 transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-roll-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="reasoning-head self-start inline-flex items-center gap-1.5 text-xs leading-[1.45] font-medium text-muted hover:text-ink-soft transition-colors select-none"
        data-state={isStreaming ? "streaming" : "done"}
      >
        <Brain size={ICON.XS} strokeWidth={2} />
        <span>{message.title || "Reasoning"}</span>
        <ChevronDown
          size={ICON.XS}
          strokeWidth={2}
          className={clsx("transition-transform duration-200", expanded && "rotate-180")}
        />
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE }}
            style={{ overflow: "hidden" }}
          >
            <Markdown
              content={smoothContent}
              className="mt-2 pl-3.5 border-l-2 border-line text-xs leading-[1.45] text-muted italic break-words [&_p]:m-0"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
});

const ToolMessage = memo(function ToolMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  if (!message) return null;
  const isRunning = !message.content;

  return (
    <article
      className={clsx(
        "grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 font-mono text-xs leading-[1.45] transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-roll-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="tool-line flex items-baseline gap-2 min-w-0" data-state={isRunning ? "running" : "done"}>
        <span className="text-faint shrink-0">↗</span>
        <Terminal size={ICON.XS} strokeWidth={2} className="text-muted shrink-0 self-center" />
        <span className="text-ink-soft font-medium shrink-0">{message.title || "tool"}</span>
        <span className="text-muted truncate min-w-0 flex-1">{message.subtitle || ""}</span>
      </div>
      {!isRunning && (
        <pre className="m-0 mt-[3px] ml-[18px] text-faint font-mono text-sm leading-[1.45] whitespace-pre-wrap max-h-[80px] overflow-hidden [mask-image:linear-gradient(180deg,#000_60%,transparent)]">
          {message.content}
        </pre>
      )}
    </article>
  );
});

const StatusMessage = memo(function StatusMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  if (!message) return null;
  const text = message.title ? `${message.title} · ${message.content}` : message.content;
  return (
    <article
      className={clsx(
        "self-center grid grid-cols-[minmax(0,1fr)] transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-fade-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface-soft font-mono text-sm leading-[1.4] text-muted">
        {text}
      </div>
    </article>
  );
});

const ErrorMessage = memo(function ErrorMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  if (!message) return null;
  return (
    <article
      className={clsx(
        "grid grid-cols-[minmax(0,1fr)] transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-fade-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="px-3.5 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.18)] text-bad text-base leading-[1.45] whitespace-pre-wrap break-words">
        {message.content}
      </div>
    </article>
  );
});

const ActivityMessage = memo(function ActivityMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  const [expanded, setExpanded] = useState(false);
  if (!message?.activity || message.activity.items.length === 0) return null;
  const { items, done } = message.activity;

  // While the run is producing tools, show the rolling tail (last 3).
  // After it's done, switch to a static list with all items and let collapse
  // just animate the container height — switching modes mid-collapse caused
  // the items to swap out (43 → 3) before the height finished shrinking,
  // producing a visible flicker.
  const collapsed = done && !expanded;
  const max = done ? undefined : 3;
  const { totalCount, activeCount } = activityTraceStats(items);

  return (
    <article
      className={clsx(
        "grid grid-cols-[minmax(0,1fr)] transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-roll-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <ActivityTrace>
        <ActivityHeader
          done={done}
          count={totalCount}
          activeCount={activeCount}
          backgrounded={!!message.activity.backgrounded}
          onToggle={done ? () => setExpanded((v) => !v) : undefined}
          expanded={expanded}
        />
        <ActivityTail items={items} max={max} collapsed={collapsed} />
      </ActivityTrace>
    </article>
  );
});

const TodoMessage = memo(function TodoMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  if (!message?.todo || message.todo.items.length === 0) return null;

  const items = message.todo.items;
  const completed = items.filter((item) => item.status === "completed").length;

  return (
    <article
      className={clsx(
        "grid grid-cols-[minmax(0,1fr)] transition-[background-color,box-shadow] duration-300",
        entryAnimation(message, "animate-roll-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="glass-surface glass-radius-lg max-w-[560px] px-3.5 py-3 border border-line-soft">
        <div className="flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-2 min-w-0">
            <ListChecks size={ICON.SM} strokeWidth={2} className="text-muted shrink-0" />
            <span className="text-sm font-medium leading-[1.35] text-ink">Tasks</span>
          </div>
          <span className="shrink-0 text-xs tabular-nums text-muted">{completed}/{items.length}</span>
        </div>
        {message.todo.explanation && (
          <div className="mt-1.5 text-xs leading-[1.4] text-muted break-words">
            {message.todo.explanation}
          </div>
        )}
        <ul className="mt-2.5 flex flex-col gap-1.5">
          {items.map((item, index) => (
            <li key={`${item.status}-${index}-${item.content}`} className="flex items-start gap-2 min-w-0">
              <TodoIcon status={item.status} />
              <span
                className={clsx(
                  "min-w-0 flex-1 text-sm leading-[1.4] break-words",
                  item.status === "completed" && "text-faint line-through",
                  item.status === "in_progress" && "text-ink font-medium",
                  item.status === "pending" && "text-muted",
                )}
              >
                {item.content}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
});

function TodoIcon({ status }: { status: TodoStatus }) {
  if (status === "completed") {
    return <CheckCircle2 size={ICON.SM} strokeWidth={2.2} className="mt-[1px] shrink-0 text-ok" />;
  }
  if (status === "in_progress") {
    return <CircleDot size={ICON.SM} strokeWidth={2.2} className="mt-[1px] shrink-0 text-info" />;
  }
  return <Circle size={ICON.SM} strokeWidth={2} className="mt-[1px] shrink-0 text-faint" />;
}
