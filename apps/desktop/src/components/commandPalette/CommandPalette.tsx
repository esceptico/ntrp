import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { useStore } from "../../store";
import { SPRING_POPOVER } from "../../lib/tokens/motion";
import { PaletteBody } from "./PaletteBody";
import type { Crumb } from "./types";

export function CommandPalette() {
  const open = useStore((s) => s.paletteOpen);
  const close = useStore((s) => s.closePalette);
  const togglePalette = useStore((s) => s.togglePalette);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  // Height-morph is disabled until the panel finishes animating in, so the
  // first content-height settle on open doesn't animate as a bump.
  const [morphReady, setMorphReady] = useState(false);

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
      setMorphReady(true);
    } else {
      setMorphReady(false);
    }
  }, [open]);

  const root = document.querySelector("#app");
  if (!root || !open) return null;

  // Open/close is intentionally instant — keyboard-frequency surface. The
  // only animation is the SPRING_POPOVER height morph as page content changes.
  return createPortal(
    <div
      className="modal-scrim absolute inset-0 z-[60] grid place-items-start justify-center pt-[14vh] p-8"
      onClick={close}
    >
      <motion.div
        layout={morphReady}
        className="surface-panel surface-radius-md w-[min(660px,calc(100vw-80px))] max-h-[62vh] grid grid-rows-[auto_minmax(0,1fr)] overflow-hidden origin-top"
        transition={{ layout: SPRING_POPOVER }}
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
          morph={morphReady}
        />
      </motion.div>
    </div>,
    root,
  );
}
