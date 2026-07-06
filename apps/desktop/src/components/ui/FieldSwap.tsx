import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Three-phase single-element swap (transitions.dev 04), ported verbatim
 * from ~/src/interaction-lab's InstrumentRuler study: exit the old state →
 * swap the content while invisible → enter the new state. The two states
 * never overlap, so nothing can ghost regardless of what the field
 * contains. `dir` signs the travel (+1/-1 = directional list traversal,
 * 0 = instant swap, no phases — e.g. a fresh open with no prior context).
 *
 * Distinct from BlurSwap: BlurSwap crossfades two states that overlap
 * mid-transition (spatial content, e.g. icon swaps) via AnimatePresence
 * sync mode. FieldSwap never overlaps old/new — it's for in-place text/
 * field states (labels, readouts) where the old and new must not blur
 * into each other. Both legitimately coexist; pick by whether the content
 * should bridge (BlurSwap) or hard-cut through invisibility (FieldSwap).
 *
 * Tuned values kept verbatim from the lab source: --duration-quick
 * (150ms fallback) ease-in-out; exit translateY(dir·-4px) blur(2px)
 * opacity 0; enter from translateY(dir·4px); force reflow with
 * `void el.offsetWidth` between phases 2 and 3 so the jump-then-release
 * doesn't get coalesced into one animation frame.
 */

const SWAP_TRANSITION =
  "transform var(--duration-quick) ease-in-out, filter var(--duration-quick) ease-in-out, opacity var(--duration-quick) ease-in-out";

const readMs = (name: string, fallback: number) => {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(v) ? v : fallback;
};

export function FieldSwap({
  swapKey,
  dir,
  children,
}: {
  swapKey: string;
  dir: number;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [shown, setShown] = useState(() => ({ k: swapKey, node: children }));
  const latest = useRef({ k: swapKey, node: children });
  latest.current = { k: swapKey, node: children };

  useEffect(() => {
    if (swapKey === shown.k) return;
    const el = ref.current;
    if (!el) return;
    if (dir === 0 || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(latest.current);
      return;
    }
    const dur = readMs("--duration-quick", 150);
    // Phase 1: exit the old state.
    el.style.transition = SWAP_TRANSITION;
    el.style.transform = `translateY(${dir * -4}px)`;
    el.style.filter = "blur(2px)";
    el.style.opacity = "0";
    const t = setTimeout(() => {
      // Phase 2: swap the content while invisible.
      setShown(latest.current);
      // Phase 3: jump below (no transition), then release to animate in.
      el.style.transition = "none";
      el.style.transform = `translateY(${dir * 4}px)`;
      void el.offsetWidth;
      el.style.transition = SWAP_TRANSITION;
      el.style.transform = "translateY(0)";
      el.style.filter = "blur(0px)";
      el.style.opacity = "1";
    }, dur);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [swapKey]);

  // Live children while at rest (interactive content keeps working); the
  // frozen snapshot only exists while the OLD state animates out.
  return (
    <div ref={ref} className="will-change-[transform,filter,opacity]">
      {shown.k === swapKey ? children : shown.node}
    </div>
  );
}
