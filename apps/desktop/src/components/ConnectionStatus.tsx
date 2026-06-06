import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { useStore } from "../store";
import { MOTION, EASE_OUT } from "../lib/tokens/motion";

// Only the degraded phases surface a pill — when connected (or during the
// initial "connecting" handshake) the UI stays clean. "reconnecting" reads
// as a recoverable blip; "disconnected"/"failed" as offline.
const DEGRADED: Record<string, { text: string; tone: string; pulse: boolean }> = {
  reconnecting: { text: "Reconnecting…", tone: "bg-warn", pulse: true },
  disconnected: { text: "Offline", tone: "bg-bad", pulse: false },
  failed: { text: "Offline", tone: "bg-bad", pulse: false },
};

/**
 * Auto-hiding connection indicator. The server going quiet used to be
 * invisible; this surfaces the live SSE transport phase as a small pill at
 * the top of the window so a dropped/recovering connection is legible.
 */
export function ConnectionStatus() {
  const phase = useStore((s) => s.connectionPhase);
  const meta = DEGRADED[phase];

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed top-2 left-1/2 z-[70] -translate-x-1/2"
    >
      <AnimatePresence>
        {meta && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: MOTION.panel, ease: EASE_OUT }}
            className="surface-panel surface-radius-pill flex items-center gap-1.5 h-[26px] px-2.5 text-2xs font-medium text-soft"
          >
            <span
              aria-hidden
              className={clsx(
                "inline-block w-1.5 h-1.5 rounded-full",
                meta.tone,
                meta.pulse && "status-dot-breathe",
              )}
            />
            {meta.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
