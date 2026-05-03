import { memo, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Brain, Check, ChevronDown, Copy, Pencil, Sparkles, Terminal } from "lucide-react";
import clsx from "clsx";
import { useStore, type UiMessage } from "../store";
import { renderMarkdown, escapeHtml } from "../markdown";
import { ActivityHeader, ActivityTail, ActivityTrace } from "./trace/ActivityTrace";
import { ApprovalCard } from "./ApprovalCard";
import type { SkillDescriptor } from "../api";

const EASE = [0.32, 0.72, 0, 1] as const;

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

function MessageActions({ id, role }: { id: string; role: "user" | "assistant" }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    const message = useStore.getState().messages.get(id);
    if (!message) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
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

  return (
    <div
      className={clsx(
        "flex gap-px h-6 mt-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150",
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
    </div>
  );
}

/** Match a leading `/skill-name` token in user content; return the skill
 *  descriptor + the remaining text (the user's actual prompt) if the token
 *  matches a known skill. Returns null otherwise. */
function detectSkillPrefix(
  content: string,
  skills: SkillDescriptor[],
): { skill: SkillDescriptor; rest: string } | null {
  if (!content.startsWith("/")) return null;
  const match = content.match(/^\/([\w-]+)\s*([\s\S]*)$/);
  if (!match) return null;
  const [, name, rest = ""] = match;
  const skill = skills.find((s) => s.name === name);
  if (!skill) return null;
  return { skill, rest: rest.trimStart() };
}

function SkillChip({ skill }: { skill: SkillDescriptor }) {
  const onClick = () => {
    if (!skill.path) return;
    void window.ntrpDesktop?.shell?.openPath(skill.path);
  };
  return (
    <button
      type="button"
      onClick={onClick}
      title={skill.path ?? skill.name}
      disabled={!skill.path}
      className={clsx(
        "inline-flex items-center gap-1.5 mt-1 px-2 py-1 rounded-md bg-surface-sunken/80 border border-line-soft",
        "text-[11.5px] font-medium text-ink-soft transition-colors",
        skill.path && "hover:bg-surface-soft hover:border-line cursor-pointer",
      )}
    >
      <Sparkles size={11} strokeWidth={2} className="text-accent" />
      <span className="capitalize">{skill.name.replace(/[_-]/g, " ")}</span>
    </button>
  );
}

const UserMessage = memo(function UserMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const skills = useStore((s) => s.skills);
  if (!message) return null;

  const skillMatch = useMemo(
    () => detectSkillPrefix(message.content, skills),
    [message.content, skills],
  );

  // When a skill prefix is detected, the bubble shows just the user's prompt
  // (the part after `/skill-name`) and the chip below identifies the skill.
  // If the user only typed `/skill-name` with no extra text, the chip stands
  // alone — no empty bubble.
  const visibleText = skillMatch ? skillMatch.rest : message.content;
  const showBubble = visibleText.trim().length > 0;

  return (
    <article className="group flex flex-col items-end animate-fade-in" data-id={id}>
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
  const html = useMemo(() => (message ? renderMarkdown(message.content) : ""), [message?.content]);
  if (!message) return null;
  return (
    <article className="group grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 animate-fade-in" data-id={id}>
      <div
        className="md py-0.5 text-[14px] leading-[1.62] text-ink tracking-[-0.005em] break-words"
        dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }}
      />
      {isFinal && <MessageActions id={id} role="assistant" />}
    </article>
  );
});

const ReasoningMessage = memo(function ReasoningMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const isLast = useIsLast(id);
  const running = useStore((s) => s.running);
  const html = useMemo(() => (message ? renderMarkdown(message.content) : ""), [message?.content]);
  const [expanded, setExpanded] = useState(false);
  if (!message) return null;
  const isStreaming = isLast && running;

  return (
    <article className="grid grid-cols-[minmax(0,1fr)] min-w-0 my-1 animate-roll-in" data-id={id}>
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
            transition={{ duration: 0.24, ease: EASE }}
            style={{ overflow: "hidden" }}
          >
            <div
              className="md mt-2 pl-3.5 border-l-2 border-line text-[13px] leading-[1.6] text-muted italic break-words"
              dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
});

const ToolMessage = memo(function ToolMessage({ id }: { id: string }) {
  const message = useMessage(id);
  if (!message) return null;
  const isRunning = !message.content;

  return (
    <article className="grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 font-mono text-[12.5px] leading-[1.55] animate-roll-in" data-id={id}>
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
  if (!message) return null;
  const text = message.title ? `${message.title} · ${message.content}` : message.content;
  return (
    <article className="self-center grid grid-cols-[minmax(0,1fr)] animate-fade-in" data-id={id}>
      <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface-soft font-mono text-[11px] text-muted tracking-[-0.005em]">
        {text}
      </div>
    </article>
  );
});

const ErrorMessage = memo(function ErrorMessage({ id }: { id: string }) {
  const message = useMessage(id);
  if (!message) return null;
  return (
    <article className="grid grid-cols-[minmax(0,1fr)] animate-fade-in" data-id={id}>
      <div
        className="px-3.5 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.18)] text-bad text-[13px] leading-[1.5] whitespace-pre-wrap break-words"
        dangerouslySetInnerHTML={{ __html: escapeHtml(message.content) }}
      />
    </article>
  );
});

const ActivityMessage = memo(function ActivityMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const [expanded, setExpanded] = useState(false);
  if (!message?.activity || message.activity.items.length === 0) return null;
  const { items, label, done } = message.activity;

  // While the run is producing tools, show the rolling tail (last 3).
  // After it's done, collapse by default; the user can click to expand and see the full list.
  const collapsed = done && !expanded;
  const max = done && expanded ? undefined : 3;

  return (
    <article className="grid grid-cols-[minmax(0,1fr)] my-1 animate-roll-in" data-id={id}>
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
