import { useEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles } from "lucide-react";
import clsx from "clsx";
import { ICON } from "../lib/icons";
import { useThemeEffect } from "../lib/theme";

/** Spotlight-style floating composer rendered in the quick-capture
 *  window (separate Electron BrowserWindow loaded with the
 *  `#quick-capture` hash). The window is frameless + transparent so
 *  this component owns the entire visible UI.
 *
 *  Flow: user types → Enter → IPC `quick:submit` → main process forwards
 *  to the main window's renderer, which calls createSession + sendMessage
 *  via its existing actions. The quick window then hides itself; the
 *  main window comes to front showing the new session.
 *
 *  Why route through the main window: createSession/sendMessage rely on
 *  the Zustand store, SSE subscription, route hash, etc. — all wired in
 *  the main App. Duplicating that in the quick window would be a
 *  second implementation we'd then have to keep in sync.  */
export function QuickCapture() {
  // Drives the .dark / .palette-<id> classes on <html> from the user's
  // prefs (same store the main window reads). Without this the quick
  // window is stuck in the light theme regardless of what the user
  // picked in Settings.
  useThemeEffect();

  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Always focus the input when the window appears. Electron re-shows
  // the same window across summons (we never destroy it), so React doesn't
  // remount — but the input may have lost focus on blur. Force it back.
  useEffect(() => {
    const focus = () => inputRef.current?.focus();
    focus();
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, []);

  async function onSubmit() {
    const trimmed = text.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    try {
      await window.ntrpDesktop?.quickCapture?.submit(trimmed);
      setText("");
    } finally {
      setSubmitting(false);
    }
  }

  function onClose() {
    void window.ntrpDesktop?.quickCapture?.close();
  }

  const disabled = !text.trim() || submitting;

  return (
    // Tiny padding just so the card's drop shadow has room to render
    // inside the transparent BrowserWindow. The card itself IS the
    // visible surface — no outer frame, no vibrancy layer.
    <div className="quick-capture-root grid place-items-stretch min-h-screen p-1.5">
      <div className="quick-capture-card flex items-center gap-2.5 rounded-[12px] px-3.5">
        <span
          aria-hidden
          className="grid place-items-center w-5 h-5 text-accent shrink-0"
        >
          <Sparkles size={ICON.MD} strokeWidth={1.8} />
        </span>
        <input
          ref={inputRef}
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void onSubmit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            }
          }}
          placeholder="What can I help you with today?"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="off"
          className="flex-1 min-w-0 bg-transparent border-0 outline-none text-[15px] text-ink placeholder:text-faint tracking-[-0.005em]"
        />
        <button
          type="button"
          onClick={() => void onSubmit()}
          disabled={disabled}
          aria-label="Send"
          className={clsx(
            "grid place-items-center w-6 h-6 rounded-md shrink-0 transition-all",
            disabled
              ? "text-faint"
              : "bg-ink text-on-ink hover:opacity-90 active:scale-[0.94]",
          )}
        >
          <ArrowUp size={ICON.SM} strokeWidth={2.4} />
        </button>
      </div>
    </div>
  );
}
