import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Archive, Brain, Pencil, Search, Settings as SettingsIcon, Sparkles, X, Zap } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { apiWithConfig } from "../api";
import { archiveSession, createSession, renameSession, switchSession } from "../actions";
import { trackHoverDish } from "../lib/hoverDish";

function formatAge(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

const DAY_MS = 86_400_000;

function bucketByTime<T extends { last_activity: string }>(
  items: T[],
): { label: string; items: T[] }[] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const todayStart = startOfToday.getTime();
  const yesterdayStart = todayStart - DAY_MS;
  const sevenDaysAgo = todayStart - 6 * DAY_MS;
  const thirtyDaysAgo = todayStart - 29 * DAY_MS;

  const today: T[] = [];
  const yesterday: T[] = [];
  const week: T[] = [];
  const month: T[] = [];
  const older: T[] = [];
  for (const item of items) {
    const t = new Date(item.last_activity).getTime();
    if (t >= todayStart) today.push(item);
    else if (t >= yesterdayStart) yesterday.push(item);
    else if (t >= sevenDaysAgo) week.push(item);
    else if (t >= thirtyDaysAgo) month.push(item);
    else older.push(item);
  }

  const buckets: { label: string; items: T[] }[] = [];
  if (today.length) buckets.push({ label: "Today", items: today });
  if (yesterday.length) buckets.push({ label: "Yesterday", items: yesterday });
  if (week.length) buckets.push({ label: "Previous 7 days", items: week });
  if (month.length) buckets.push({ label: "Previous 30 days", items: month });
  if (older.length) buckets.push({ label: "Older", items: older });
  return buckets;
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
      onMouseMove={trackHoverDish}
      className="hover-dish flex items-center gap-[9px] w-full px-2 py-1.5 rounded-lg text-[13px] font-medium text-ink-soft text-left tracking-[-0.005em] hover:bg-[rgba(0,0,0,0.045)] transition-colors"
    >
      <span className="nav-icon grid place-items-center w-[22px] h-[22px] rounded-md text-ink-soft shrink-0">
        {icon}
      </span>
      <span>{label}</span>
    </button>
  );
}

interface ContextMenuState {
  sessionId: string;
  x: number;
  y: number;
}

function SessionRow({
  sessionId,
  name,
  lastActivity,
  active,
  streaming,
  unread,
  renaming,
  onStartRename,
  onCancelRename,
  onContextMenu,
}: {
  sessionId: string;
  name: string | null;
  lastActivity: string;
  active: boolean;
  streaming: boolean;
  unread: boolean;
  renaming: boolean;
  onStartRename: () => void;
  onCancelRename: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
}) {
  const [draft, setDraft] = useState(name ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) {
      setDraft(name ?? "");
      requestAnimationFrame(() => inputRef.current?.select());
    }
  }, [renaming, name]);

  async function commitRename() {
    const trimmed = draft.trim();
    onCancelRename();
    if (!trimmed || trimmed === (name ?? "")) return;
    try {
      await renameSession(sessionId, trimmed);
    } catch {
      /* surfaced via store error elsewhere */
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
              onCancelRename();
            }
          }}
          className="w-full h-[26px] px-2 border border-line rounded-md bg-surface text-ink text-[13px] outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
        />
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => void switchSession(sessionId)}
      onContextMenu={onContextMenu}
      onDoubleClick={(e) => {
        e.preventDefault();
        onStartRename();
      }}
      onMouseMove={trackHoverDish}
      data-streaming={streaming ? "true" : undefined}
      className={clsx(
        "session-row hover-dish relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 w-full pl-3 pr-2.5 py-1.5 rounded-lg text-left transition-colors",
        active
          ? "bg-[rgba(0,0,0,0.075)] text-ink"
          : "text-ink-soft hover:bg-[rgba(0,0,0,0.045)]",
      )}
    >
      {active && (
        <span
          aria-hidden
          className="absolute left-1 top-1.5 bottom-1.5 w-[2px] rounded-full bg-accent-strong"
        />
      )}
      <span
        className={clsx(
          "min-w-0 flex items-center gap-1.5 text-[13px] tracking-[-0.005em]",
          active ? "font-semibold" : "font-medium",
        )}
      >
        <span className="truncate">{name || "untitled"}</span>
      </span>
      {unread && !streaming ? (
        <span aria-hidden className="session-unread-dot shrink-0" title="New activity" />
      ) : (
        <span
          className={clsx(
            "text-[11px] tabular-nums shrink-0",
            active ? "text-muted" : "text-faint",
          )}
        >
          {formatAge(lastActivity)}
        </span>
      )}
    </button>
  );
}

