import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { Repeat2, X } from "lucide-react";
import { useStore, type ServerLoop } from "../../store";
import { refreshLoops, stopLoop } from "../../actions";
import { useEscapeKey, useFocusTrap } from "../../lib/hooks";
import { ICON } from "../../lib/icons";
import { EASE_DECELERATE, EASE_OUT, ENTRY_PANEL, MOTION, POSE_MODAL } from "../../lib/tokens/motion";
import { formatLoopCountdown } from "../../lib/loops";
import { Chip } from "../Chip";
import { IconButton } from "../IconButton";
import { Markdown } from "../Markdown";
import { RollingToken } from "../trace/RollingToken";
import { HoverPopover } from "../ui/HoverPopover";

/** Per-character odometer aligned to the RIGHT so the unit suffix
 *  ("s"/"m"/"h"/"d") sits at a stable slot and only digits that
 *  actually differ between renders roll. Slot keys are right-anchored
 *  ("r0", "r1", …) so "12s" → "9s" drops slot "r2" (the leading "1")
 *  without disturbing "r0"=s / "r1"=2→9. AnimatePresence at the row
 *  gives the dropped slot a clean exit instead of a hard unmount. */
function RollingDigits({ value }: { value: string }) {
  const chars = Array.from(value);
  const slots = chars.map((ch, i) => ({ key: `r${chars.length - 1 - i}`, ch }));
  return (
    <span className="inline-flex items-baseline tabular-nums whitespace-nowrap">
      {slots.map(({ key, ch }) => (
        <RollingToken key={key} value={ch} mono />
      ))}
    </span>
  );
}

/** Composer-toolbar pill that summarizes active loops for the current
 *  session. Hover reveals a portaled popover listing each loop with
 *  countdown + a stop button; clicking a loop opens a detail modal with
 *  the full prompt. Hidden when the session has no enabled loops. */
export function LoopStatusBar() {
  const sessionId = useStore((s) => s.currentSessionId);
  const allLoops = useStore((s) => s.loops);
  const loops = useMemo(
    () =>
      allLoops
        .filter((loop) => loop.session_id === sessionId && loop.enabled)
        .sort((a, b) => {
          const aT = a.next_run_at ? Date.parse(a.next_run_at) : Infinity;
          const bT = b.next_run_at ? Date.parse(b.next_run_at) : Infinity;
          return aT - bT;
        }),
    [allLoops, sessionId],
  );
  const [now, setNow] = useState(Date.now());
  // Click on a loop entry opens a detail modal with the full prompt.
  // null = no modal open. Stored by task_id so the panel auto-closes
  // when the loop is stopped or completes.
  const [openLoopId, setOpenLoopId] = useState<string | null>(null);
  const openLoop = openLoopId ? loops.find((l) => l.task_id === openLoopId) ?? null : null;
  const setOpenLoop = (loop: ServerLoop) => setOpenLoopId(loop.task_id);

  // Two intervals: refresh server state every 3s, tick the local clock
  // every 1s so countdowns under a minute display live seconds without
  // pounding the API.
  useEffect(() => {
    if (!sessionId) return;
    void refreshLoops(sessionId);
    const tickId = window.setInterval(() => setNow(Date.now()), 1_000);
    const refreshId = window.setInterval(() => {
      void refreshLoops(sessionId);
    }, 3_000);
    return () => {
      window.clearInterval(tickId);
      window.clearInterval(refreshId);
    };
  }, [sessionId]);

  if (loops.length === 0) return null;

  const next = loops[0];
  const nextRunMs = next.next_run_at ? Date.parse(next.next_run_at) : Number.POSITIVE_INFINITY;
  const countdown = formatLoopCountdown(nextRunMs, now);

  return (
    <div className="relative flex items-center">
      <HoverPopover
        className="w-[360px] p-3"
        trigger={({ ref, hoverProps }) => (
          <Chip
            ref={ref}
            size="sm"
            tone="neutral"
            variant="ghost"
            leading={<Repeat2 size={ICON.SM} strokeWidth={2} />}
            {...hoverProps}
            aria-label="Active loops"
          >
            {loops.length === 1 ? (
              <>
                <span className="composer-loop-label">Loop · </span>
                <RollingDigits value={countdown} />
              </>
            ) : (
              <>
                <span className="composer-loop-label">Loops · {loops.length} · next </span>
                <RollingDigits value={countdown} />
              </>
            )}
          </Chip>
        )}
      >
        <div className="mb-2 px-1 text-xs font-medium text-muted">Active loops</div>
        <div className="space-y-1">
          {loops.map((loop) => {
            const runAt = loop.next_run_at ? Date.parse(loop.next_run_at) : Number.POSITIVE_INFINITY;
            return (
              <div key={loop.task_id} className="flex items-start gap-2 rounded-lg px-1.5 py-1.5">
                <button
                  type="button"
                  onClick={() => void stopLoop(loop.task_id)}
                  title="Stop loop"
                  aria-label="Stop loop"
                  className="mt-[2px] grid h-5 w-5 shrink-0 place-items-center rounded-md text-faint hover:bg-surface-soft hover:text-ink transition-[color,background-color,scale] duration-check ease-out active:scale-[0.92]"
                >
                  <X size={ICON.SM} strokeWidth={2} />
                </button>
                <button
                  type="button"
                  onClick={() => setOpenLoop(loop)}
                  className="min-w-0 text-left -my-1.5 -mr-1.5 py-1.5 pr-1.5 rounded-md hover:bg-surface-soft transition-colors"
                  title="Show full prompt"
                >
                  <div className="truncate text-sm text-ink-soft">{loop.prompt}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    Every {loop.every} · next in <RollingDigits value={formatLoopCountdown(runAt, now)} />
                    {loop.max_iterations
                      ? ` · ${loop.iteration_count}/${loop.max_iterations}`
                      : loop.iteration_count > 0
                        ? ` · iter ${loop.iteration_count}`
                        : ""}
                  </div>
                </button>
              </div>
            );
          })}
        </div>
      </HoverPopover>
      <LoopDetailModal loop={openLoop} onClose={() => setOpenLoopId(null)} />
    </div>
  );
}

