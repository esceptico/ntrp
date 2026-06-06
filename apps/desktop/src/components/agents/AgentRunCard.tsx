import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { ArrowUpRight, Bot, SendHorizontal, Square } from "lucide-react";
import { ICON } from "../../lib/icons";
import { EASE_EMPHASIZED, EASE_OUT, MOTION } from "../../lib/tokens/motion";
import {
  isActiveAgentStatus,
  type AgentRunStatus,
  type AgentRunView,
} from "../../lib/agentRun";
import { StatusDot } from "../StatusDot";

// One representation of a sub-agent run, in two sizes:
//   <AgentRunCard> — a distinct mini-card for the chat trace.
//   <AgentRunRow>  — a dense borderless row for the right-sidebar hub.
// Both share the glyph, the status dot, and the two-line meta/result body,
// so an agent reads as the same object wherever it appears.

interface AgentRunCardProps {
  run: AgentRunView;
  /** Open the agent's session. Omit to render a non-interactive card. */
  onOpen?: () => void;
  /** Cancel a running agent. Omit to hide the stop affordance. */
  onStop?: () => void;
  stopping?: boolean;
}

function glyphToneClass(status: AgentRunStatus): string {
  switch (status) {
    case "completed":
      return "bg-ok-soft text-ok";
    case "failed":
      return "bg-bad-soft text-bad";
    case "cancelled":
    case "interrupted":
      return "bg-surface-soft text-faint";
    default:
      return "bg-accent-soft text-accent-strong"; // running, cancel_requested
  }
}

function AgentGlyph({
  status,
  size,
  onStop,
  stopping,
}: {
  status: AgentRunStatus;
  size: number;
  onStop?: () => void;
  stopping?: boolean;
}) {
  const canStop = !!onStop && status === "running";
  const box = { width: size, height: size } as const;
  return (
    <span
      className="relative grid place-items-center shrink-0 self-center"
      style={box}
    >
      <span
        aria-hidden
        className={clsx(
          "grid place-items-center rounded-md transition-opacity",
          glyphToneClass(status),
          canStop && "group-hover/run:opacity-0",
        )}
        style={box}
      >
        <Bot size={ICON.XS} strokeWidth={2} />
      </span>
      {canStop && (
        <button
          type="button"
          aria-label="Stop agent"
          title="Stop agent"
          disabled={stopping}
          onClick={(event) => {
            event.stopPropagation();
            onStop?.();
          }}
          className="absolute inset-0 grid place-items-center rounded-md border-0 p-0 m-0 bg-surface-soft text-faint opacity-0 pointer-events-none transition-[opacity,color] group-hover/run:pointer-events-auto group-hover/run:opacity-100 hover:text-bad focus-visible:pointer-events-auto focus-visible:opacity-100 disabled:opacity-[0.6]"
        >
          <Square size={ICON.XS} strokeWidth={2} />
        </button>
      )}
    </span>
  );
}

function metaLine(run: AgentRunView): string {
  return [run.type, run.detached ? "detached" : null].filter(Boolean).join(" · ");
}

/** Inline chat mini-card — a distinct surface that reads as "an agent ran
 *  here", clickable to open the child session, stoppable while running. */
