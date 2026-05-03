import { memo, useMemo, useState } from "react";
import { Brain, Check, Copy, Pencil, Terminal } from "lucide-react";
import clsx from "clsx";
import { useStore, type UiMessage } from "../store";
import { renderMarkdown, escapeHtml } from "../markdown";

export function Message({ id }: { id: string }) {
  const role = useStore((s) => s.messages.get(id)?.role);
  if (!role) return null;
  switch (role) {
    case "user": return <UserMessage id={id} />;
    case "assistant": return <AssistantMessage id={id} />;
    case "reasoning": return <ReasoningMessage id={id} />;
    case "tool": return <ToolMessage id={id} />;
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

function MessageActions({ id, role }: { id: string; role: "user" | "assistant" | "reasoning" }) {
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
        "flex gap-px mt-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100",
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

const UserMessage = memo(function UserMessage({ id }: { id: string }) {
  const message = useMessage(id);
  if (!message) return null;
  return (
    <article className="group flex flex-col items-end animate-fade-in" data-id={id}>
      <div
        className="max-w-[75%] px-3.5 py-2 rounded-[18px] bg-surface-sunken text-ink text-[13.5px] leading-[1.5] whitespace-pre-wrap break-words text-left"
      >
        {message.content || " "}
      </div>
      <MessageActions id={id} role="user" />
    </article>
  );
});

const AssistantMessage = memo(function AssistantMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const html = useMemo(() => (message ? renderMarkdown(message.content) : ""), [message?.content]);
  if (!message) return null;
  return (
    <article className="group grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 animate-fade-in" data-id={id}>
      <div
        className="md py-0.5 text-[14px] leading-[1.62] text-ink tracking-[-0.005em] break-words"
        dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }}
      />
      <MessageActions id={id} role="assistant" />
    </article>
  );
});

const ReasoningMessage = memo(function ReasoningMessage({ id }: { id: string }) {
  const message = useMessage(id);
  const isLast = useIsLast(id);
  const running = useStore((s) => s.running);
  const html = useMemo(() => (message ? renderMarkdown(message.content) : ""), [message?.content]);
  if (!message) return null;
  const isStreaming = isLast && running;

  return (
    <article className="group grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 my-1 animate-roll-in" data-id={id}>
      <div
        className="reasoning-head inline-flex items-center gap-1.5 mb-1.5 text-[12px] font-medium text-muted tracking-[-0.005em]"
        data-state={isStreaming ? "streaming" : "done"}
      >
        <Brain size={12} strokeWidth={1.7} />
        <span>{message.title || "Reasoning"}</span>
      </div>
      <div
        className="md pl-3.5 border-l-2 border-line text-[13px] leading-[1.6] text-muted italic break-words"
        dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }}
      />
      <MessageActions id={id} role="reasoning" />
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
