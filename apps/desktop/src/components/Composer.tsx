import { useEffect, useRef } from "react";
import { ArrowUp } from "lucide-react";
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
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hasDraft = draft.trim().length > 0;
  const disabled = running || !connected || !hasDraft;

  // Resize on every draft change (keeps up with edit-message-loaded value too).
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

  return (
    <div className="px-7 pb-[18px]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="composer-card max-w-[760px] mx-auto grid grid-rows-[minmax(0,auto)_auto] border border-line rounded-[14px] bg-surface focus-within:border-line-strong transition-colors"
      >
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
          <UsageDisplay />
          <span className="flex-1" />
          <button
            type="submit"
            disabled={disabled}
            aria-label="Send"
            className="grid place-items-center w-7 h-7 rounded-full bg-ink text-[#f6f5f2] shadow-[0_1px_2px_rgba(20,18,14,0.2)] hover:bg-black disabled:bg-whisper disabled:text-surface disabled:shadow-none transition-colors"
          >
            <ArrowUp size={13} strokeWidth={2.4} />
          </button>
        </div>
      </form>
    </div>
  );
}
