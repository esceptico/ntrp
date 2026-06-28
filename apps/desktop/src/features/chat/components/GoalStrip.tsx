import { CheckCircle2, Pause, Play, Target, Trash2 } from "lucide-react";
import { clearGoal, updateGoal } from "@/actions/goals";
import { useStore } from "@/stores";
import { ICON } from "@/lib/icons";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { Chip } from "@/components/ui/Chip";
import { IconButton } from "@/components/ui/IconButton";
import { HoverPopover } from "@/components/ui/HoverPopover";

export function GoalStatusBar() {
  const sessionId = useStore((s) => s.currentSessionId);
  const goal = useStore((s) => (sessionId ? s.goals[sessionId] : null));

  if (!goal) return null;

  const paused = goal.status === "paused";
  const complete = goal.status === "complete";

  return (
    <div className="relative flex items-center">
      <HoverPopover
        className="w-[360px] p-3"
        trigger={({ ref, toggle, hoverProps }) => (
          <Chip
            ref={ref}
            size="sm"
            tone="accent"
            variant="ghost"
            active={!complete}
            leading={<Target size={ICON.SM} strokeWidth={2} />}
            {...hoverProps}
            onClick={toggle}
            aria-label="Session goal"
            title={goal.objective}
            className="max-w-[220px]"
          >
            <span className="truncate">
              Goal · {goal.status.replace("_", " ")}
            </span>
          </Chip>
        )}
      >
        <div className="mb-2 flex items-center gap-2">
          <Target size={ICON.SM} strokeWidth={2} className="text-accent" />
          <span className="text-xs font-medium text-muted">Goal</span>
          <span className="ml-auto rounded-md border border-line-soft px-1.5 py-0.5 text-2xs text-muted">
            {goal.status.replace("_", " ")}
          </span>
        </div>
        <div className="scroll-thin max-h-36 overflow-auto text-sm text-ink-soft whitespace-pre-wrap">
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
              <BlurSwap swapKey={paused ? "play" : "pause"}>
                {paused ? <Play size={ICON.SM} /> : <Pause size={ICON.SM} />}
              </BlurSwap>
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
      </HoverPopover>
    </div>
  );
}

export function GoalStrip() {
  return <GoalStatusBar />;
}
