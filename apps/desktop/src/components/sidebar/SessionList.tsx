import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Archive, ChevronDown, Search, X } from "lucide-react";
import clsx from "clsx";
import { MOTION, EASE_EMPHASIZED, originFromEvent } from "../../lib/motion";
import { useStore } from "../../store";
import { compactSessionApi } from "../../api";
import { archiveSession, loadHistory } from "../../actions";
import { ICON } from "../../lib/icons";
import { useTimeTicker } from "../../lib/hooks";
import { SessionRow } from "./SessionRow";
import { SessionContextMenu, type ContextMenuState } from "./SessionContextMenu";

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

export function SessionList() {
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

      <div className={clsx("flex-1 min-h-0 overflow-y-auto scroll-thin scroll-fade-both pb-3", !searchActive && "pt-3")}>
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
                <div className="sticky top-0 z-10 flex items-center gap-1 pr-[18px]">
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
                      initial={{ gridTemplateRows: "0fr", opacity: 0 }}
                      animate={{ gridTemplateRows: "1fr", opacity: 1 }}
                      exit={{ gridTemplateRows: "0fr", opacity: 0 }}
                      transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
                      style={{ display: "grid" }}
                    >
                      <div className="px-2.5 flex flex-col gap-0 overflow-hidden min-h-0">
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
            const sessionId = menu.sessionId;
            closeMenu();
            const cfg = useStore.getState().config;
            try {
              const result = await compactSessionApi(cfg, sessionId);
              if (result.status === "compacted" && useStore.getState().currentSessionId === sessionId) {
                await loadHistory(sessionId);
              }
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
