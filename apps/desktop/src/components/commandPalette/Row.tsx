import { ChevronRight } from "lucide-react";
import clsx from "clsx";
import { ICON } from "../../lib/icons";
import type { CommandEntry } from "./types";

export function Row({
  entry,
  active,
  activeRef,
  onHover,
  onClick,
}: {
  entry: CommandEntry;
  active: boolean;
  activeRef?: React.RefObject<HTMLButtonElement | null>;
  onHover: () => void;
  onClick: () => void;
}) {
  const Icon = entry.icon;
  return (
    <li>
      <button
        ref={activeRef}
        type="button"
        // `onMouseMove` (not `onMouseEnter`) so keyboard navigation
        // doesn't fight a stationary cursor — when arrow-scroll shifts
        // a row under the mouse, mouseenter would fire and reset the
        // active index back to whatever the cursor happens to cover,
        // making it feel like rows got "skipped". Mousemove only fires
        // on actual cursor motion, so hover takes over again the moment
        // the user touches the mouse.
        onMouseMove={onHover}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onClick}
        data-active={active ? "true" : undefined}
        className="app-row w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-[8px] text-ink-soft text-left"
      >
        <span
          className={clsx(
            "grid place-items-center w-5 h-5 rounded-md shrink-0 transition-colors",
            active ? "bg-accent-soft text-accent-strong" : "text-muted",
          )}
        >
          <Icon size={ICON.SM} strokeWidth={2} />
        </span>
        <span className="text-base text-ink truncate flex-1">{entry.label}</span>
        {entry.hint && (
          <span className="text-xs text-faint tabular-nums shrink-0">{entry.hint}</span>
        )}
        {entry.shortcut && (
          <kbd className="text-2xs text-faint font-mono shrink-0 ml-1">{entry.shortcut}</kbd>
        )}
        {entry.children && (
          <ChevronRight
            size={ICON.XS}
            strokeWidth={2}
            className="text-faint shrink-0 ml-1"
            aria-hidden
          />
        )}
      </button>
    </li>
  );
}
