import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, Pause, Play, Target, Trash2 } from "lucide-react";
import { clearGoal, updateGoal } from "../actions";
import { useStore } from "../store";
import { ICON } from "../lib/icons";
import { Chip } from "./Chip";
import { IconButton } from "./IconButton";

export function GoalStatusBar() {
  const sessionId = useStore((s) => s.currentSessionId);
  const goal = useStore((s) => (sessionId ? s.goals[sessionId] : null));
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ bottom: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect();
      setCoords({
        bottom: Math.max(8, window.innerHeight - r.top + 8),
        left: Math.max(8, r.left),
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  if (!goal) return null;

  const cancelHide = () => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  };
  const show = () => {
    cancelHide();
    setOpen(true);
  };
  const scheduleHide = () => {
    cancelHide();
    hideTimerRef.current = window.setTimeout(() => setOpen(false), 120);
  };
  const paused = goal.status === "paused";
  const complete = goal.status === "complete";

  return (
    <div className="relative flex items-center">
      <Chip
        ref={triggerRef}
        size="sm"
        tone="accent"
        variant="ghost"
        active={!complete}
        leading={<Target size={ICON.SM} strokeWidth={2} />}
        onMouseEnter={show}
        onMouseLeave={scheduleHide}
        onFocus={show}
        onBlur={scheduleHide}
        onClick={() => setOpen((v) => !v)}
        aria-label="Session goal"
        title={goal.objective}
        className="max-w-[220px]"
      >
        <span className="truncate">
          Goal · {goal.status.replace("_", " ")}
        </span>
      </Chip>
      {open && coords && createPortal(
        <div
          ref={popoverRef}
          onMouseEnter={show}
          onMouseLeave={scheduleHide}
          style={{ position: "fixed", bottom: coords.bottom, left: coords.left, zIndex: 60 }}
          className="surface-panel surface-popover w-[360px] p-3"
        >
          <div className="mb-2 flex items-center gap-2">
            <Target size={ICON.SM} strokeWidth={2} className="text-accent" />
            <span className="text-xs font-medium text-muted">Goal</span>
            <span className="ml-auto rounded-md border border-line-soft px-1.5 py-0.5 text-2xs text-muted">
              {goal.status.replace("_", " ")}
            </span>
          </div>
          <div className="max-h-36 overflow-auto text-sm text-ink-soft whitespace-pre-wrap">
            {goal.objective}
          </div>
          <div className="mt-3 flex items-center gap-1">
            {!complete && (
              <IconButton
                tone="faint"
                onClick={() => void updateGoal(paused ? "active" : "paused")}
                title={paused ? "Resume goal" : "Pause goal"}
                aria-label={paused ? "Resume goal" : "Pause goal"}
              >
                {paused ? <Play size={ICON.SM} /> : <Pause size={ICON.SM} />}
              </IconButton>
            )}
            {!complete && (
              <IconButton
                tone="faint"
                onClick={() => void updateGoal("complete")}
                title="Mark complete"
                aria-label="Mark complete"
              >
                <CheckCircle2 size={ICON.SM} />
              </IconButton>
            )}
            <IconButton
              tone="faint"
              className="ml-auto"
              onClick={() => void clearGoal()}
              title="Clear goal"
              aria-label="Clear goal"
            >
              <Trash2 size={ICON.SM} />
            </IconButton>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

export function GoalStrip() {
  return <GoalStatusBar />;
}
