import { CheckCircle2, Pause, Play, Target, Trash2 } from "lucide-react";
import { clearGoal, updateGoal } from "../actions";
import { useStore } from "../store";
import { ICON } from "../lib/icons";

export function GoalStrip() {
  const sessionId = useStore((s) => s.currentSessionId);
  const goal = useStore((s) => (sessionId ? s.goals[sessionId] : null));
  if (!goal) return null;

  const paused = goal.status === "paused";
  const complete = goal.status === "complete";
  return (
    <div className="mx-4 -mb-3 rounded-t-[12px] rounded-b-[14px] border border-line border-b-0 bg-surface shadow-[var(--shadow-sm)]">
      <div className="flex items-center gap-2 min-w-0 px-3 pt-2 pb-5">
        <Target size={ICON.SM} strokeWidth={2} className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate text-sm text-ink-soft" title={goal.objective}>
          {goal.objective}
        </span>
        <span className="shrink-0 rounded-md border border-line-soft px-1.5 py-0.5 text-2xs text-muted">
          {goal.status.replace("_", " ")}
        </span>
        {!complete && (
          <button
            type="button"
            onClick={() => void updateGoal(paused ? "active" : "paused")}
            title={paused ? "Resume goal" : "Pause goal"}
            aria-label={paused ? "Resume goal" : "Pause goal"}
            className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors"
          >
            {paused ? <Play size={ICON.XS} /> : <Pause size={ICON.XS} />}
          </button>
        )}
        {!complete && (
          <button
            type="button"
            onClick={() => void updateGoal("complete")}
            title="Mark complete"
            aria-label="Mark complete"
            className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors"
          >
            <CheckCircle2 size={ICON.XS} />
          </button>
        )}
        <button
          type="button"
          onClick={() => void clearGoal()}
          title="Clear goal"
          aria-label="Clear goal"
          className="grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors"
        >
          <Trash2 size={ICON.XS} />
        </button>
      </div>
    </div>
  );
}
