import { useEffect, useRef } from "react";
import { ArrowUp, ShieldOff, ShieldCheck, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { sendMessage } from "../actions";

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

function formatCost(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}

function UsageDisplay() {
  const usage = useStore((s) => s.usage);
  if (!usage.lastPrompt && !usage.totalCost) return <span />;
  return (
    <span className="px-1.5 text-[11px] text-faint tabular-nums tracking-[-0.005em] select-none">
      {usage.lastPrompt > 0 && (
        <>
          <strong className="text-muted font-medium">{formatTokens(usage.lastPrompt)}</strong> ctx
        </>
      )}
      {usage.totalCost > 0 && (
        <>
          {usage.lastPrompt > 0 && " · "}
          {formatCost(usage.totalCost)}
        </>
      )}
    </span>
  );
}

function resize(input: HTMLTextAreaElement) {
  input.style.height = "0px";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
}

export function Composer() {
  const draft = useStore((s) => s.draft);
  const setDraft = useStore((s) => s.setDraft);
  const running = useStore((s) => s.running);
  const connected = useStore((s) => s.connected);
  const editingId = useStore((s) => s.editingId);
  const setEditingId = useStore((s) => s.setEditingId);
  const skipApprovals = useStore((s) => s.skipApprovals);
  const setSkipApprovals = useStore((s) => s.setSkipApprovals);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hasDraft = draft.trim().length > 0;
  const disabled = running || !connected || !hasDraft;

  useEffect(() => {
    if (inputRef.current) resize(inputRef.current);
  }, [draft]);

  function submit() {
    const text = draft;
    if (!text.trim()) return;
    setDraft("");
    if (inputRef.current) {
      inputRef.current.value = "";
      resize(inputRef.current);
    }
    void sendMessage(text);
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft("");
    if (inputRef.current) {
      inputRef.current.value = "";
      resize(inputRef.current);
    }
  }

  return (
    <div className="px-7 pb-[18px]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="composer-card max-w-[760px] mx-auto flex flex-col border border-line rounded-[14px] bg-surface focus-within:border-line-strong transition-colors"
      >
        {editingId && (
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-line-soft text-[11.5px] text-accent-strong bg-accent-soft/40 rounded-t-[14px]">
            <span>Editing previous message — pressing send will replace it.</span>
            <button
              type="button"
              onClick={cancelEdit}
              className="ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
              title="Cancel edit"
            >
              <X size={11} strokeWidth={2} />
              cancel
            </button>
          </div>
        )}
        <textarea
          ref={inputRef}
          id="message-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Message ntrp…"
          className="w-full min-h-[44px] max-h-[220px] resize-none border-0 bg-transparent px-4 pt-[13px] pb-1 text-[14px] leading-[1.5] text-ink outline-none tracking-[-0.005em] placeholder:text-whisper"
        />
        <div className="flex items-center gap-1.5 px-2 pt-1.5 pb-2">
          <button
            type="button"
            onClick={() => setSkipApprovals(!skipApprovals)}
            title={skipApprovals ? "Auto-approving every tool call. Click to require approval." : "Approvals required for sensitive tools. Click to enable YOLO."}
            className={clsx(
              "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-[11.5px] font-medium tracking-[-0.005em] transition-colors select-none",
              skipApprovals
                ? "bg-accent-soft text-accent-strong hover:bg-accent-soft/80"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            )}
          >
            {skipApprovals ? (
              <>
                <ShieldOff size={11} strokeWidth={2} />
                YOLO
              </>
            ) : (
              <>
                <ShieldCheck size={11} strokeWidth={2} />
                Approve
              </>
            )}
          </button>
          <UsageDisplay />
          <span className="flex-1" />
          <button
            type="submit"
            disabled={disabled}
            aria-label="Send"
            className="grid place-items-center w-7 h-7 rounded-full bg-ink text-on-ink shadow-[0_1px_2px_rgba(20,18,14,0.2)] hover:opacity-90 disabled:opacity-40 disabled:shadow-none transition-opacity"
          >
            <ArrowUp size={13} strokeWidth={2.4} />
          </button>
        </div>
      </form>
    </div>
  );
}
