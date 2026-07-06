import { type AutomationTemplate } from "@/features/automations/lib/templates";
import { ICON } from "@/lib/icons";

export function TemplateCard({
  template,
  onPick,
}: {
  template: AutomationTemplate;
  onPick: () => void;
}) {
  const Icon = template.icon;
  return (
    <button
      type="button"
      onClick={onPick}
      className="surface-panel surface-radius-sm focus-ring-accent grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left transition-[scale] duration-check ease-out active:scale-[0.99]"
    >
      <Icon size={ICON.SM} strokeWidth={2} className="text-muted mt-[2px] shrink-0" />
      <div className="min-w-0 grid gap-1">
        <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
          {template.name}
        </h4>
        <p className="m-0 text-sm text-muted leading-[1.5] line-clamp-2">
          {template.blurb}
        </p>
      </div>
    </button>
  );
}
