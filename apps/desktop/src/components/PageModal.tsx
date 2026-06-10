import { type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import {
  ENTRY_PANEL,
  EASE_DECELERATE,
  EASE_OUT,
  MOTION,
  POSE_MODAL,
} from "../lib/tokens/motion";
import { useEscapeKey } from "../lib/hooks";
import { IconButton } from "./IconButton";
import { ICON } from "../lib/icons";

const BACKDROP_DURATION = MOTION.trace;

export interface PageModalHeader {
  /** Main title — usually a string but any node so callers can include
   *  count badges, icons, etc. */
  title: ReactNode;
  /** Optional second line under the title (small, faint, mono). Used by
   *  MarkdownViewer for source paths. */
  subtitle?: ReactNode;
  /** Extra buttons rendered to the left of the standard close X. */
  actions?: ReactNode;
}

export interface PageModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** When provided, PageModal renders a standard header bar with the title,
   *  optional subtitle, any extra actions, and a close X button. Callers
   *  with non-standard headers (e.g. Settings' sidebar layout) omit this
   *  and compose their own header inside `children`. */
  header?: PageModalHeader;
  /** Tailwind size class string for the panel — e.g.
   *  `"w-[min(960px,calc(100vw-80px))] h-[min(680px,calc(100vh-80px))]"`.
   *  Defaults to a 960×680 viewport-aware panel. */
  size?: string;
  /** Tailwind grid-template classes for the panel's internal layout.
   *  Defaults to a header + body split (`grid-rows-[auto_minmax(0,1fr)]`).
   *  Settings overrides this with a sidebar + content split. */
  grid?: string;
  /** When true, Escape no longer closes the modal. Useful when a nested
   *  modal owns the Escape key (e.g., automation editor inside the
   *  Automations modal). */
  disableEscape?: boolean;
}

const DEFAULT_SIZE =
  "w-[min(960px,calc(100vw-32px))] h-[min(680px,calc(100vh-32px))] sm:w-[min(960px,calc(100vw-80px))] sm:h-[min(680px,calc(100vh-80px))]";
const DEFAULT_GRID = "grid-rows-[auto_minmax(0,1fr)]";

/** Standard portal+backdrop+panel modal shell used across Settings,
 *  Automations, Archive, Memory. Callers compose their own header / body
 *  inside `children`. Closes on backdrop click and Escape (unless
 *  `disableEscape` is set). Corner radius comes from .surface-radius-md —
 *  callers cannot override (was the source of per-modal radius drift). */
export function PageModal({
  open,
  onClose,
  children,
  header,
  size = DEFAULT_SIZE,
  grid = DEFAULT_GRID,
  disableEscape,
}: PageModalProps) {
  useEscapeKey(onClose, open && !disableEscape);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="page-modal"
          className="modal-scrim absolute inset-0 z-50 grid place-items-center p-4 sm:p-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: BACKDROP_DURATION, ease: EASE_DECELERATE }}
          onClick={onClose}
        >
          <motion.div
            className={`surface-panel surface-radius-md ${size} grid ${grid} overflow-hidden`}
            initial={POSE_MODAL}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{
              opacity: 0,
              scale: 0.98,
              transition: { duration: MOTION.fast, ease: EASE_OUT },
            }}
            transition={ENTRY_PANEL}
            onClick={(e) => e.stopPropagation()}
          >
            {header && (
              <header className="flex items-start justify-between gap-3 px-5 pt-[18px] pb-3">
                <div className="min-w-0">
                  <div className="text-lg font-semibold tracking-[-0.012em] text-ink truncate">
                    {header.title}
                  </div>
                  {header.subtitle && (
                    <div className="mt-0.5 text-xs text-faint font-mono truncate">
                      {header.subtitle}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {header.actions}
                  <IconButton onClick={onClose} aria-label="Close">
                    <X size={ICON.SM} strokeWidth={2} />
                  </IconButton>
                </div>
              </header>
            )}
            {/* Keep structured header/body shells in one grid cell; callers
                with custom grids supply their own children directly. */}
            {header ? (
              <motion.div
                className="min-h-0 min-w-0 grid grid-rows-[minmax(0,1fr)]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{
                  duration: MOTION.palette,
                  ease: EASE_DECELERATE,
                }}
              >
                {children}
              </motion.div>
            ) : (
              children
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}
