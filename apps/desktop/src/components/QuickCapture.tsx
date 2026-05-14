import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
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
  // `present` drives AnimatePresence — when it flips false we play an
  // exit animation, and only fire the IPC dismiss (submit or close) once
  // the animation completes. This is what keeps the card from vanishing
  // mid-flick: the Electron `quick:submit` handler hides the window
  // immediately, so we have to animate BEFORE the IPC, not after.
  const [present, setPresent] = useState(true);
  // Encodes the intent behind the exit so we can play the right motion
  // and fire the matching IPC in onExitComplete. submit = decisive flick
  // upward (intent sent); close = settle in place (intent withdrawn).
  type ExitReason = "submit" | "close" | null;
  const [exitReason, setExitReason] = useState<ExitReason>(null);
  // Held during the exit animation so we can fire submit with the
  // exact text the user typed, even if state has already cleared.
  const pendingSubmit = useRef<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Each summon: re-present the card so AnimatePresence replays the
  // entry. The window persists across summons (we never destroy it),
  // so React doesn't remount on its own — we hook into window.focus
  // (fired every time Electron `win.show()` brings us forward) as the
  // per-summon signal.
  useEffect(() => {
    const onFocus = () => {
      setPresent(true);
      setExitReason(null);
      pendingSubmit.current = null;
      setText("");
      setSubmitting(false);
      // Defer focus to next frame — the focus event fires before the
      // motion.div has remounted from a prior exit.
      requestAnimationFrame(() => inputRef.current?.focus());
    };
    onFocus();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const onSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || submitting) return;
    pendingSubmit.current = trimmed;
    setSubmitting(true);
    setExitReason("submit");
    setPresent(false);
  }, [text, submitting]);

  const onClose = useCallback(() => {
    if (!present) return;
    setExitReason("close");
    setPresent(false);
  }, [present]);

  const onExitComplete = useCallback(async () => {
    if (exitReason === "submit" && pendingSubmit.current) {
      const msg = pendingSubmit.current;
      pendingSubmit.current = null;
      await window.ntrpDesktop?.quickCapture?.submit(msg);
    } else if (exitReason === "close") {
      void window.ntrpDesktop?.quickCapture?.close();
    }
  }, [exitReason]);

  const disabled = !text.trim() || submitting;

  return (
    // Tiny padding just so the card's drop shadow has room to render
    // inside the transparent BrowserWindow. The card itself IS the
    // visible surface — no outer frame, no vibrancy layer.
    <div className="quick-capture-root grid place-items-stretch min-h-screen p-1.5">
      <AnimatePresence onExitComplete={onExitComplete}>
        {present && (
          <motion.div
            key="card"
            initial={{ y: -16, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            // Entry uses a spring — the card "arrives" with a subtle
            // settle. Exit uses a tighter ease-out — leaving should feel
            // decisive, not bouncy. Direction encodes intent: submit
            // flicks upward (sent), close fades in place (withdrawn).
            exit={
              exitReason === "submit"
                ? {
                    y: -10,
                    opacity: 0,
                    scale: 0.97,
                    transition: { duration: 0.14, ease: [0.4, 0, 1, 1] },
                  }
                : {
                    y: 0,
                    opacity: 0,
                    scale: 0.96,
                    transition: { duration: 0.11, ease: [0.4, 0, 1, 1] },
                  }
            }
            transition={{
              type: "spring",
              stiffness: 520,
              damping: 36,
              mass: 0.7,
              opacity: { duration: 0.16, ease: [0.22, 1, 0.36, 1] },
            }}
            style={{ willChange: "transform, opacity" }}
            className="quick-capture-card flex items-center gap-2.5 rounded-[12px] px-3.5"
          >
            <span
              aria-hidden
              className="grid place-items-center w-5 h-5 text-accent shrink-0"
            >
              <Sparkles size={ICON.MD} strokeWidth={2} />
            </span>
            <input
              ref={inputRef}
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit();
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
              onClick={onSubmit}
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
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
