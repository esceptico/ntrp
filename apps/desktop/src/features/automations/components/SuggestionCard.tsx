import { motion } from "motion/react";
import { X } from "lucide-react";
import {
  SPRING_LAYOUT,
  ROW_EXIT,
  EASE_OUT,
  MOTION,
} from "@/lib/tokens/motion";
import { dismissSuggestion } from "@/actions/automations";
import type { AutomationSuggestion } from "@/api/types";
import { formatTrigger } from "@/lib/agentRun";
import { suggestionIcon } from "@/features/automations/lib/automationFormat";
import { Badge } from "@/components/ui/Badge";
import { ICON } from "@/lib/icons";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import { ShowMore } from "@/components/ui/ShowMore";

export function SuggestionCard({
  suggestion,
  onPick,
  onDismiss = dismissSuggestion,
}: {
  suggestion: AutomationSuggestion;
  onPick: (suggestion: AutomationSuggestion) => void;
  onDismiss?: (id: string) => void;
}) {
  const Icon = suggestionIcon(suggestion.icon);
  const schedule = suggestion.triggers.map(formatTrigger).join(" · ") || "—";
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_LAYOUT}
      data-suggestion={suggestion.id}
      className="group/suggestion surface-panel surface-radius-sm relative grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left focus-within:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[scale] duration-check ease-out has-[button:active]:scale-[0.99]"
    >
      {/* Stretched accessible click target (see AutomationCard) — a real button
          over the card, below the dismiss control which is positioned above it. */}
      <button
        type="button"
        aria-label={`Use suggestion: ${suggestion.name}`}
        onClick={() => onPick(suggestion)}
        className="absolute inset-0 cursor-pointer rounded-[inherit] focus:outline-none"
      />
      <Icon size={ICON.SM} strokeWidth={2} className="text-muted mt-[2px] shrink-0" />
      <div className="relative z-[1] min-w-0 grid gap-1.5 pr-6">
        <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
          {suggestion.name}
        </h4>
        <ShowMore collapsedHeight={44} moreLabel="More" lessLabel="Less">
          <p className="m-0 text-sm text-muted leading-[1.5]">{suggestion.rationale}</p>
        </ShowMore>
        <Badge tone="neutral" className="font-mono tabular-nums" title={schedule}>
          {schedule}
        </Badge>
      </div>
      <Tooltip label="Dismiss">
        <IconButton
          size="sm"
          tone="faint"
          aria-label="Dismiss suggestion"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(suggestion.id);
          }}
          className="absolute top-2.5 right-2.5 z-[1] opacity-0 transition-[opacity,background-color,color,transform,scale] group-hover/suggestion:opacity-100 focus-visible:opacity-100 focus-visible:outline-none"
        >
          <X size={ICON.XS} strokeWidth={2} />
        </IconButton>
      </Tooltip>
    </motion.div>
  );
}
