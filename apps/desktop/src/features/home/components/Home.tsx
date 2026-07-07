import { useMemo } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Settings, Sparkles } from "lucide-react";
import type { SliceAsk, SliceSummary } from "@/api/slices";
import { useStore } from "@/stores";
import { useSlicesData } from "@/features/home/hooks/useSlicesData";
import { HeroInput } from "@/features/home/components/HeroInput";
import { FocusRow } from "@/features/home/components/FocusRow";
import { SlicesStrip } from "@/features/home/components/SlicesStrip";
import { Button } from "@/components/ui/Button";
import { ICON } from "@/lib/icons";
import { RISE_IN, RISE_SETTLED, MOTION, EASE_DECELERATE, originFromEvent } from "@/lib/tokens/motion";

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
  const openSettings = useStore((s) => s.openSettings);
  const focus = overview?.focus ?? NO_FOCUS;
  const slices = overview?.slices ?? NO_SLICES;
  const dateLabel = useMemo(() => new Date().toLocaleDateString(undefined, DATE_FORMAT), []);

  if (!connected) {
    // Mirrors the retired HomeHero's disconnected state: Home's hero input
    // is a dead end with no server behind it, so a connect CTA replaces it
    // entirely rather than showing an input that can't send.
    return (
      <motion.div
        initial={RISE_IN}
        animate={RISE_SETTLED}
        transition={{ duration: MOTION.trace, ease: EASE_DECELERATE }}
        className="mt-[14vh] mx-auto grid gap-5 justify-items-center text-center"
      >
        <span
          aria-hidden
          className="grid place-items-center w-12 h-12 rounded-2xl bg-accent-soft text-accent-strong"
        >
          <Sparkles size={ICON.HERO} strokeWidth={2} />
        </span>
        <div className="grid gap-1.5 max-w-[420px]">
          <h2 className="m-0 text-2xl font-semibold tracking-[-0.018em] text-ink">Connect to get started</h2>
          <p className="m-0 text-base text-muted leading-snug">Open settings to point ntrp at your server.</p>
        </div>
        <Button
          variant="secondary"
          size="md"
          leadingIcon={Settings}
          onClick={(e) => openSettings(originFromEvent(e.currentTarget), "connection")}
        >
          Open settings
        </Button>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={RISE_IN}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.trace, ease: EASE_DECELERATE }}
      className="h-full overflow-y-auto"
    >
      <div className="mx-auto grid w-[640px] max-w-full gap-7 px-4 pt-[16vh] pb-16">
      <div className="grid gap-3">
        <span className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{dateLabel}</span>
        <HeroInput />
      </div>
      <h2 className="m-0 text-[21px] font-medium tracking-[-0.01em] text-ink">{greeting(focus.length)}</h2>
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
      </div>
    </motion.div>
  );
}
