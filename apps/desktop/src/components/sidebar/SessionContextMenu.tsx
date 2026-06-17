import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { Archive, FolderInput, Pencil, Pin, PinOff, Sparkles } from "lucide-react";
import type { Project } from "../../api";
import { EASE_DECELERATE, MOTION, SPRING_POPOVER } from "../../lib/tokens/motion";
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
  onMoveProject,
  onTogglePin,
  isPinned,
  projects,
}: {
  state: ContextMenuState;
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
  const [pos, setPos] = useState({ left: state.x, top: state.y, ready: false });

  // After mount, measure the menu and clamp to the viewport so it never
  // hangs off the right or bottom edge.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // offsetWidth/offsetHeight: layout box, unaffected by the in-flight
    // entrance transform (getBoundingClientRect would read the scaled size).
    const margin = 8;
    const left = Math.min(state.x, window.innerWidth - el.offsetWidth - margin);
    const top = Math.min(state.y, window.innerHeight - el.offsetHeight - margin);
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

  // Grow from the clamped anchor corner — if the menu was pushed left/up to
  // fit the viewport, the cursor sits at its right/bottom edge instead.
  const originX = pos.left < state.x ? "right" : "left";
  const originY = pos.top < state.y ? "bottom" : "top";

  return createPortal(
    <motion.div
      ref={ref}
      initial="closed"
      animate={pos.ready ? "open" : "closed"}
      exit="closed"
      variants={{
        closed: { opacity: 0, scale: 0.97, y: -4 },
        open: { opacity: 1, scale: 1, y: 0, transition: { ...SPRING_POPOVER, staggerChildren: 0.035 } },
      }}
      transition={{ ...SPRING_POPOVER, when: "afterChildren" }}
      className="surface-panel surface-popover fixed z-50 w-[220px] py-1"
      style={{ left: pos.left, top: pos.top, transformOrigin: `${originY} ${originX}` }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <ContextItem
        icon={isPinned ? <PinOff size={ICON.MD} strokeWidth={2} /> : <Pin size={ICON.MD} strokeWidth={2} />}
        label={isPinned ? "Unpin" : "Pin to top"}
        onClick={onTogglePin}
      />
      <ContextItem icon={<Pencil size={ICON.MD} strokeWidth={2} />} label="Rename" onClick={onRename} />
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
    </motion.div>,
    root,
  );
}

const ITEM_VARIANTS = {
  closed: { opacity: 0, y: -4 },
  open: { opacity: 1, y: 0, transition: { duration: MOTION.row, ease: EASE_DECELERATE } },
};

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
    <motion.button
      type="button"
      variants={ITEM_VARIANTS}
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-sm text-ink-soft hover:bg-surface-soft/60 hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.98]"
    >
      <span className="grid place-items-center w-3.5 h-3.5 shrink-0 text-faint">{icon}</span>
      <span className="truncate">{label}</span>
    </motion.button>
  );
}
