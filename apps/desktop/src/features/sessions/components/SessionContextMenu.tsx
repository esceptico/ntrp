import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { Archive, FolderInput, Pencil, Pin, PinOff, Sparkles } from "lucide-react";
import type { Project } from "@/api/types";
import { EASE_OUT, MOTION, SPRING_POPOVER } from "@/lib/tokens/motion";
import { ICON } from "@/lib/icons";

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
  onMoveProject,
  onTogglePin,
  isPinned,
  projects,
}: {
  state: ContextMenuState | null;
  onClose: () => void;
  onRename: () => void;
  onCompact: () => void;
  onArchive: () => void;
  onMoveProject: (projectId: string | null) => void;
  onTogglePin: () => void;
  isPinned: boolean;
  projects: Project[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const [pos, setPos] = useState({ left: 0, top: 0, ready: false });

  // Snapshot the element that opened the menu (the session row) and return
  // focus to it on close — WAI-ARIA APG menu pattern.
  useEffect(() => {
    if (!state) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    return () => {
      const el = restoreRef.current;
      if (el && document.contains(el)) el.focus();
    };
  }, [state?.sessionId]);

  // Move focus into the menu once it's positioned so arrow keys work
  // immediately for keyboard users.
  useEffect(() => {
    if (!state || !pos.ready) return;
    ref.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, [state?.sessionId, pos.ready]);

  const onMenuKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    const items = Array.from(ref.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    if (items.length === 0) return;
    e.preventDefault();
    const idx = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === "Home" ? 0
      : e.key === "End" ? items.length - 1
      : e.key === "ArrowDown" ? (idx + 1) % items.length
      : (idx <= 0 ? items.length - 1 : idx - 1);
    items[next]?.focus();
  };

  // After mount, measure the menu and clamp to the viewport so it never
  // hangs off the right or bottom edge.
  useEffect(() => {
    if (!state) {
      setPos((p) => (p.ready ? { left: 0, top: 0, ready: false } : p));
      return;
    }
    const el = ref.current;
    if (!el) return;
    // offsetWidth/offsetHeight: layout box, unaffected by the in-flight
    // entrance transform (getBoundingClientRect would read the scaled size).
    const margin = 8;
    const left = Math.min(state.x, window.innerWidth - el.offsetWidth - margin);
    const top = Math.min(state.y, window.innerHeight - el.offsetHeight - margin);
    setPos({ left: Math.max(margin, left), top: Math.max(margin, top), ready: true });
  }, [state?.x, state?.y, state?.sessionId]);

  useEffect(() => {
    if (!state) return;
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
  }, [state, onClose]);

  const root = document.querySelector("#app");
  if (!root) return null;

  // Grow from the clamped anchor corner — if the menu was pushed left/up to
  // fit the viewport, the cursor sits at its right/bottom edge instead.
  const originX = state && pos.left < state.x ? "right" : "left";
  const originY = state && pos.top < state.y ? "bottom" : "top";

  return createPortal(
    <AnimatePresence>
      {state && (
        <motion.div
          key={state.sessionId}
          ref={ref}
          initial={{ opacity: 0, scale: 0.97, y: -4 }}
          animate={pos.ready ? { opacity: 1, scale: 1, y: 0 } : { opacity: 0, scale: 0.97, y: -4 }}
          exit={{ opacity: 0, scale: 0.97, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
          transition={SPRING_POPOVER}
          className="surface-panel surface-popover fixed z-[var(--z-popover)] w-[220px] py-1"
          style={{ left: pos.left, top: pos.top, transformOrigin: `${originY} ${originX}` }}
          onContextMenu={(e) => e.preventDefault()}
          role="menu"
          aria-label="Session actions"
          onKeyDown={onMenuKeyDown}
        >
          <ContextItem
            icon={isPinned ? <PinOff size={ICON.MD} strokeWidth={2} /> : <Pin size={ICON.MD} strokeWidth={2} />}
            label={isPinned ? "Unpin" : "Pin to top"}
            onClick={onTogglePin}
          />
          <ContextItem icon={<Pencil size={ICON.MD} strokeWidth={2} />} label="Rename…" onClick={onRename} />
          <ContextItem icon={<Sparkles size={ICON.MD} strokeWidth={2} />} label="Compact context" onClick={onCompact} />
          <ContextItem icon={<Archive size={ICON.MD} strokeWidth={2} />} label="Archive" onClick={onArchive} />
          <div className="my-1 h-px bg-line-soft" />
          <ContextItem icon={<FolderInput size={ICON.MD} strokeWidth={2} />} label="Move to Inbox" onClick={() => onMoveProject(null)} />
          {projects.map((project) => (
            <ContextItem
              key={project.project_id}
              icon={<FolderInput size={ICON.MD} strokeWidth={2} />}
              label={project.name}
              onClick={() => onMoveProject(project.project_id)}
            />
          ))}
        </motion.div>
      )}
    </AnimatePresence>,
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
      role="menuitem"
      tabIndex={-1}
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-sm text-ink-soft hover:bg-surface-soft/60 hover:text-ink focus-visible:bg-surface-soft/60 focus-visible:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.98]"
    >
      <span className="grid place-items-center w-3.5 h-3.5 shrink-0 text-faint">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  );
}
