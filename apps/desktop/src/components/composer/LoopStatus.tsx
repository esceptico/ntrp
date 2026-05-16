import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Repeat2, X } from "lucide-react";
import { useStore, type ServerLoop } from "../../store";
import { refreshLoops, stopLoop } from "../../actions";
import { useEscapeKey } from "../../lib/hooks";
import { ICON } from "../../lib/icons";
import { formatLoopCountdown } from "../../lib/loops";
import { Markdown } from "../Markdown";
import { RollingToken } from "../trace/RollingToken";

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

  // Hover popover is portaled to document.body so it can use a real
  // `backdrop-filter` — otherwise the composer form's own glass
  // backdrop-filter would neutralize the child's blur (see
  // `feedback_backdrop_filter_containing_block.md`). Open state is
  // hover-bridged: button hover shows; popover hover keeps it open;
  // either leaving hides after a brief delay so the user can move the
  // cursor across the gap.
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ bottom: number; left: number } | null>(null);
  const hideTimerRef = useRef<number | null>(null);
  const show = useCallback(() => {
    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    setOpen(true);
  }, []);
  const scheduleHide = useCallback(() => {
    if (hideTimerRef.current) window.clearTimeout(hideTimerRef.current);
    hideTimerRef.current = window.setTimeout(() => setOpen(false), 80);
  }, []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect();
      setCoords({ bottom: window.innerHeight - r.top + 8, left: r.left });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  if (loops.length === 0) return null;

  const next = loops[0];
  const nextRunMs = next.next_run_at ? Date.parse(next.next_run_at) : Number.POSITIVE_INFINITY;
  const countdown = formatLoopCountdown(nextRunMs, now);

  return (
    <div className="relative flex items-center">
      <button
        ref={triggerRef}
        type="button"
        onMouseEnter={show}
        onMouseLeave={scheduleHide}
        onFocus={show}
        onBlur={scheduleHide}
        className="inline-flex h-7 items-center gap-1.5 rounded-full px-2 text-xs font-medium text-muted hover:bg-surface-soft hover:text-ink transition-colors"
        aria-label="Active loops"
      >
        <Repeat2 size={ICON.SM} strokeWidth={2} />
        {loops.length === 1 ? (
          <>Loop · <RollingDigits value={countdown} /></>
        ) : (
          <>Loops · {loops.length} · next <RollingDigits value={countdown} /></>
        )}
      </button>
      {open && coords && createPortal(
        <div
          ref={popoverRef}
          onMouseEnter={show}
          onMouseLeave={scheduleHide}
          style={{ position: "fixed", bottom: coords.bottom, left: coords.left, zIndex: 60 }}
          className="glass-surface glass-heavy glass-radius-md w-[360px] rounded-[14px] p-3"
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
                    className="mt-[2px] grid h-5 w-5 shrink-0 place-items-center rounded-md text-faint hover:bg-surface-soft hover:text-ink transition-colors"
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
                    <div className="mt-0.5 text-xs text-faint">
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
        </div>,
        document.body
      )}
      <LoopDetailModal loop={openLoop} onClose={() => setOpenLoopId(null)} />
    </div>
  );
}

function LoopDetailModal({ loop, onClose }: { loop: ServerLoop | null; onClose: () => void }) {
  useEscapeKey(onClose, !!loop);

  if (!loop) return null;
  const nextRunMs = loop.next_run_at ? Date.parse(loop.next_run_at) : Number.POSITIVE_INFINITY;
  const root = document.querySelector("#app");
  if (!root) return null;

  const detail = (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/30 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Loop detail"
        className="glass-surface glass-heavy glass-radius-md w-[min(560px,calc(100vw-32px))] max-h-[min(640px,calc(100vh-32px))] grid grid-rows-[auto_minmax(0,1fr)_auto] rounded-[14px]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-line">
          <Repeat2 size={ICON.SM} strokeWidth={2} className="text-muted" />
          <div className="text-sm font-medium text-ink">Loop</div>
          <div className="ml-auto text-xs text-faint">
            Every {loop.every} · next in {formatLoopCountdown(nextRunMs)}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-6 w-6 place-items-center rounded-md text-faint hover:bg-surface-soft hover:text-ink transition-colors"
          >
            <X size={ICON.SM} strokeWidth={2} />
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-3">
          <Markdown content={loop.prompt} className="text-sm text-ink-soft" />
        </div>
        <div className="px-4 py-2 border-t border-line text-xs text-faint flex flex-wrap gap-x-3 gap-y-1">
          {loop.max_iterations ? <span>iter {loop.iteration_count}/{loop.max_iterations}</span> : loop.iteration_count > 0 ? <span>iter {loop.iteration_count}</span> : null}
          {loop.max_age_days ? <span>expires after {loop.max_age_days}d</span> : null}
          {loop.stop_when ? <span>stops when: {loop.stop_when}</span> : null}
          <span className="ml-auto font-mono text-[11px]">{loop.task_id}</span>
        </div>
      </div>
    </div>
  );
  return createPortal(detail, root);
}
