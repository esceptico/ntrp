import { ChevronRight } from "lucide-react";
import clsx from "clsx";
import { ICON } from "@/lib/icons";
import { PickerRow } from "@/components/PickerRow";
import type { CommandEntry } from "@/components/commandPalette/types";

export function Row({
  entry,
  active,
  activeRef,
  optionId,
  onHover,
  onClick,
}: {
  entry: CommandEntry;
  active: boolean;
  activeRef?: React.RefObject<HTMLButtonElement | null>;
  optionId?: string;
  onHover: () => void;
  onClick: () => void;
}) {
  const Icon = entry.icon;
  return (
    <li role="presentation">
      <PickerRow
        ref={activeRef}
        active={active}
        id={optionId}
        role="option"
        aria-selected={active}
        onMouseMove={onHover}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onClick}
        className="app-row flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-ink-soft"
      >
        <span
          className={clsx(
            "grid place-items-center w-5 h-5 rounded-md shrink-0 transition-colors duration-check ease-out",
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
      </PickerRow>
    </li>
  );
}
