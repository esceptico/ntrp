import type { ButtonHTMLAttributes, Ref, ReactNode } from "react";
import { Loader2, Search, X } from "lucide-react";
import clsx from "clsx";
import { ICON } from "../../lib/icons";
import { ScrollFadeTop } from "../ScrollBlur";
import { Badge, type BadgeTone } from "../Badge";

// ─── Pane / list / detail shells ──────────────────────────────────────

export function PaneShell({
  list,
  detail,
}: {
  list: ReactNode;
  detail: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[minmax(280px,360px)_minmax(0,1fr)] h-full">
      <div className="flex flex-col min-h-0">{list}</div>
      <div className="min-h-0 overflow-y-auto scroll-thin">
        <ScrollFadeTop />
        {detail}
      </div>
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
  totalLabel,
  wrapItems,
}: {
  toolbar: ReactNode;
  items: T[];
  renderItem: (item: T) => ReactNode;
  loading: boolean;
  error?: ReactNode;
  empty?: string;
  totalLabel: string | null;
  wrapItems?: (children: ReactNode) => ReactNode;
}) {
  const mapped = items.map(renderItem);
  return (
    <>
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">{toolbar}</div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin scroll-fade-bottom px-2 pb-3">
        {loading ? (
          <Empty>Loading…</Empty>
        ) : error ? (
          <div className="px-1 py-3">{error}</div>
        ) : items.length === 0 ? (
          <Empty>{empty ?? "No matches."}</Empty>
        ) : (
          <ul className="flex flex-col gap-px">{wrapItems ? wrapItems(mapped) : mapped}</ul>
        )}
      </div>
      {totalLabel && (
        <div className="px-4 py-2 text-xs text-faint tabular-nums">{totalLabel}</div>
      )}
    </>
  );
}

export function ListError({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-[10px] border border-bad/15 bg-bad-soft px-3 py-2.5">
      <div className="text-sm font-semibold text-bad">{title}</div>
      <div className="mt-0.5 text-sm leading-[1.4] text-bad">{message}</div>
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
          "text-ink-soft min-w-0",
          row.mono && "font-mono text-xs break-all whitespace-pre-wrap",
        )}
      >
        {row.value}
      </dd>
    </>
  );
}

export function DetailPlaceholder({ children }: { children: ReactNode }) {
  return (
    <div className="grid place-items-center h-full text-base italic text-muted">{children}</div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="grid place-items-center min-h-[200px] text-base italic text-muted">
      {children}
    </div>
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
      className="inline-flex items-center h-7 px-3 rounded-md bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45] disabled:cursor-not-allowed"
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
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-sm text-ink-soft hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
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
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-sm text-ink-soft hover:bg-bad-soft hover:text-bad transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
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
        className="w-full h-7 pl-7 pr-7 rounded-md bg-surface-soft focus:bg-surface-sunken border border-transparent focus:border-line-soft text-sm text-ink-soft placeholder:text-muted outline-none transition-[background-color,border-color]"
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
