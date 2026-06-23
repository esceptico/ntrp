import type { ButtonHTMLAttributes, ComponentType, Ref, ReactNode } from "react";
import { AlertCircle, Inbox, Loader2, Search, X } from "lucide-react";
import clsx from "clsx";
import { ICON } from "../../lib/icons";
import { ScrollFadeTop } from "../ScrollBlur";
import { Badge, type BadgeTone } from "../Badge";

// ─── Display helpers ──────────────────────────────────────────────────

/** Relative-time string for a freshness / recency stamp. Null-safe. */
export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.round(d / 30);
  if (mo < 12) return `${mo}mo ago`;
  return `${Math.round(mo / 12)}y ago`;
}

// ─── Pane / list / detail shells ──────────────────────────────────────

export function PaneShell({
  list,
  detail,
  /** Fixed 280px list column with a hard divider (file-tree layout) instead
   *  of the default resizable minmax(280,360). */
  fixedList = false,
  /** Skip the detail-pane scroll container — the caller owns its own scroll
   *  (e.g. DetailShell, which already scrolls its body). */
  scrollDetail = true,
}: {
  list: ReactNode;
  detail: ReactNode;
  fixedList?: boolean;
  scrollDetail?: boolean;
}) {
  return (
    <div
      className={clsx(
        "grid h-full",
        fixedList ? "grid-cols-[280px_minmax(0,1fr)]" : "grid-cols-[minmax(280px,360px)_minmax(0,1fr)]",
      )}
    >
      <div className={clsx("flex flex-col min-h-0", fixedList && "border-r border-line-soft")}>{list}</div>
      {scrollDetail ? (
        <div className="min-h-0 overflow-y-auto scroll-thin">
          <ScrollFadeTop />
          {detail}
        </div>
      ) : (
        <div className="min-h-0">{detail}</div>
      )}
    </div>
  );
}

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
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex h-7 items-center rounded-[10px] px-2.5 text-sm font-medium text-bad transition-colors hover:bg-bad/10"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function DetailShell({
  header,
  body,
  meta,
  actions,
}: {
  header: ReactNode;
  body: ReactNode;
  meta: ReactNode;
  actions: ReactNode;
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-7 pt-6 pb-3">{header}</div>
      <div className="flex-1 min-h-0 px-7 overflow-y-auto scroll-thin">
        <ScrollFadeTop />
        {body}
        <div className="mt-7 mb-6">{meta}</div>
      </div>
      <div className="flex items-center justify-end gap-2 px-7 py-3">{actions}</div>
    </div>
  );
}

export function DetailMeta({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center flex-wrap gap-2 text-xs text-faint">{children}</div>
  );
}

export function Sep() {
  return (
    <span aria-hidden className="text-line">
      ·
    </span>
  );
}

// ─── Metadata grid ────────────────────────────────────────────────────

export interface MetaGridRow {
  label: string;
  value: string;
  mono?: boolean;
}

export function MetaGrid({ rows }: { rows: (MetaGridRow | null | false)[] }) {
  const present = rows.filter(Boolean) as MetaGridRow[];
  return (
    <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-y-2.5 text-sm">
      {present.map((row) => (
        <MetaRow key={row.label} row={row} />
      ))}
    </dl>
  );
}

function MetaRow({ row }: { row: MetaGridRow }) {
  return (
    <>
      <dt className="text-muted">{row.label}</dt>
      <dd
        className={clsx(
          "text-ink-soft min-w-0 tabular-nums",
          row.mono && "font-mono text-xs break-all whitespace-pre-wrap",
        )}
      >
        {row.value}
      </dd>
    </>
  );
}

type EmptyStateProps = {
  icon?: ComponentType<{ size?: number | string; strokeWidth?: number; className?: string }>;
  children: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
};

/** Designed empty/placeholder state: icon chip + conversational copy + an
 *  optional next action. Shared by both list and detail panes. */
function EmptyState({ icon: Icon = Inbox, children, hint, action, className }: EmptyStateProps) {
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

export function ErrorPill({ message }: { message: string }) {
  return (
    <Badge tone="bad" size="md" shape="rounded" outline title={message} className="mr-auto max-w-[60%] truncate">
      {message}
    </Badge>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <Badge tone={tone} size="md" shape="rounded" outline>
      {children}
    </Badge>
  );
}

// ─── Buttons ──────────────────────────────────────────────────────────

export function PrimaryBtn({
  children,
  onClick,
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center h-7 px-3 rounded-[10px] bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45] disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}

export function GhostBtn({
  children,
  onClick,
  disabled,
  ...buttonProps
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type" | "onClick" | "disabled" | "className">) {
  return (
    <button
      {...buttonProps}
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[10px] text-sm text-ink-soft hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
    >
      {children}
    </button>
  );
}

export function DangerBtn({
  children,
  onClick,
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[10px] text-sm text-ink-soft hover:bg-bad-soft hover:text-bad transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
    >
      {children}
    </button>
  );
}

// ─── Toolbar ──────────────────────────────────────────────────────────

export function SearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel = placeholder,
  autoFocus = false,
  busy = false,
  inputRef,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  ariaLabel?: string;
  autoFocus?: boolean;
  busy?: boolean;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const Icon = busy ? Loader2 : Search;
  return (
    <div className="relative flex-1 min-w-0">
      <Icon
        size={ICON.XS}
        strokeWidth={2}
        className={clsx(
          "absolute left-2.5 top-1/2 -translate-y-1/2 text-faint pointer-events-none",
          busy && "animate-spin",
        )}
      />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        autoFocus={autoFocus}
        spellCheck={false}
        className="w-full h-7 pl-7 pr-7 rounded-[10px] bg-surface-soft focus:bg-surface-sunken border border-transparent focus:border-line-soft text-sm text-ink-soft placeholder:text-muted outline-none transition-[background-color,border-color]"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-1.5 top-1/2 grid size-4 -translate-y-1/2 place-items-center rounded text-faint hover:bg-surface-soft hover:text-ink"
        >
          <X size={ICON.XS} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}
