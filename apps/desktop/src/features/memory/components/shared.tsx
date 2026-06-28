import type { ButtonHTMLAttributes, ComponentType, ReactNode } from "react";
import { AlertCircle, Calendar, Inbox, List, Text } from "lucide-react";
import clsx from "clsx";
import { ICON } from "@/lib/icons";
import { ScrollFadeTop } from "@/components/ui/ScrollBlur";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

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
          <Button variant="danger" size="sm" onClick={onRetry} className="mt-2">
            Retry
          </Button>
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

// ─── Obsidian-style frontmatter properties ────────────────────────────

type FmValue = string | number | boolean | null | Array<string | number | boolean | null>;

// Internal/opaque bookkeeping a human shouldn't see as a property: the title is the
// page header, scope_key is an opaque id, aliases mirror the title, type is folder-derived,
// prose_* are synthesis telemetry. What's left is meaningful (updated + the label tags).
const _HIDE_PROPS = new Set([
  "title", "labels", "type", "aliases", "scope_key", "prose_synced", "prose_tokens", "prose_cites",
]);
const _DATE_KEYS = new Set(["created", "updated", "prose_synced", "last_updated_at", "date"]);

function humanizeKey(k: string): string {
  return k.replace(/_/g, " ");
}
function fmtDate(v: string): string {
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : v;
}

/** Render a page's YAML frontmatter as Obsidian-style typed properties (text / date /
 *  list-of-tags), each with an icon. Hides internal bookkeeping keys. */
export function Properties({ frontmatter }: { frontmatter?: Record<string, FmValue> }) {
  const entries = Object.entries(frontmatter ?? {}).filter(
    ([k, v]) => !_HIDE_PROPS.has(k) && v != null && v !== "" && !(Array.isArray(v) && v.length === 0),
  );
  if (entries.length === 0) return null;
  return (
    <div className="mb-5">
      <div className="mb-2.5 text-sm font-medium text-ink">Properties</div>
      <dl className="flex flex-col gap-2">
        {entries.map(([key, value]) => {
          const isList = Array.isArray(value);
          const isDate = !isList && _DATE_KEYS.has(key) && typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value);
          const Icon = isList ? List : isDate ? Calendar : Text;
          return (
            <div key={key} className="grid grid-cols-[140px_minmax(0,1fr)] items-start gap-2 text-sm">
              <dt className="flex items-center gap-1.5 pt-0.5 text-muted">
                <Icon className="h-3.5 w-3.5 shrink-0 text-faint" strokeWidth={2} />
                <span className="truncate">{humanizeKey(key)}</span>
              </dt>
              <dd className="min-w-0 text-ink-soft">
                {isList ? (
                  <div className="flex flex-wrap gap-1">
                    {(value as Array<string | number | boolean | null>).map((v, i) => (
                      <Pill key={`${String(v)}-${i}`} tone="neutral">{String(v)}</Pill>
                    ))}
                  </div>
                ) : isDate ? (
                  <span className="inline-flex items-center gap-1.5 tabular-nums">{fmtDate(value as string)}</span>
                ) : (
                  <span className="break-words">{String(value)}</span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
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
    <Button variant="primary" size="sm" onClick={onClick} disabled={disabled}>
      {children}
    </Button>
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
    <Button {...buttonProps} variant="ghost" size="sm" onClick={onClick} disabled={disabled}>
      {children}
    </Button>
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
    <Button variant="danger" size="sm" onClick={onClick} disabled={disabled}>
      {children}
    </Button>
  );
}

