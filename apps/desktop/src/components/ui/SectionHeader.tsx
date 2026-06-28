import clsx from "clsx";
import type { ReactNode } from "react";

interface SectionHeaderProps {
  label: string;
  count?: number;
  detail?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function SectionHeader({ label, count, detail, action, className }: SectionHeaderProps) {
  const hasRight = detail !== undefined || action !== undefined;
  return (
    <div className={clsx("flex items-center justify-between gap-2", className)}>
      <h3 className="m-0 text-xs font-medium uppercase tracking-[0.06em] text-muted">
        {label}
        {count !== undefined && <span className="ml-1 text-faint">({count})</span>}
      </h3>
      {hasRight && (
        <div className="ml-auto flex items-center gap-2">
          {detail !== undefined && <div className="text-xs text-faint">{detail}</div>}
          {action}
        </div>
      )}
    </div>
  );
}
