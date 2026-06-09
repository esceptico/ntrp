import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, SlidersHorizontal } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import type { SidebarGroupBy } from "../../store/types";
import { ICON } from "../../lib/icons";

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
  const popRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: 0, top: 0, ready: false });

  // Non-default view = surfaced on the trigger so the user knows a filter
  // is hiding sessions even when the popover is closed.
  const active = groupBy !== "project" || unreadOnly || channelsOnly;

  useEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    const el = popRef.current;
    if (!trigger || !el) return;
    const tr = trigger.getBoundingClientRect();
    const rect = el.getBoundingClientRect();
    const margin = 8;
    const left = Math.max(
      margin,
      Math.min(tr.right - rect.width, window.innerWidth - rect.width - margin),
    );
    const top = Math.max(margin, Math.min(tr.bottom + 4, window.innerHeight - rect.height - margin));
    setPos({ left, top, ready: true });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (popRef.current && !popRef.current.contains(t) && triggerRef.current && !triggerRef.current.contains(t)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const root = document.querySelector("#app");

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
      {open && root &&
        createPortal(
          <div
            ref={popRef}
            className="surface-panel surface-popover fixed z-50 w-[200px] py-1.5"
            style={{ left: pos.left, top: pos.top, opacity: pos.ready ? 1 : 0 }}
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
          </div>,
          root,
        )}
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-2.5 pt-1 pb-0.5 text-2xs font-medium uppercase tracking-[0.06em] text-faint select-none">
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
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1 text-left text-sm text-ink-soft hover:bg-surface-soft/60 hover:text-ink transition-colors"
    >
      <span className="grid place-items-center w-3.5 h-3.5 shrink-0 text-accent">
        {selected && <Check size={ICON.XS} strokeWidth={2.5} />}
      </span>
      <span className="truncate">{children}</span>
    </button>
  );
}