function LoopDetailModal({ loop, onClose }: { loop: ServerLoop | null; onClose: () => void }) {
  useEscapeKey(onClose, !!loop);
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(panelRef, !!loop);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {loop && (
        <motion.div
          key="loop-detail"
          className="modal-scrim fixed inset-0 z-50 grid place-items-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: MOTION.trace, ease: EASE_DECELERATE }}
          onClick={onClose}
        >
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Loop detail"
            tabIndex={-1}
            className="surface-panel surface-radius-md w-[min(560px,calc(100vw-32px))] max-h-[min(640px,calc(100vh-32px))] grid grid-rows-[auto_minmax(0,1fr)_auto] focus:outline-none"
            initial={POSE_MODAL}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
            transition={ENTRY_PANEL}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 px-4 py-3 border-b border-line">
              <Repeat2 size={ICON.SM} strokeWidth={2} className="text-muted" />
              <div className="text-sm font-medium text-ink">Loop</div>
              <div className="ml-auto text-xs text-muted">
                Every {loop.every} · next in {formatLoopCountdown(loop.next_run_at ? Date.parse(loop.next_run_at) : Number.POSITIVE_INFINITY)}
              </div>
              <IconButton size="sm" tone="faint" onClick={onClose} aria-label="Close">
                <X size={ICON.SM} strokeWidth={2} />
              </IconButton>
            </div>
            <div className="scroll-thin overflow-y-auto px-4 py-3">
              <Markdown content={loop.prompt} className="text-sm text-ink-soft" />
            </div>
            <div className="px-4 py-2 border-t border-line text-xs text-muted flex flex-wrap gap-x-3 gap-y-1">
              {loop.max_iterations ? <span>iter {loop.iteration_count}/{loop.max_iterations}</span> : loop.iteration_count > 0 ? <span>iter {loop.iteration_count}</span> : null}
              {loop.max_age_days ? <span>expires after {loop.max_age_days}d</span> : null}
              {loop.stop_when ? <span>stops when: {loop.stop_when}</span> : null}
              <span className="ml-auto font-mono text-2xs">{loop.task_id}</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}
