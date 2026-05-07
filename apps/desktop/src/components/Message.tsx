import { memo, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Brain, Check, ChevronDown, Copy, GitBranch, Pencil, Sparkles, Terminal } from "lucide-react";
import clsx from "clsx";
import { useStore, type UiMessage } from "../store";
import { messageInSourceFocus } from "../lib/messageSourceFocus";
import { ActivityHeader, ActivityTail, ActivityTrace } from "./trace/ActivityTrace";
import { ApprovalCard } from "./ApprovalCard";
import type { SkillDescriptor } from "../api";
import { branchAtMessage, viewSkill } from "../actions";
import { Markdown } from "./Markdown";
import { MOTION, EASE_EMPHASIZED } from "../lib/motion";

const EASE = EASE_EMPHASIZED;
const SOURCE_FOCUS_CLASS = "scroll-mt-20 rounded-[10px] bg-accent-soft/35 shadow-[0_0_0_1px_var(--color-accent-strong)]";

export function Message({ id, isFinal = true }: { id: string; isFinal?: boolean }) {
  const role = useStore((s) => s.messages.get(id)?.role);
  if (!role) return null;
  switch (role) {
    case "user": return <UserMessage id={id} />;
    case "assistant": return <AssistantMessage id={id} isFinal={isFinal} />;
    case "reasoning": return <ReasoningMessage id={id} />;
    case "tool": return <ToolMessage id={id} />;
    case "activity": return <ActivityMessage id={id} />;
    case "approval": return <ApprovalCard id={id} />;
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
  const [copied, setCopied] = useState(false);
  const [branching, setBranching] = useState(false);
  const startedAt = useStore((s) => s.messages.get(id)?.turn?.startedAt);

  async function copy() {
    const message = useStore.getState().messages.get(id);
    if (!message) return;
    await window.ntrpDesktop?.clipboard?.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
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
        {copied ? <Check size={13} strokeWidth={2.4} /> : <Copy size={13} strokeWidth={2} />}
      </button>
      {role === "assistant" && (
        <button
          type="button"
          onClick={() => void branch()}
          disabled={branching}
          title="Branch from this message"
          className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <GitBranch size={13} strokeWidth={2} />
        </button>
      )}
      {role === "user" && (
        <button
          type="button"
          onClick={edit}
          title="Edit and resend"
          className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors"
        >
          <Pencil size={13} strokeWidth={2} />
        </button>
      )}
      {timeLabel && (
        <span
          className={clsx(
            "text-[11px] text-faint tracking-[-0.005em] select-none",
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

function SkillChip({ skill }: { skill: SkillDescriptor }) {
  return (
    <button
      type="button"
      onClick={() => void viewSkill(skill.name)}
      title={skill.path ?? skill.name}
      className="inline-flex items-center gap-1.5 mt-1 px-2 py-1 rounded-md bg-surface-sunken/80 border border-line-soft text-[11.5px] font-medium text-ink-soft hover:bg-surface-soft hover:border-line transition-colors cursor-pointer"
    >
      <Sparkles size={11} strokeWidth={2} className="text-accent" />
      <span className="capitalize">{skill.name.replace(/[_-]/g, " ")}</span>
    </button>
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

  const visibleText = skillMatch ? skillMatch.rest : message.content;
  const showBubble = visibleText.trim().length > 0;
  const images = message.images ?? [];

  return (
    <article
      className={clsx("group flex flex-col items-end animate-fade-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
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
      {showBubble && (
        <div className="max-w-[75%] px-3.5 py-2 rounded-[18px] bg-surface-sunken text-ink text-[13.5px] leading-[1.5] whitespace-pre-wrap break-words text-left">
          {visibleText}
        </div>
      )}
      {skillMatch && <SkillChip skill={skillMatch.skill} />}
      <MessageActions id={id} role="user" />
    </article>
  );
});

const AssistantMessage = memo(function AssistantMessage({ id, isFinal = true }: { id: string; isFinal?: boolean }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  const running = useStore((s) => s.running);
  const isStreaming = Boolean(message && running && message.turn?.endedAt === null);
  if (!message) return null;
  // Drop intermediate assistant messages that finished empty — the model
  // opens TEXT_MESSAGE_START before deciding to tool-call instead, leaving
  // a zero-content article that would otherwise stack ~30px of phantom
  // padding inside the work block.
  if (!isFinal && !isStreaming && !message.content.trim()) return null;
  return (
    <article
      className={clsx("assistant-message group grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 animate-fade-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
      data-streaming={isStreaming ? "true" : undefined}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <Markdown
        content={message.content}
        streaming={isStreaming}
        className="py-0.5 text-[14px] leading-[1.62] text-ink tracking-[-0.005em] break-words"
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
  if (!message) return null;
  const isStreaming = isLast && running;

  return (
    <article
      className={clsx("grid grid-cols-[minmax(0,1fr)] min-w-0 my-1 animate-roll-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="reasoning-head self-start inline-flex items-center gap-1.5 text-[12px] font-medium text-muted tracking-[-0.005em] hover:text-ink-soft transition-colors select-none"
        data-state={isStreaming ? "streaming" : "done"}
      >
        <Brain size={12} strokeWidth={1.7} />
        <span>{message.title || "Reasoning"}</span>
        <ChevronDown
          size={12}
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
              content={message.content}
              className="mt-2 pl-3.5 border-l-2 border-line text-[13px] leading-[1.6] text-muted italic break-words"
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
      className={clsx("grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 font-mono text-[12.5px] leading-[1.55] animate-roll-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="tool-line flex items-baseline gap-2 min-w-0" data-state={isRunning ? "running" : "done"}>
        <span className="text-faint shrink-0">↗</span>
        <Terminal size={12} strokeWidth={1.8} className="text-muted shrink-0 self-center" />
        <span className="text-ink-soft font-medium shrink-0">{message.title || "tool"}</span>
        <span className="text-muted truncate min-w-0 flex-1">{message.subtitle || ""}</span>
      </div>
      {!isRunning && (
        <pre className="tool-preview-fade m-0 mt-[3px] ml-[18px] text-faint font-mono text-[11.5px] leading-[1.5] whitespace-pre-wrap max-h-[80px] overflow-hidden">
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
      className={clsx("self-center grid grid-cols-[minmax(0,1fr)] animate-fade-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface-soft font-mono text-[11px] text-muted tracking-[-0.005em]">
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
      className={clsx("grid grid-cols-[minmax(0,1fr)] animate-fade-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <div className="px-3.5 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.18)] text-bad text-[13px] leading-[1.5] whitespace-pre-wrap break-words">
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
  const { items, label, done } = message.activity;

  // While the run is producing tools, show the rolling tail (last 3).
  // After it's done, switch to a static list with all items and let collapse
  // just animate the container height — switching modes mid-collapse caused
  // the items to swap out (43 → 3) before the height finished shrinking,
  // producing a visible flicker.
  const collapsed = done && !expanded;
  const max = done ? undefined : 3;

  return (
    <article
      className={clsx("grid grid-cols-[minmax(0,1fr)] my-1 animate-roll-in transition-[background-color,box-shadow] duration-300", sourceFocused && SOURCE_FOCUS_CLASS)}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <ActivityTrace>
        <ActivityHeader
          label={label}
          count={items.length}
          onToggle={done ? () => setExpanded((v) => !v) : undefined}
          expanded={expanded}
        />
        <ActivityTail items={items} max={max} collapsed={collapsed} />
      </ActivityTrace>
    </article>
  );
});