export function AgentRunCard({ run, onOpen, onStop, stopping }: AgentRunCardProps) {
  const running = isActiveAgentStatus(run.status);
  const meta = metaLine(run);
  const third = running ? run.progress : run.resultPreview;
  const interactive = !!onOpen;

  return (
    <div
      className={clsx(
        "group/run w-full rounded-[10px] surface-card px-2.5 py-2 text-left",
        interactive && "cursor-pointer",
      )}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onOpen}
      onKeyDown={
        interactive
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onOpen?.();
              }
            }
          : undefined
      }
      title={run.name}
      aria-label={interactive ? `Open agent session: ${run.name}` : undefined}
      data-child-session-id={run.childSessionId}
    >
      <div className="flex items-center gap-2 min-w-0">
        <AgentGlyph status={run.status} size={18} onStop={onStop} stopping={stopping} />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
          {run.name}
        </span>
        <StatusDot status={run.status} pulse={running} />
        {run.elapsedLabel && (
          <span className="shrink-0 text-2xs tabular-nums text-faint">{run.elapsedLabel}</span>
        )}
        {interactive && (
          <ArrowUpRight
            size={ICON.XS}
            strokeWidth={2}
            className="shrink-0 text-faint opacity-0 -ml-1 transition-opacity group-hover/run:opacity-100"
            aria-hidden
          />
        )}
      </div>
      {(meta || third) && (
        <div className="mt-1 pl-[26px] min-w-0 space-y-0.5">
          {meta && <div className="truncate text-xs text-faint">{meta}</div>}
          {third && (
            <div className={clsx("truncate text-xs text-muted", running && "italic")}>
              {third}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Dense sidebar row — same object, no card chrome (the panel is the surface).
 *  `active` marks the agent whose session you're currently viewing. */
export function AgentRunRow({
  run,
  onOpen,
  onStop,
  stopping,
  active,
  onSend,
}: AgentRunCardProps & { active?: boolean; onSend?: (message: string) => void | Promise<void> }) {
  const running = isActiveAgentStatus(run.status);
  const meta = metaLine(run);
  const third = running ? run.progress : run.resultPreview;
  const canSend = running && !!onSend;
  const [composing, setComposing] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  // Await the send so a failure (e.g. the agent finished between render and
  // send → 404) keeps the draft + composer instead of silently eating it.
  const submit = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await onSend?.(text);
      setDraft("");
      setComposing(false);
    } catch {
      /* keep draft + composer open so the message isn't lost */
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      data-active={active || undefined}
      className={clsx(
        "group/run py-1",
        active && "app-row rounded-lg -mx-1.5 px-1.5",
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <AgentGlyph status={run.status} size={16} onStop={onStop} stopping={stopping} />
        {onOpen ? (
          <button
            type="button"
            onClick={onOpen}
            title="Open agent session"
            data-child-session-id={run.childSessionId}
            className={clsx(
              "min-w-0 flex-1 truncate border-0 bg-transparent p-0 text-left text-sm tracking-[-0.005em]",
              active ? "text-ink" : "text-ink-soft hover:text-ink",
            )}
          >
            {run.name}
          </button>
        ) : (
          <span className="min-w-0 flex-1 truncate text-sm text-ink-soft tracking-[-0.005em]">
            {run.name}
          </span>
        )}
        {canSend && (
          <button
            type="button"
            onClick={() => setComposing((v) => !v)}
            aria-label="Send a message to this agent"
            title="Send a message to this agent"
            className={clsx(
              "shrink-0 grid place-items-center w-4 h-4 rounded text-faint transition-opacity hover:text-ink",
              composing ? "opacity-100 text-ink" : "opacity-0 group-hover/run:opacity-100",
            )}
          >
            <SendHorizontal size={ICON.XS} strokeWidth={2} />
          </button>
        )}
        <StatusDot status={run.status} pulse={running} />
        {run.elapsedLabel && (
          <span className="shrink-0 text-2xs tabular-nums text-faint">{run.elapsedLabel}</span>
        )}
      </div>
      {(meta || third) && (
        <div className="pl-[24px] min-w-0">
          {meta && <div className="truncate text-2xs text-faint">{meta}</div>}
          {third &&
            (running ? (
              <div className="truncate text-2xs text-muted italic">{third}</div>
            ) : (
              <motion.div
                key={third}
                initial={{ opacity: 0, y: 2 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: MOTION.row, ease: EASE_OUT }}
                className="truncate text-2xs text-muted"
              >
                {third}
              </motion.div>
            ))}
        </div>
      )}
      <AnimatePresence initial={false}>
        {composing && (
          <motion.div
            key="composer"
            initial={{ gridTemplateRows: "0fr", opacity: 0 }}
            animate={{ gridTemplateRows: "1fr", opacity: 1 }}
            exit={{ gridTemplateRows: "0fr", opacity: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
            style={{ display: "grid" }}
          >
            <div className="min-h-0 overflow-hidden">
              <div className="mt-1.5 pl-[24px]">
              <input
                autoFocus
                value={draft}
                disabled={sending}
                aria-label="Message this agent"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void submit();
                  } else if (event.key === "Escape") {
                    event.preventDefault();
                    setComposing(false);
                    setDraft("");
                  }
                }}
                onBlur={() => {
                  if (!draft.trim()) setComposing(false);
                }}
                placeholder="Message this agent…"
                spellCheck={false}
                className="w-full h-7 px-2 rounded-md bg-surface-soft focus:bg-surface-sunken text-xs text-ink-soft placeholder:text-muted outline-none border border-transparent focus:border-line-soft transition-colors disabled:opacity-60"
              />
            </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
