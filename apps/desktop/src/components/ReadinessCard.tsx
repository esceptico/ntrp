import clsx from "clsx";
import { Badge } from "@/components/Badge";

interface ReadinessCardProps {
  tone: "ok" | "warn";
  label: string;
  detail: string;
  footnote?: string;
  className?: string;
}

export function ReadinessCard({ tone, label, detail, footnote, className }: ReadinessCardProps) {
  return (
    <section
      className={clsx(
        "surface-card px-3.5 py-3",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone} size="md">{label}</Badge>
        <div className="text-sm text-ink-soft">{detail}</div>
      </div>
      {footnote && <div className="mt-1.5 text-xs text-faint">{footnote}</div>}
    </section>
  );
}
