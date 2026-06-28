import type { ComponentType, ReactNode } from "react";
import { Inbox } from "lucide-react";
import clsx from "clsx";

type EmptyStateProps = {
  icon?: ComponentType<{ size?: number | string; strokeWidth?: number; className?: string }>;
  children: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
};

/** Designed empty/placeholder state: icon chip + conversational copy + an
 *  optional next action. Shared by both list and detail panes. */
export function EmptyState({ icon: Icon = Inbox, children, hint, action, className }: EmptyStateProps) {
  return (
    <div className={clsx("grid place-items-center px-6 text-center", className)}>
      <div className="flex max-w-[260px] flex-col items-center gap-3">
        <div className="grid size-12 place-items-center rounded-xl bg-surface-soft text-faint">
          <Icon size={22} strokeWidth={1.75} />
        </div>
        <div className="text-sm text-muted">{children}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
        {action && <div className="mt-1">{action}</div>}
      </div>
    </div>
  );
}

export function DetailPlaceholder({
  children,
  icon,
  hint,
  action,
}: {
  children: ReactNode;
  icon?: EmptyStateProps["icon"];
  hint?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <EmptyState icon={icon} hint={hint} action={action} className="h-full">
      {children}
    </EmptyState>
  );
}

export function Empty({
  children,
  icon,
  hint,
  action,
}: {
  children: ReactNode;
  icon?: EmptyStateProps["icon"];
  hint?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <EmptyState icon={icon} hint={hint} action={action} className="min-h-[200px]">
      {children}
    </EmptyState>
  );
}
