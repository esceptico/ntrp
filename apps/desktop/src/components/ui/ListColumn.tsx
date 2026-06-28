import type { ComponentType, ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { ICON } from "@/lib/icons";
import { Button } from "@/components/ui/Button";
import { Empty } from "@/components/ui/EmptyState";

export function ListColumn<T>({
  toolbar,
  items,
  renderItem,
  loading,
  error,
  empty,
  emptyIcon,
  emptyAction,
  totalLabel,
  wrapItems,
  skeleton = false,
}: {
  toolbar: ReactNode;
  items: T[];
  renderItem: (item: T) => ReactNode;
  loading: boolean;
  error?: ReactNode;
  empty?: ReactNode;
  emptyIcon?: ComponentType<{ size?: number | string; strokeWidth?: number; className?: string }>;
  emptyAction?: ReactNode;
  totalLabel: string | null;
  wrapItems?: (children: ReactNode) => ReactNode;
  /** Render shimmer bars instead of a "Loading…" string while loading. */
  skeleton?: boolean;
}) {
  const mapped = items.map(renderItem);
  return (
    <>
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">{toolbar}</div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin scroll-fade-bottom px-2 pb-3">
        {loading ? (
          skeleton ? (
            <ListSkeleton />
          ) : (
            <div className="grid min-h-[200px] place-items-center text-sm text-muted">Loading…</div>
          )
        ) : error ? (
          <div className="px-1 py-3">{error}</div>
        ) : items.length === 0 ? (
          <Empty icon={emptyIcon} action={emptyAction}>
            {empty ?? "No matches."}
          </Empty>
        ) : (
          <ul className="flex flex-col gap-px">{wrapItems ? wrapItems(mapped) : mapped}</ul>
        )}
      </div>
      {totalLabel && (
        <div className="px-4 py-2 text-xs text-muted tabular-nums">{totalLabel}</div>
      )}
    </>
  );
}

/** Shimmer placeholder rows that mirror the file-tree row geometry. */
export function ListSkeleton() {
  return (
    <div className="flex flex-col gap-1.5 px-1 pt-1" aria-hidden>
      {Array.from({ length: 7 }).map((_, i) => (
        <div
          key={i}
          className="h-8 rounded-[10px] bg-surface-soft motion-safe:animate-pulse"
          style={{ width: `${72 - (i % 4) * 13}%` }}
        />
      ))}
    </div>
  );
}

export function ListError({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex gap-2.5 rounded-[10px] bg-bad-soft px-3 py-2.5">
      <AlertCircle size={ICON.SM} strokeWidth={2} className="mt-px shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-bad">{title}</div>
        <div className="mt-0.5 text-sm leading-[1.4] text-bad">{message}</div>
        {onRetry && (
          <Button variant="danger" size="sm" onClick={onRetry} className="mt-2">
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
