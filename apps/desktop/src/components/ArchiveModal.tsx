import { useEffect, useMemo, useState } from "react";
import { ArchiveRestore, Search, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import {
  fetchArchivedSessions,
  permanentlyDeleteSession,
  restoreArchivedSession,
} from "../actions";
import type { ArchivedSession } from "../api";
import { PageModal } from "./PageModal";
import { useMountedRef, useMutationState } from "../lib/hooks";
import { formatRelativePast } from "../lib/format";
import { ICON } from "../lib/icons";
import { ScrollBlurTop } from "./ScrollBlur";

export function ArchiveModal() {
  const open = useStore((s) => s.archiveOpen);
  const close = useStore((s) => s.closeArchive);
  const archived = useStore((s) => s.archivedSessions);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    void fetchArchivedSessions();
  }, [open]);

  const filtered = useMemo(() => {
    if (!archived) return null;
    const q = query.trim().toLowerCase();
    if (!q) return archived;
    return archived.filter((s) => (s.name ?? "untitled").toLowerCase().includes(q));
  }, [archived, query]);

  const archivedCount = archived?.length ?? 0;

  return (
    <PageModal
      open={open}
      onClose={close}
      size="w-[min(720px,calc(100vw-80px))] h-[min(560px,calc(100vh-80px))]"
      header={{
        title: (
          <span className="inline-flex items-center gap-3">
            <span>Archive</span>
            {archivedCount > 0 && (
              <span className="text-sm font-normal text-faint tabular-nums">
                {archivedCount} session{archivedCount === 1 ? "" : "s"}
              </span>
            )}
          </span>
        ),
        actions: <SearchInput value={query} onChange={setQuery} />,
      }}
    >
      <div className="overflow-y-auto scroll-thin px-3 py-3">
        <ScrollBlurTop />
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
    </PageModal>
  );
}

function ArchivedRow({ session }: { session: ArchivedSession }) {
  const mounted = useMountedRef();
  const { busy: anyBusy, error, run } = useMutationState(mounted);
  const [busyOp, setBusyOp] = useState<"restore" | "delete" | null>(null);

  const trigger = async (op: "restore" | "delete", fn: () => Promise<void>) => {
    if (anyBusy) return;
    setBusyOp(op);
    await run(fn);
    if (mounted.current) setBusyOp(null);
  };

  const onRestore = () =>
    void trigger("restore", () => restoreArchivedSession(session.session_id));
  const onDelete = () => {
    if (!confirm("Permanently delete this session? This cannot be undone.")) return;
    void trigger("delete", () => permanentlyDeleteSession(session.session_id));
  };

  return (
    <li className="app-row group flex items-center gap-3 px-3 py-2 rounded-[10px]">
      <div className="min-w-0 flex-1">
        <div className="text-base font-medium text-ink tracking-[-0.005em] truncate">
          {session.name || "untitled"}
        </div>
        <div className="text-xs text-faint tabular-nums">
          archived {formatRelativePast(session.archived_at)} ago · {session.message_count} msg
          {session.message_count === 1 ? "" : "s"}
        </div>
        {error && (
          <div className="mt-1 text-xs text-bad truncate" title={error}>
            {error}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <RowAction
          icon={<ArchiveRestore size={ICON.XS} strokeWidth={2} />}
          label="Restore"
          onClick={onRestore}
          busy={busyOp === "restore"}
        />
        <RowAction
          icon={<Trash2 size={ICON.XS} strokeWidth={2} />}
          label="Delete"
          onClick={onDelete}
          busy={busyOp === "delete"}
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
        "inline-flex items-center gap-1.5 h-6 px-2 rounded-md text-xs font-medium tracking-[-0.005em] transition-colors",
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
    <div className="grid place-items-center min-h-[200px] text-base italic text-faint">
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
        size={ICON.XS}
        strokeWidth={2}
        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Filter…"
        spellCheck={false}
        className="w-full h-7 pl-7 pr-2 rounded-md border border-line-soft bg-[rgba(0,0,0,0.025)] text-sm text-ink-soft placeholder:text-faint outline-none focus:bg-surface focus:border-line transition-[background-color,border-color]"
      />
    </div>
  );
}