function SessionList() {
  const sessions = useStore((s) => s.sessions);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const activeRunSessionIds = useStore((s) => s.activeRunSessionIds);
  const unreadDoneSessionIds = useStore((s) => s.unreadDoneSessionIds);
  const connected = useStore((s) => s.connected);
  const openArchive = useStore((s) => s.openArchive);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);

  const searchActive = searchOpen || query.length > 0;
  const closeSearch = () => {
    setQuery("");
    setSearchOpen(false);
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.name ?? "untitled").toLowerCase().includes(q));
  }, [sessions, query]);

  const closeMenu = () => setMenu(null);

  return (
    <div className="group/sessions flex flex-col flex-1 min-h-0">
      <div className="flex items-center gap-1 pl-[18px] pr-5 pt-4 pb-1.5 h-[34px]">
        {searchActive ? (
          <SessionSearch
            value={query}
            onChange={setQuery}
            onClose={closeSearch}
            autoFocus
          />
        ) : (
          <>
            <span className="flex-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-faint leading-none select-none">
              Sessions
            </span>
            <div className="flex items-center gap-0.5 shrink-0 -mr-1 opacity-0 group-hover/sessions:opacity-100 focus-within:opacity-100 transition-opacity">
              <HeaderIconBtn
                icon={<Search size={13} strokeWidth={1.8} />}
                label="Filter sessions"
                onClick={() => setSearchOpen(true)}
              />
              <HeaderIconBtn
                icon={<Archive size={13} strokeWidth={1.8} />}
                label="View archived sessions"
                onClick={openArchive}
              />
            </div>
          </>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin pb-3">
        {sessions.length === 0 ? (
          <div className="px-3 py-3 text-[12px] italic text-faint">
            {connected ? "No sessions yet." : "Connect to load sessions."}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-3 py-3 text-[12px] italic text-faint">No matches.</div>
        ) : (
          bucketByTime(filtered).map((bucket) => (
            <div key={bucket.label}>
              <div className="sticky top-0 z-10 px-3 pt-3 pb-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-faint bg-bg">
                {bucket.label}
              </div>
              <div className="px-2.5 flex flex-col gap-px">
                {bucket.items.map((session) => (
                  <SessionRow
                    key={session.session_id}
                    sessionId={session.session_id}
                    name={session.name ?? null}
                    lastActivity={session.last_activity}
                    active={session.session_id === currentSessionId}
                    streaming={activeRunSessionIds.has(session.session_id)}
                    unread={unreadDoneSessionIds.has(session.session_id)}
                    renaming={renamingId === session.session_id}
                    onStartRename={() => setRenamingId(session.session_id)}
                    onCancelRename={() => setRenamingId(null)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setMenu({ sessionId: session.session_id, x: e.clientX, y: e.clientY });
                    }}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {menu && (
        <SessionContextMenu
          state={menu}
          onClose={closeMenu}
          onRename={() => {
            setRenamingId(menu.sessionId);
            closeMenu();
          }}
          onCompact={async () => {
            closeMenu();
            const cfg = useStore.getState().config;
            try {
              await apiWithConfig(cfg, "/compact", {
                method: "POST",
                body: JSON.stringify({ session_id: menu.sessionId }),
              });
            } catch {
              /* ignore */
            }
          }}
          onArchive={async () => {
            closeMenu();
            if (!confirm("Archive this session? You can restore it later from the server.")) return;
            try {
              await archiveSession(menu.sessionId);
            } catch {
              /* ignore */
            }
          }}
        />
      )}
    </div>
  );
}

function HeaderIconBtn({
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
      aria-label={label}
      title={label}
      className="grid place-items-center w-[22px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-[rgba(0,0,0,0.05)] transition-colors"
    >
      {icon}
    </button>
  );
}

function SessionSearch({
  value,
  onChange,
  onClose,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onClose: () => void;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (autoFocus) requestAnimationFrame(() => ref.current?.focus());
  }, [autoFocus]);

  return (
    <div className="relative flex-1 h-[24px]">
      <Search
        size={11}
        strokeWidth={1.8}
        className="absolute left-[7px] top-1/2 -translate-y-1/2 text-faint pointer-events-none"
      />
      <input
        ref={ref}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            if (value) onChange("");
            else onClose();
          }
        }}
        onBlur={() => {
          if (!value) onClose();
        }}
        placeholder="Filter sessions"
        spellCheck={false}
        className="w-full h-full pl-[22px] pr-6 rounded-md bg-[rgba(0,0,0,0.05)] focus:bg-[rgba(0,0,0,0.07)] text-[12px] leading-none text-ink-soft placeholder:text-faint outline-none transition-[background-color] border border-transparent focus:border-line-soft"
      />
      <button
        type="button"
        onMouseDown={(e) => {
          // Prevent the input's blur from firing before our click —
          // otherwise blur-on-empty would close the bar before clear runs.
          e.preventDefault();
        }}
        onClick={() => {
          if (value) {
            onChange("");
            ref.current?.focus();
          } else {
            onClose();
          }
        }}
        aria-label={value ? "Clear filter" : "Close filter"}
        className="absolute right-1 top-1/2 -translate-y-1/2 grid place-items-center w-4 h-4 rounded-[4px] text-faint hover:text-ink hover:bg-[rgba(0,0,0,0.06)] transition-colors"
      >
        <X size={10} strokeWidth={2} />
      </button>
    </div>
  );
}

function SessionContextMenu({
  state,
  onClose,
  onRename,
  onCompact,
  onArchive,
}: {
  state: ContextMenuState;
  onClose: () => void;
  onRename: () => void;
  onCompact: () => void;
  onArchive: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: state.x, top: state.y, ready: false });

  // After mount, measure the menu and clamp to the viewport so it never
  // hangs off the right or bottom edge.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const margin = 8;
    const left = Math.min(state.x, window.innerWidth - rect.width - margin);
    const top = Math.min(state.y, window.innerHeight - rect.height - margin);
    setPos({ left: Math.max(margin, left), top: Math.max(margin, top), ready: true });
  }, [state.x, state.y]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onScroll = () => onClose();
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [onClose]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <div
      ref={ref}
      className="fixed z-50 w-[160px] py-1 rounded-[10px] border border-line-soft bg-surface shadow-[var(--shadow-pop)]"
      style={{ left: pos.left, top: pos.top, opacity: pos.ready ? 1 : 0 }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <ContextItem icon={<Pencil size={12} strokeWidth={1.8} />} label="Rename" onClick={onRename} />
      <ContextItem icon={<Sparkles size={12} strokeWidth={1.8} />} label="Compact context" onClick={onCompact} />
      <ContextItem icon={<Archive size={12} strokeWidth={1.8} />} label="Archive" onClick={onArchive} />
    </div>,
    root,
  );
}

function ContextItem({
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

export function Sidebar() {
  const openSettings = useStore((s) => s.openSettings);
  const openAutomations = useStore((s) => s.openAutomations);
  const openMemory = useStore((s) => s.openMemory);

  return (
    <aside className="sidebar flex flex-col h-full">
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
        <NavRow
          icon={<Brain size={13} strokeWidth={1.7} />}
          label="Memory"
          onClick={openMemory}
        />
      </nav>
      <SessionList />
      <nav className="flex flex-col gap-px px-2.5 pt-1.5 pb-3">
        <NavRow icon={<SettingsIcon size={13} strokeWidth={1.7} />} label="Settings" onClick={openSettings} />
      </nav>
    </aside>
  );
}
