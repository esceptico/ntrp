import { useRef, useState } from "react";
import { Check, SlidersHorizontal } from "lucide-react";
import clsx from "clsx";
import { useStore } from "@/stores";
import type { SidebarGroupBy } from "@/stores/types";
import { ICON } from "@/lib/icons";
import { MenuItem } from "@/components/ui/MenuItem";
import { AnchoredPopover } from "@/components/ui/AnchoredPopover";

const GROUP_OPTIONS: { value: SidebarGroupBy; label: string }[] = [
  { value: "project", label: "Project" },
  { value: "time", label: "Time" },
  { value: "type", label: "Type" },
  { value: "status", label: "Status" },
];

export function SidebarFilters() {
  const groupBy = useStore((s) => s.prefs.sidebarGroupBy);
  const unreadOnly = useStore((s) => s.prefs.sidebarUnreadOnly);
  const channelsOnly = useStore((s) => s.prefs.sidebarChannelsOnly);
  const setPref = useStore((s) => s.setPref);

  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Non-default view = surfaced on the trigger so the user knows a filter
  // is hiding sessions even when the popover is closed.
  const active = groupBy !== "project" || unreadOnly || channelsOnly;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Filter and group sessions"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Filter & group"
        className={clsx(
          "grid place-items-center w-[26px] h-[22px] rounded-[5px] transition-colors",
          active || open
            ? "text-ink bg-surface-soft/80"
            : "text-faint hover:text-ink hover:bg-surface-soft/70",
        )}
      >
        <SlidersHorizontal size={ICON.SM} strokeWidth={2} />
      </button>
      <AnchoredPopover
        open={open}
        onClose={() => setOpen(false)}
        anchor={triggerRef}
        proximity
        className="w-[200px] py-1.5"
      >
        <SectionLabel>Group by</SectionLabel>
        {GROUP_OPTIONS.map((opt) => (
          <PopRow
            key={opt.value}
            selected={groupBy === opt.value}
            onClick={() => setPref("sidebarGroupBy", opt.value)}
          >
            {opt.label}
          </PopRow>
        ))}
        <div className="my-1 h-px bg-line-soft" />
        <SectionLabel>Filter</SectionLabel>
        <PopRow selected={unreadOnly} onClick={() => setPref("sidebarUnreadOnly", !unreadOnly)}>
          Unread only
        </PopRow>
        <PopRow selected={channelsOnly} onClick={() => setPref("sidebarChannelsOnly", !channelsOnly)}>
          Channels only
        </PopRow>
      </AnchoredPopover>
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-2.5 pt-1 pb-0.5 text-2xs font-medium uppercase tracking-[0.06em] text-muted select-none">
      {children}
    </div>
  );
}

function PopRow({
  children,
  selected,
  onClick,
}: {
  children: React.ReactNode;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <MenuItem
      dense
      onClick={onClick}
      leading={selected && <Check size={ICON.XS} strokeWidth={2.5} className="text-accent" />}
    >
      {children}
    </MenuItem>
  );
}
