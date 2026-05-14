import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { Archive, Brain, ChevronDown, Pencil, Radio, Search, Settings as SettingsIcon, Sparkles, X, Zap } from "lucide-react";
import clsx from "clsx";
import { MOTION, EASE_EMPHASIZED, originFromEvent } from "../lib/motion";
import { useStore } from "../store";
import { apiWithConfig } from "../api";
import { archiveSession, createSession, fetchAutomations, renameSession, switchSession } from "../actions";
import { ICON } from "../lib/icons";
import { StatusDot } from "./AgentRightSidebar";

function formatAge(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

/** Re-render the caller every `intervalMs` so `Date.now()`-based labels
 *  (formatAge, "1m / 12h / 2d") tick forward without user interaction. */
function useTimeTicker(intervalMs = 30_000): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
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

/** Primary nav row — matches the SessionRow grid (16px icon column +
 *  label) so the top and bottom blocks of the sidebar read as the
 *  same visual rhythm. No boxed icon container; flat stroked icon
 *  inherits the row's text color for hover/active states. */
function NavRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  // Receives the click event so callers can capture the trigger position
  // for modal spatial-origin animations.
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="app-row grid grid-cols-[16px_minmax(0,1fr)] items-center gap-2 w-full px-2 py-1 rounded-lg text-base font-medium text-ink-soft text-left tracking-[-0.005em]"
    >
      <span className="grid place-items-center w-4 h-4 shrink-0">
        {icon}
      </span>
      <span className="truncate">{label}</span>
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
  isChannel,
  renaming,
  onStartRename,
  onCancelRename,
  onArchive,
  onContextMenu,
}: {
  sessionId: string;
  name: string | null;
  lastActivity: string;
  active: boolean;
  streaming: boolean;
  unread: boolean;
  isChannel: boolean;
  renaming: boolean;
  onStartRename: () => void;
  onCancelRename: () => void;
  onArchive: () => void;
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
      <div className="grid grid-cols-[16px_minmax(0,1fr)] items-center gap-2 w-full px-2 py-1 rounded-lg bg-surface-soft text-ink shadow-[var(--shadow-sm)]">
        <span aria-hidden />
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
          className="min-w-0 w-full bg-transparent border-0 p-0 text-base font-medium tracking-[-0.005em] text-ink outline-none"
        />
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => void switchSession(sessionId)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          void switchSession(sessionId);
        }
      }}
      onContextMenu={onContextMenu}
      onDoubleClick={(e) => {
        e.preventDefault();
        onStartRename();
      }}
      data-streaming={streaming ? "true" : undefined}
      data-active={active ? "true" : undefined}
      className="app-row session-row group/row grid grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 w-full px-2 py-1 rounded-lg text-ink-soft text-left cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
    >
      <SessionStateIcon streaming={streaming} unread={unread} isChannel={isChannel} />
      <span className="min-w-0 truncate text-base font-medium tracking-[-0.005em]">
        {name || "untitled"}
      </span>
      <span className="relative shrink-0 h-[22px] w-[56px]">
        {/* Default state: timestamp. Hover swaps to row actions. */}
        <span className="absolute inset-0 flex items-center justify-end pr-[5px] transition-opacity duration-150 group-hover/row:opacity-0 pointer-events-none">
          <span
            className={clsx(
              "text-xs tabular-nums",
              active ? "text-muted" : "text-faint",
            )}
          >
            {formatAge(lastActivity)}
          </span>
        </span>
        <span className="absolute inset-0 flex items-center justify-end gap-0.5 opacity-0 group-hover/row:opacity-100 transition-opacity duration-150">
          <RowAction
            icon={<Pencil size={ICON.SM} strokeWidth={2} />}
            label="Rename"
            onClick={onStartRename}
          />
          <RowAction
            icon={<Archive size={ICON.SM} strokeWidth={2} />}
            label="Archive"
            onClick={onArchive}
          />
        </span>
      </span>
    </div>
  );
}

/** Leading state glyph on each session row. Only rendered for
 *  states with something to indicate — streaming (animated dots in
 *  accent) and unread done (solid dot in accent-strong). Idle rows
 *  return an empty span that preserves the grid column width so the
 *  text alignment stays consistent across all rows. */
