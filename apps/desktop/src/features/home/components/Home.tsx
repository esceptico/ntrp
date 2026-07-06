import { useMemo } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { SliceAsk, SliceSummary } from "@/api/slices";
import { useStore } from "@/stores";
import { useSlicesData } from "@/features/home/hooks/useSlicesData";
import { HeroInput } from "@/features/home/components/HeroInput";
import { FocusRow } from "@/features/home/components/FocusRow";
import { SlicesStrip } from "@/features/home/components/SlicesStrip";
import { RISE_IN, RISE_SETTLED, MOTION, EASE_DECELERATE } from "@/lib/tokens/motion";

const DATE_FORMAT: Intl.DateTimeFormatOptions = {
  weekday: "long",
  month: "long",
  day: "numeric",
};

// Stable references for "not loaded yet" fallbacks — see HeroInput's
// NO_SLICES/NO_AUTOMATIONS for why an inline `?? []` is unsafe with zustand.
const NO_FOCUS: SliceAsk[] = [];
const NO_SLICES: SliceSummary[] = [];

function greeting(focusCount: number): string {
  if (focusCount === 0) return "All clear.";
  if (focusCount === 1) return "One thing needs you.";
  return `${focusCount} things need you.`;
}

/** Home entrypoint: centered 640px column, nothing else on the screen.
 *  date line → hero input (the composer, promoted) → greeting stating the
 *  focus count → FOCUS rows → SLICES strip. Replaces HomeHero as the empty-
 *  state surface Chat.tsx renders when the current session has no visible
 *  messages and nothing is running. */
export function Home() {
  const { overview } = useSlicesData();
  const connected = useStore((s) => s.connected);
  const focus = overview?.focus ?? NO_FOCUS;
  const slices = overview?.slices ?? NO_SLICES;
  const dateLabel = useMemo(() => new Date().toLocaleDateString(undefined, DATE_FORMAT), []);

  return (
    <motion.div
      initial={RISE_IN}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.trace, ease: EASE_DECELERATE }}
      className="mx-auto mt-[12vh] grid w-[640px] max-w-full gap-6 px-4"
    >
      <span className="text-[11px] font-medium tracking-wide text-faint uppercase">{dateLabel}</span>
      <HeroInput />
      {connected && (
        <>
          <p className="m-0 text-lg text-ink-soft">{greeting(focus.length)}</p>
          {focus.length > 0 && (
            <div className="grid gap-2">
              <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Focus</span>
              <div className="grid gap-1.5">
                <AnimatePresence initial={false}>
                  {focus.map((ask) => (
                    <FocusRow key={ask.id} ask={ask} />
                  ))}
                </AnimatePresence>
              </div>
            </div>
          )}
          <SlicesStrip slices={slices} />
        </>
      )}
    </motion.div>
  );
}
