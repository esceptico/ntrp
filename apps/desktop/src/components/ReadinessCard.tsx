import clsx from "clsx";

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
        "rounded-[12px] border border-line-soft bg-surface-soft/45 px-3.5 py-3",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={clsx(
            "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
            tone === "ok" ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn",
          )}
        >
          {label}
        </span>
        <div className="text-sm text-ink-soft">{detail}</div>
      </div>
      {footnote && <div className="mt-1.5 text-xs text-faint">{footnote}</div>}
    </section>
  );
}
