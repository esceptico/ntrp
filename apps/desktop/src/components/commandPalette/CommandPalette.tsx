import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "../../store";
import { EASE_OUT } from "../../lib/motion";
import { PaletteBody } from "./PaletteBody";
import type { Crumb } from "./types";

const BACKDROP_DURATION = 0.16;
const PANEL_DURATION = 0.18;
const EASE = EASE_OUT;

export function CommandPalette() {
  const open = useStore((s) => s.paletteOpen);
  const close = useStore((s) => s.closePalette);
  const togglePalette = useStore((s) => s.togglePalette);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);

  // Global Cmd/Ctrl+K toggle + Esc close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        togglePalette();
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, togglePalette, close]);

  // Reset state on open.
  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      setCrumbs([]);
    }
  }, [open]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette"
          className="modal-scrim absolute inset-0 z-[60] grid place-items-start justify-center pt-[14vh] p-8 backdrop-blur-xl"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: BACKDROP_DURATION, ease: EASE }}
          onClick={close}
        >
          <motion.div
            className="glass-surface glass-radius-md w-[min(660px,calc(100vw-80px))] max-h-[62vh] grid grid-rows-[auto_minmax(0,1fr)] overflow-hidden origin-top"
            initial={{ opacity: 0, scale: 0.96, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -6 }}
            transition={{ duration: PANEL_DURATION, ease: EASE }}
            onClick={(e) => e.stopPropagation()}
          >
            <PaletteBody
              query={query}
              setQuery={setQuery}
              index={index}
              setIndex={setIndex}
              crumbs={crumbs}
              setCrumbs={setCrumbs}
              onClose={close}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}
