import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { ArchiveRestore, Search, Trash2, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import {
  fetchArchivedSessions,
  permanentlyDeleteSession,
  restoreArchivedSession,
} from "../actions";
import type { ArchivedSession } from "../api";

const MODAL_BACKDROP_DURATION = 0.2;
const MODAL_PANEL_DURATION = 0.22;
const MODAL_EASE = [0.2, 0.8, 0.2, 1] as const;

export function ArchiveModal() {
  const open = useStore((s) => s.archiveOpen);
  const close = useStore((s) => s.closeArchive);
  const archived = useStore((s) => s.archivedSessions);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    void fetchArchivedSessions();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  const filtered = useMemo(() => {
    if (!archived) return null;
    const q = query.trim().toLowerCase();
    if (!q) return archived;
    return archived.filter((s) => (s.name ?? "untitled").toLowerCase().includes(q));
  }, [archived, query]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="archive"
          className="absolute inset-0 z-50 grid place-items-center p-8 bg-[rgba(0,0,0,0.32)] backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: MODAL_BACKDROP_DURATION, ease: MODAL_EASE }}
          onClick={close}
        >
          <motion.div
            className="w-[min(720px,calc(100vw-80px))] h-[min(560px,calc(100vh-80px))] grid grid-rows-[auto_minmax(0,1fr)] rounded-[14px] bg-surface shadow-[var(--shadow-pop)] overflow-hidden border border-line-soft"
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={{ duration: MODAL_PANEL_DURATION, ease: MODAL_EASE }}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between gap-3 px-6 pt-5 pb-4 border-b border-line-soft">
              <div className="flex items-center gap-3">
                <h2 className="m-0 text-[18px] font-semibold tracking-[-0.014em] text-ink">
                  Archive
                </h2>
                {archived && archived.length > 0 && (
                  <span className="text-[12px] text-faint tabular-nums">
                    {archived.length} session{archived.length === 1 ? "" : "s"}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <SearchInput value={query} onChange={setQuery} />
                <button
                  type="button"
                  onClick={close}
                  aria-label="Close"
                  className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
                >
                  <X size={13} strokeWidth={1.7} />
                </button>
              </div>
            </header>

            <div className="overflow-y-auto scroll-thin px-3 py-3">
              {filtered === null ? (
                <Empty>Loading…</Empty>
              ) : filtered.length === 0 ? (
                <Empty>
                  {archived && archived.length > 0
                    ? "No matches."
                    : "Nothing here. Archived sessions will show up in this view."}
                </Empty>
              ) : (
                <ul className="flex flex-col gap-1">
                  {filtered.map((s) => (
                    <ArchivedRow key={s.session_id} session={s} />
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}

function ArchivedRow({ session }: { session: ArchivedSession }) {
  const [busy, setBusy] = useState<"restore" | "delete" | null>(null);

  const onRestore = async () => {
    if (busy) return;
    setBusy("restore");
    try {
      await restoreArchivedSession(session.session_id);
    } catch {
      setBusy(null);
    }
  };

  const onDelete = async () => {
    if (busy) return;
    if (!confirm("Permanently delete this session? This cannot be undone.")) return;
    setBusy("delete");
    try {
      await permanentlyDeleteSession(session.session_id);
    } catch {
      setBusy(null);
    }
  };

  return (
    <li className="group flex items-center gap-3 px-3 py-2 rounded-[10px] hover:bg-surface-soft/50 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-ink tracking-[-0.005em] truncate">
          {session.name || "untitled"}
        </div>
        <div className="text-[11.5px] text-faint tabular-nums">
          archived {formatRelativePast(session.archived_at)} · {session.message_count} msg
          {session.message_count === 1 ? "" : "s"}
        </div>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <RowAction
          icon={<ArchiveRestore size={12} strokeWidth={1.8} />}
          label="Restore"
          onClick={onRestore}
          busy={busy === "restore"}
        />
        <RowAction
          icon={<Trash2 size={12} strokeWidth={1.8} />}
          label="Delete"
          onClick={onDelete}
          busy={busy === "delete"}
          danger
        />
      </div>
    </li>
  );
}

function RowAction({
  icon,
  label,
  onClick,
  busy,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  busy?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={clsx(
        "inline-flex items-center gap-1.5 h-6 px-2 rounded-md text-[11.5px] font-medium tracking-[-0.005em] transition-colors",
        busy
          ? "text-faint cursor-wait"
          : danger
            ? "text-ink-soft hover:bg-[rgba(220,38,38,0.08)] hover:text-[#b42318]"
            : "text-ink-soft hover:bg-surface-soft hover:text-ink",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center min-h-[200px] text-[13px] italic text-faint">
      {children}
    </div>
  );
}

function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative w-[200px]">
      <Search
        size={11}
        strokeWidth={1.8}
        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Filter…"
        spellCheck={false}
        className="w-full h-7 pl-7 pr-2 rounded-md border border-line-soft bg-[rgba(0,0,0,0.025)] text-[12px] text-ink-soft placeholder:text-faint outline-none focus:bg-surface focus:border-line transition-[background-color,border-color]"
      />
    </div>
  );
}

function formatRelativePast(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}
