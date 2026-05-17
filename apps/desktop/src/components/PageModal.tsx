import { type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import { SPRING_SMOOTH } from "../lib/motion";
import { useEscapeKey } from "../lib/hooks";
import { IconButton } from "./IconButton";
import { ICON } from "../lib/icons";

const BACKDROP_DURATION = 0.2;
const EASE = [0.2, 0.8, 0.2, 1] as const;

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
  /** Optional rounded panel corner radius class (e.g. `"rounded-[14px]"`). */
  rounded?: string;
}

const DEFAULT_SIZE =
  "w-[min(960px,calc(100vw-32px))] h-[min(680px,calc(100vh-32px))] sm:w-[min(960px,calc(100vw-80px))] sm:h-[min(680px,calc(100vh-80px))]";
const DEFAULT_GRID = "grid-rows-[auto_minmax(0,1fr)]";
const DEFAULT_ROUNDED = "rounded-[14px]";

/** Standard portal+backdrop+panel modal shell used across Settings,
 *  Automations, Archive, Memory. Callers compose their own header / body
 *  inside `children`. Closes on backdrop click and Escape (unless
 *  `disableEscape` is set). */
export function PageModal({
  open,
  onClose,
  children,
  header,
  size = DEFAULT_SIZE,
  grid = DEFAULT_GRID,
  rounded = DEFAULT_ROUNDED,
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
          className="modal-scrim absolute inset-0 z-50 grid place-items-center p-4 sm:p-8 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: BACKDROP_DURATION, ease: EASE }}
          onClick={onClose}
        >
          <motion.div
            className={`glass-surface glass-radius-md ${size} grid ${grid} ${rounded} overflow-hidden`}
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={SPRING_SMOOTH}
            onClick={(e) => e.stopPropagation()}
          >
            {header && (
              <header className="flex items-start justify-between gap-3 px-5 pt-[18px] pb-3 border-b border-line-soft">
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
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}
