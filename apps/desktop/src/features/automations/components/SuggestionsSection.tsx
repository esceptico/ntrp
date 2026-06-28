import { useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  RISE_IN,
  RISE_SETTLED,
  EASE_DECELERATE,
  MOTION,
} from "@/lib/tokens/motion";
import { dismissSuggestion } from "@/actions/automations";
import type { AutomationSuggestion } from "@/api/types";
import { SuggestionCard } from "@/features/automations/components/SuggestionCard";

/** Server-synthesized, contextual automation cards rendered above the
 *  static templates. Renders nothing when there are no active suggestions
 *  so cold-start shows only the static templates. */
export function SuggestionsSection({
  suggestions,
  onPick,
  onDismiss = dismissSuggestion,
}: {
  suggestions: AutomationSuggestion[] | null;
  onPick: (suggestion: AutomationSuggestion) => void;
  onDismiss?: (id: string) => void;
}) {
  // Suggestions resolve async after the templates paint. Rise the section in
  // only when it arrives late — on tab revisits the data is already loaded
  // and the section mounts statically with the rest of the panel.
  const arrivedLate = useRef(!suggestions || suggestions.length === 0);
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <motion.section
      initial={arrivedLate.current ? RISE_IN : false}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.panel, ease: EASE_DECELERATE }}
      className="grid gap-2"
    >
      <h3 className="m-0 text-xs font-medium uppercase tracking-[0.08em] text-muted">
        Suggested for you
      </h3>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
        <AnimatePresence mode="popLayout" initial={false}>
          {suggestions.map((suggestion) => (
            <SuggestionCard
              key={suggestion.id}
              suggestion={suggestion}
              onPick={onPick}
              onDismiss={onDismiss}
            />
          ))}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}