function SessionStateIcon({
  streaming,
  unread,
  isChannel,
}: {
  streaming: boolean;
  unread: boolean;
  isChannel: boolean;
}) {
  if (streaming) {
    return (
      <span className="grid place-items-center w-4 h-4" aria-label="Running">
        <StatusDot status="running" pulse />
      </span>
    );
  }
  if (unread) {
    return (
      <span className="grid place-items-center w-4 h-4" aria-label="Unread">
        <span className="block w-[5px] h-[5px] rounded-full bg-accent-strong" />
      </span>
    );
  }
  if (isChannel) {
    return (
      <span className="grid place-items-center w-4 h-4 text-faint" aria-label="Channel">
        <Radio size={ICON.SM} strokeWidth={2} />
      </span>
    );
  }
  return <span aria-hidden />;
}

function RowAction({
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
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      onMouseDown={(e) => e.stopPropagation()}
      // Wider than the icon (Fitts's law) — vertical space in the row is
      // tight (22px row) so we widen horizontally to expand the hit area
      // without affecting line-height. Icon stays centered.
      className="grid place-items-center w-[26px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-surface-soft/70 transition-colors"
    >
      {icon}
    </button>
  );
}

function SessionList() {
  useTimeTicker();
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
  // Buckets that the user has explicitly collapsed. Local state — not
  // persisted, since "what's open" tends to be answer-where-you-left-off
  // and resetting on app launch is fine.
  const [collapsedBuckets, setCollapsedBuckets] = useState<Set<string>>(new Set());

  const searchActive = searchOpen || query.length > 0;
  const closeSearch = () => {
    setQuery("");
    setSearchOpen(false);
  };

  // Cmd/Ctrl+F opens the sidebar search. Replaces the previous always-
  // visible search button — keeps the chrome minimal while preserving
  // standard "filter this list" muscle memory.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggleBucket = (label: string) => {
    setCollapsedBuckets((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.name ?? "untitled").toLowerCase().includes(q));
  }, [sessions, query]);

  const closeMenu = () => setMenu(null);

  return (
    <div className="group/sessions flex flex-col flex-1 min-h-0">
      {/* No umbrella "Recents" label — the time buckets below are
          themselves the section labels, so a redundant title would
          just add chrome. Search expands inline at the top of the
          list when triggered (button in bottom nav). */}
      {searchActive && (
        <div className="px-2.5 pt-3 pb-1">
          <SessionSearch
            value={query}
            onChange={setQuery}
            onClose={closeSearch}
            autoFocus
          />
        </div>
      )}

      <div className={clsx("flex-1 min-h-0 overflow-y-auto scroll-thin pb-3", !searchActive && "pt-3")}>
        {sessions.length === 0 ? (
          <div className="px-3 py-3 text-sm italic text-faint">
            {connected ? "No sessions yet." : "Connect to load sessions."}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-3 py-3 text-sm italic text-faint">No matches.</div>
        ) : (
          bucketByTime(filtered).map((bucket, idx) => {
            const isCollapsed = collapsedBuckets.has(bucket.label);
            const isFirst = idx === 0 && !searchActive;
            return (
              <div key={bucket.label}>
                <div className="sticky top-0 z-10 flex items-center gap-1 pr-[18px] bg-bg-main">
                  <button
                    type="button"
                    onClick={() => toggleBucket(bucket.label)}
                    aria-expanded={!isCollapsed}
                    className={clsx(
                      "flex-1 flex items-center gap-1 pl-[18px] pt-1.5 pb-1 text-2xs font-medium uppercase tracking-[0.08em] text-faint hover:text-muted transition-colors cursor-pointer select-none",
                    )}
                  >
                    <ChevronDown
                      size={ICON.XS}
                      strokeWidth={2.2}
                      className={clsx(
                        "transition-transform duration-150",
                        isCollapsed && "-rotate-90",
                      )}
                    />
                    <span>{bucket.label}</span>
                  </button>
                  {isFirst && (
                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => setSearchOpen(true)}
                        aria-label="Filter sessions"
                        title="Filter sessions (⌘F)"
                        className="grid place-items-center w-[26px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-surface-soft/70 transition-colors"
                      >
                        <Search size={ICON.SM} strokeWidth={2} />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => openArchive(originFromEvent(e.currentTarget))}
                        aria-label="View archived sessions"
                        title="View archived sessions"
                        className="grid place-items-center w-[26px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-surface-soft/70 transition-colors"
                      >
                        <Archive size={ICON.SM} strokeWidth={2} />
                      </button>
                    </div>
                  )}
                </div>
                <AnimatePresence initial={false}>
                  {!isCollapsed && (
                    <motion.div
                      key="rows"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
                      style={{ overflow: "hidden" }}
                    >
                      <div className="px-2.5 flex flex-col gap-0">
                        {bucket.items.map((session) => (
                          <SessionRow
                            key={session.session_id}
                            sessionId={session.session_id}
                            name={session.name ?? null}
                            lastActivity={session.last_activity}
                            active={session.session_id === currentSessionId}
                            streaming={activeRunSessionIds.has(session.session_id)}
                            unread={unreadDoneSessionIds.has(session.session_id)}
                            isChannel={session.session_type === "channel"}
                            renaming={renamingId === session.session_id}
                            onStartRename={() => setRenamingId(session.session_id)}
                            onCancelRename={() => setRenamingId(null)}
                            onArchive={() => void archiveSession(session.session_id)}
                            onContextMenu={(e) => {
                              e.preventDefault();
                              setMenu({ sessionId: session.session_id, x: e.clientX, y: e.clientY });
                            }}
                          />
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })
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
        size={ICON.SM}
        strokeWidth={2}
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
        className="w-full h-full pl-[22px] pr-6 rounded-md bg-[rgba(0,0,0,0.05)] focus:bg-[rgba(0,0,0,0.07)] text-sm leading-none text-ink-soft placeholder:text-faint outline-none transition-[background-color] border border-transparent focus:border-line-soft"
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
        <X size={ICON.XS} strokeWidth={2} />
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
      <ContextItem icon={<Pencil size={ICON.MD} strokeWidth={2} />} label="Rename" onClick={onRename} />
      <ContextItem icon={<Sparkles size={ICON.MD} strokeWidth={2} />} label="Compact context" onClick={onCompact} />
      <ContextItem icon={<Archive size={ICON.MD} strokeWidth={2} />} label="Archive" onClick={onArchive} />
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
      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-sm text-ink-soft hover:bg-surface-soft/60 hover:text-ink transition-colors"
    >
      <span className="grid place-items-center w-3.5 h-3.5 shrink-0 text-faint">{icon}</span>
      {label}
    </button>
  );
}

/** Background poll for automations so the sidebar card stays fresh.
 *  There's no SSE for automation start/stop today, so we ask every 20s.
 *  Cheap GET, only when the app is foregrounded — pause when the tab is
 *  hidden so a background instance isn't hitting the backend on a timer. */
function useAutomationsPoll(): void {
  useEffect(() => {
    let cancelled = false;
    const tick = () => { if (!cancelled) void fetchAutomations(); };
    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, 20_000);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
}

export function Sidebar() {
  const openSettings = useStore((s) => s.openSettings);
  const openAutomations = useStore((s) => s.openAutomations);
  const openMemory = useStore((s) => s.openMemory);
  useAutomationsPoll();

  return (
    <aside className="sidebar flex flex-col h-full">
      {/* Drag region. Height tuned so nav rows start just below the
          macOS traffic-lights zone, not below a 38px chrome ribbon. */}
      <div className="drag-spacer shrink-0 h-[22px]" />
      <nav className="flex flex-col gap-px px-2.5 pt-2">
        <NavRow
          icon={<Pencil size={ICON.LG} strokeWidth={2} />}
          label="New session"
          onClick={() => void createSession()}
        />
        <NavRow
          icon={<Zap size={ICON.LG} strokeWidth={2} />}
          label="Automations"
          onClick={(e) => openAutomations(originFromEvent(e.currentTarget))}
        />
        <NavRow
          icon={<Brain size={ICON.LG} strokeWidth={2} />}
          label="Memory"
          onClick={(e) => openMemory(originFromEvent(e.currentTarget))}
        />
      </nav>
      <SessionList />
      <nav className="flex flex-col gap-px px-2.5 pt-1.5 pb-3">
        <NavRow
          icon={<SettingsIcon size={ICON.LG} strokeWidth={2} />}
          label="Settings"
          onClick={(e) => openSettings(originFromEvent(e.currentTarget))}
        />
      </nav>
    </aside>
  );
}
