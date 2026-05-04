import { useEffect, useRef, useState } from "react";
import { Archive, MoreHorizontal, Pencil, Settings as SettingsIcon, Zap } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { archiveSession, createSession, renameSession, switchSession } from "../actions";

function formatAge(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function NavRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-[9px] w-full px-2 py-1.5 rounded-lg text-[13px] font-medium text-ink-soft text-left tracking-[-0.005em] hover:bg-[rgba(0,0,0,0.045)] transition-colors"
    >
      <span className="nav-icon grid place-items-center w-[22px] h-[22px] rounded-md text-ink-soft shrink-0">
        {icon}
      </span>
      <span>{label}</span>
    </button>
  );
}

function SessionRow({
  sessionId,
  name,
  lastActivity,
  active,
}: {
  sessionId: string;
  name: string | null;
  lastActivity: string;
  active: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(name ?? "");
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  useEffect(() => {
    if (renaming) {
      setDraft(name ?? "");
      requestAnimationFrame(() => inputRef.current?.select());
    }
  }, [renaming, name]);

  async function commitRename() {
    const trimmed = draft.trim();
    setRenaming(false);
    if (!trimmed || trimmed === (name ?? "")) return;
    try {
      await renameSession(sessionId, trimmed);
    } catch {
      /* surfaced via store error elsewhere */
    }
  }

  async function doArchive() {
    setMenuOpen(false);
    if (!confirm("Archive this session? You can restore it later from the server.")) return;
    try {
      await archiveSession(sessionId);
    } catch {
      /* ignore — caller will see UI snap back */
    }
  }

  if (renaming) {
    return (
      <div className="grid grid-cols-[minmax(0,1fr)] w-full px-2 py-1">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void commitRename()}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void commitRename();
            } else if (e.key === "Escape") {
              e.preventDefault();
              setRenaming(false);
            }
          }}
          className="w-full h-[26px] px-2 border border-line rounded-md bg-surface text-ink text-[13px] outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
        />
      </div>
    );
  }

  return (
    <div ref={wrapRef} className="relative group/session">
      <button
        type="button"
        onClick={() => void switchSession(sessionId)}
        className={clsx(
          "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 w-full px-2.5 py-1.5 rounded-lg text-left transition-colors",
          active
            ? "bg-[rgba(0,0,0,0.07)] text-ink"
            : "text-ink-soft hover:bg-[rgba(0,0,0,0.045)]",
        )}
      >
        <span className="text-[13px] font-medium tracking-[-0.005em] truncate">
          {name || "untitled"}
        </span>
        <span
          className={clsx(
            "text-[11px] tabular-nums shrink-0 transition-opacity",
            active ? "text-muted" : "text-faint",
            // Hide the age when the row is hovered or the menu's open so the
            // ⋯ trigger has somewhere to live without shifting layout.
            "group-hover/session:opacity-0",
            menuOpen && "opacity-0",
          )}
        >
          {formatAge(lastActivity)}
        </span>
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((v) => !v);
        }}
        title="Session actions"
        aria-label="Session actions"
        className={clsx(
          "absolute top-1/2 -translate-y-1/2 right-1.5 grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-[rgba(0,0,0,0.06)] transition-opacity",
          menuOpen ? "opacity-100" : "opacity-0 group-hover/session:opacity-100",
        )}
      >
        <MoreHorizontal size={13} strokeWidth={2} />
      </button>
      {menuOpen && (
        <div className="absolute z-20 right-1 top-[calc(100%+2px)] w-[140px] rounded-[10px] border border-line-soft bg-surface shadow-[var(--shadow-pop)] overflow-hidden py-1">
          <MenuItem
            icon={<Pencil size={12} strokeWidth={1.8} />}
            label="Rename"
            onClick={() => {
              setMenuOpen(false);
              setRenaming(true);
            }}
          />
          <MenuItem
            icon={<Archive size={12} strokeWidth={1.8} />}
            label="Archive"
            onClick={() => void doArchive()}
          />
        </div>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[12.5px] text-ink-soft hover:bg-surface-soft/60 hover:text-ink transition-colors"
    >
      <span className="grid place-items-center w-3.5 h-3.5 shrink-0 text-faint">{icon}</span>
      {label}
    </button>
  );
}

function SessionList() {
  const sessions = useStore((s) => s.sessions);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const connected = useStore((s) => s.connected);

  return (
    <>
      <div className="flex items-center justify-between px-[18px] pt-[22px] pb-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-faint">
        <span>Sessions</span>
        {sessions.length > 0 && <span>{sessions.length}</span>}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin px-2.5 pb-3 flex flex-col gap-px">
        {sessions.length === 0 ? (
          <div className="px-3 py-3 text-[12px] italic text-faint">
            {connected ? "No sessions yet." : "Connect to load sessions."}
          </div>
        ) : (
          sessions.map((session) => (
            <SessionRow
              key={session.session_id}
              sessionId={session.session_id}
              name={session.name ?? null}
              lastActivity={session.last_activity}
              active={session.session_id === currentSessionId}
            />
          ))
        )}
      </div>
    </>
  );
}

export function Sidebar() {
  const openSettings = useStore((s) => s.openSettings);
  const openAutomations = useStore((s) => s.openAutomations);

  return (
    <aside className="sidebar flex flex-col">
      <div className="drag-spacer shrink-0 h-[38px]" />
      <nav className="flex flex-col gap-px px-2.5 pt-2">
        <NavRow
          icon={<Pencil size={13} strokeWidth={1.7} />}
          label="New session"
          onClick={() => void createSession()}
        />
        <NavRow
          icon={<Zap size={13} strokeWidth={1.7} />}
          label="Automations"
          onClick={openAutomations}
        />
      </nav>
      <SessionList />
      <nav className="flex flex-col gap-px px-2.5 pt-1.5 pb-3">
        <NavRow icon={<SettingsIcon size={13} strokeWidth={1.7} />} label="Settings" onClick={openSettings} />
      </nav>
    </aside>
  );
}
