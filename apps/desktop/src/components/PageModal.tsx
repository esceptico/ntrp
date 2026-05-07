import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";

const BACKDROP_DURATION = 0.2;
const PANEL_DURATION = 0.22;
const EASE = [0.2, 0.8, 0.2, 1] as const;

export interface PageModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
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
  size = DEFAULT_SIZE,
  grid = DEFAULT_GRID,
  rounded = DEFAULT_ROUNDED,
  disableEscape,
}: PageModalProps) {
  useEffect(() => {
    if (!open || disableEscape) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, disableEscape, onClose]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="page-modal"
          className="absolute inset-0 z-50 grid place-items-center p-4 sm:p-8 bg-[rgba(0,0,0,0.32)] backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: BACKDROP_DURATION, ease: EASE }}
          onClick={onClose}
        >
          <motion.div
            className={`${size} grid ${grid} ${rounded} bg-surface shadow-[var(--shadow-pop)] overflow-hidden border border-line-soft`}
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={{ duration: PANEL_DURATION, ease: EASE }}
            onClick={(e) => e.stopPropagation()}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}
