import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { EASE_OUT, MOTION } from "@/lib/tokens/motion";

type SaveState = "idle" | "saving" | "saved";

interface SaveButtonProps {
  onSave: () => void | Promise<void>;
  idleLabel?: string;
  savingLabel?: string;
  savedLabel?: string;
  tone?: "accent" | "ink";
  disabled?: boolean;
  className?: string;
}

const SAVED_HOLD_MS = 1500;

/** A 3/4 arc that spins — reads as indeterminate progress. */
function Spinner() {
  return (
    <motion.svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, ease: "linear", duration: 0.7 }}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" strokeOpacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </motion.svg>
  );
}

/** Checkmark that draws itself in on mount. */
function DrawCheck() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <motion.path
        d="M5 13l4 4L19 7"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.3, ease: EASE_OUT }}
      />
    </svg>
  );
}

/**
 * Save with state morph: idle → saving (spinning arc) → saved (a checkmark
 * that draws itself in), then auto-reverts. The label slides up/in on each
 * transition rather than hard-cutting — the whole content block is one
 * `AnimatePresence` so icon + word move together.
 */
export function SaveButton({
  onSave,
  idleLabel = "Save",
  savingLabel = "Saving",
  savedLabel = "Saved",
  tone = "accent",
  disabled,
  className,
}: SaveButtonProps) {
  const [state, setState] = useState<SaveState>("idle");
  const mounted = useRef(true);
  const revertTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    return () => {
      mounted.current = false;
      clearTimeout(revertTimer.current);
    };
  }, []);

  const handleClick = async () => {
    if (state === "saving") return;
    setState("saving");
    try {
      await onSave();
      if (!mounted.current) return;
      setState("saved");
      revertTimer.current = setTimeout(() => {
        if (mounted.current) setState("idle");
      }, SAVED_HOLD_MS);
    } catch {
      if (mounted.current) setState("idle");
    }
  };

  const label = state === "saving" ? savingLabel : state === "saved" ? savedLabel : idleLabel;

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || state === "saving"}
      aria-busy={state === "saving"}
      className={clsx(
        "relative inline-flex items-center justify-center h-8 px-3.5 rounded-[9px] text-sm font-medium text-on-ink overflow-hidden",
        tone === "ink" ? "bg-ink hover:bg-ink/90" : "bg-accent hover:bg-accent/90",
        "disabled:opacity-45 transition-[background-color,opacity] duration-check ease-out active:scale-[0.98]",
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={state}
          className="inline-flex items-center gap-1.5 whitespace-nowrap"
          initial={{ opacity: 0, y: 7 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -7 }}
          transition={{ duration: MOTION.fast, ease: EASE_OUT }}
        >
          {state === "saving" && <Spinner />}
          {state === "saved" && <DrawCheck />}
          {label}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
