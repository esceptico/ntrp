import type { ReactNode } from "react";
import { Search } from "lucide-react";
import clsx from "clsx";

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
      <div className="flex flex-col min-h-0 bg-bg-main/50">{list}</div>
      <div className="min-h-0 overflow-y-auto scroll-thin">{detail}</div>
    </div>
  );
}

export function ListColumn<T>({
  toolbar,
  items,
  renderItem,
  loading,
  empty,
  totalLabel,
}: {
  toolbar: ReactNode;
  items: T[];
  renderItem: (item: T) => ReactNode;
  loading: boolean;
  empty?: string;
  totalLabel: string | null;
}) {
  return (
    <>
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">{toolbar}</div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin px-2 pb-3">
        {loading ? (
          <Empty>Loading…</Empty>
        ) : items.length === 0 ? (
          <Empty>{empty ?? "No matches."}</Empty>
        ) : (
          <ul className="flex flex-col gap-px">{items.map(renderItem)}</ul>
        )}
      </div>
      {totalLabel && (
        <div className="px-4 py-2 text-[11px] text-faint tabular-nums">{totalLabel}</div>
      )}
    </>
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
        {body}
        <div className="mt-7 mb-6">{meta}</div>
      </div>
      <div className="flex items-center justify-end gap-2 px-7 py-3">{actions}</div>
    </div>
  );
}

export function DetailMeta({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center flex-wrap gap-2 text-[11.5px] text-faint">{children}</div>
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
    <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-y-2.5 text-[12px]">
      {present.map((row) => (
        <MetaRow key={row.label} row={row} />
      ))}
    </dl>
  );
}

function MetaRow({ row }: { row: MetaGridRow }) {
  return (
    <>
      <dt className="text-faint">{row.label}</dt>
      <dd
        className={clsx(
          "text-ink-soft min-w-0",
          row.mono && "font-mono text-[11.5px] break-all whitespace-pre-wrap",
        )}
      >
        {row.value}
      </dd>
    </>
  );
}

export function DetailPlaceholder({ children }: { children: ReactNode }) {
  return (
    <div className="grid place-items-center h-full text-[13px] italic text-faint">{children}</div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="grid place-items-center min-h-[200px] text-[13px] italic text-faint">
      {children}
    </div>
  );
}

export function ErrorPill({ message }: { message: string }) {
  return (
    <span
      className="mr-auto inline-flex items-center max-w-[60%] truncate rounded-md bg-bad-soft border border-[rgba(184,68,43,0.18)] text-bad text-[11.5px] px-2 py-[3px]"
      title={message}
    >
      {message}
    </span>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "ok" | "warn" | "bad";
}) {
  const classes = {
    neutral: "bg-surface-soft text-muted border-line-soft",
    accent: "bg-accent-soft text-accent-strong border-[rgba(184,92,31,0.16)]",
    ok: "bg-ok-soft text-ok border-[rgba(79,138,58,0.18)]",
    warn: "bg-warn-soft text-warn border-[rgba(196,106,20,0.18)]",
    bad: "bg-bad-soft text-bad border-[rgba(184,68,43,0.18)]",
  }[tone];

  return (
    <span className={clsx("inline-flex items-center rounded-md border px-2 py-[3px] text-[11px]", classes)}>
      {children}
    </span>
  );
}

export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="m-0 max-h-[260px] overflow-auto scroll-thin rounded-[8px] border border-line-soft bg-code-bg px-3 py-2 text-[11.5px] leading-relaxed text-ink-soft whitespace-pre-wrap">
      {JSON.stringify(value, null, 2)}
    </pre>
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
      className="inline-flex items-center h-7 px-3 rounded-md bg-ink text-on-ink text-[12px] font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}

export function GhostBtn({
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
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[12px] text-ink-soft hover:bg-surface-soft hover:text-ink transition-colors disabled:opacity-50"
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
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[12px] text-ink-soft hover:bg-[rgba(220,38,38,0.08)] hover:text-[#b42318] transition-colors disabled:opacity-50"
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
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative flex-1 min-w-0">
      <Search
        size={11}
        strokeWidth={1.8}
        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className="w-full h-7 pl-7 pr-2 rounded-md bg-[rgba(0,0,0,0.04)] focus:bg-[rgba(0,0,0,0.06)] border border-transparent focus:border-line-soft text-[12px] text-ink-soft placeholder:text-faint outline-none transition-[background-color,border-color]"
      />
    </div>
  );
}
