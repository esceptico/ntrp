import { X } from "lucide-react";
import { dismissSuggestion } from "@/actions/automations";
import type { AutomationSuggestion } from "@/api/types";
import { formatTrigger } from "@/lib/agentRun";
import { suggestionIcon } from "@/features/automations/lib/automationFormat";
import { Badge } from "@/components/ui/Badge";
import { ICON } from "@/lib/icons";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import { ShowMore } from "@/components/ui/ShowMore";
import { SurfaceCard } from "@/components/ui/SurfaceCard";

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
    <SurfaceCard
      interactive
      onClick={() => onPick(suggestion)}
      ariaLabel={`Use suggestion: ${suggestion.name}`}
      data-suggestion={suggestion.id}
      className="group/suggestion grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left"
    >
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
    </SurfaceCard>
  );
}
