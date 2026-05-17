import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Archive, Pencil, Sparkles } from "lucide-react";
import { ICON } from "../../lib/icons";

export interface ContextMenuState {
  sessionId: string;
  x: number;
  y: number;
}

export function SessionContextMenu({
  state,
  onClose,
  onRename,
  onCompact,
  onArchive,
}: {
  state: ContextMenuState;
  onClose: () => void;
  onRename: () => void;
  onCompact: () => void;
  onArchive: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: state.x, top: state.y, ready: false });

  // After mount, measure the menu and clamp to the viewport so it never
  // hangs off the right or bottom edge.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const margin = 8;
    const left = Math.min(state.x, window.innerWidth - rect.width - margin);
    const top = Math.min(state.y, window.innerHeight - rect.height - margin);
    setPos({ left: Math.max(margin, left), top: Math.max(margin, top), ready: true });
  }, [state.x, state.y]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onScroll = () => onClose();
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [onClose]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <div
      ref={ref}
      className="glass-surface glass-radius-sm fixed z-50 w-[160px] py-1"
      style={{ left: pos.left, top: pos.top, opacity: pos.ready ? 1 : 0 }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <ContextItem icon={<Pencil size={ICON.MD} strokeWidth={2} />} label="Rename" onClick={onRename} />
      <ContextItem icon={<Sparkles size={ICON.MD} strokeWidth={2} />} label="Compact context" onClick={onCompact} />
      <ContextItem icon={<Archive size={ICON.MD} strokeWidth={2} />} label="Archive" onClick={onArchive} />
    </div>,
    root,
  );
}

function ContextItem({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-sm text-ink-soft hover:bg-surface-soft/60 hover:text-ink transition-colors"
    >
      <span className="grid place-items-center w-3.5 h-3.5 shrink-0 text-faint">{icon}</span>
      {label}
    </button>
  );
}
