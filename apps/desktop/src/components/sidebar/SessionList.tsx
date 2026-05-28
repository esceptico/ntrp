import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Archive, ChevronDown, Folder, FolderPlus, Plus, Search, Settings, X } from "lucide-react";
import clsx from "clsx";
import { MOTION, EASE_EMPHASIZED, originFromEvent } from "../../lib/motion";
import { useStore } from "../../store";
import { compactSessionApi } from "../../api";
import { archiveSession, createProject, createSession, loadHistory, moveSessionToProject } from "../../actions";
import { ICON } from "../../lib/icons";
import { useTimeTicker } from "../../lib/hooks";
import { groupProjectSessions } from "../../lib/projects";
import { SessionRow } from "./SessionRow";
import { SessionContextMenu, type ContextMenuState } from "./SessionContextMenu";
import { ProjectSettingsModal } from "./ProjectSettingsModal";

export function SessionList() {
  useTimeTicker();
  const projects = useStore((s) => s.projects);
  const sessions = useStore((s) => s.sessions);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const activeRunSessionIds = useStore((s) => s.activeRunSessionIds);
  const backgroundedRunSessionIds = useStore((s) => s.backgroundedRunSessionIds);
  const unreadDoneSessionIds = useStore((s) => s.unreadDoneSessionIds);
  const connected = useStore((s) => s.connected);
  const openArchive = useStore((s) => s.openArchive);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

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

  const toggleGroup = (label: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const grouped = useMemo(() => groupProjectSessions(projects, sessions, query), [projects, sessions, query]);
  const editingProject = projects.find((project) => project.project_id === editingProjectId) ?? null;

  const closeMenu = () => setMenu(null);

  return (
    <div className="group/sessions flex flex-col flex-1 min-h-0">
      <div className="px-2.5 pt-3 pb-1.5">
        <div className="flex items-center gap-2 pl-[8px] pr-[6px] h-[26px]">
          <div className="min-w-0 flex-1 flex items-center gap-1.5 text-2xs font-medium uppercase tracking-[0.08em] text-faint select-none">
            <Folder size={ICON.XS} strokeWidth={2.1} />
            <span className="truncate">Projects</span>
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <HeaderIconButton
              icon={<FolderPlus size={ICON.SM} strokeWidth={2} />}
              label="New project"
              onClick={() => void createProject()}
            />
            <HeaderIconButton
              icon={<Search size={ICON.SM} strokeWidth={2} />}
              label="Filter sessions"
              title="Filter sessions (⌘F)"
              active={searchActive}
              onClick={() => setSearchOpen(true)}
            />
            <HeaderIconButton
              icon={<Archive size={ICON.SM} strokeWidth={2} />}
              label="View archived sessions"
              onClick={(e) => openArchive(originFromEvent(e.currentTarget))}
            />
          </div>
        </div>
        {searchActive && (
          <div className="pt-1.5">
            <SessionSearch
              value={query}
              onChange={setQuery}
              onClose={closeSearch}
              autoFocus
            />
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin scroll-fade-bottom pb-3">
        {sessions.length === 0 && projects.length === 0 ? (
          <div className="px-3 py-3 text-sm italic text-faint">
            {connected ? "No sessions yet." : "Connect to load sessions."}
          </div>
        ) : grouped.length === 0 ? (
          <div className="px-3 py-3 text-sm italic text-faint">No matches.</div>
        ) : (
          grouped.map((group) => {
            const groupKey = group.project?.project_id ?? "inbox";
            const label = group.project?.name ?? "Inbox";
            const isCollapsed = collapsedGroups.has(groupKey);
            return (
              <div key={groupKey}>
                <div className="flex items-center gap-1 pr-[18px]">
                  <button
                    type="button"
                    onClick={() => toggleGroup(groupKey)}
                    aria-expanded={!isCollapsed}
                    className={clsx(
                      "flex-1 flex items-center gap-1 pl-[18px] pt-1.5 pb-1 text-2xs font-medium uppercase tracking-[0.08em] text-faint hover:text-muted transition-colors cursor-pointer select-none",
                    )}
                  >
                    <Folder size={ICON.XS} strokeWidth={2.1} />
                    <ChevronDown
                      size={ICON.XS}
                      strokeWidth={2.2}
                      className={clsx(
                        "transition-transform duration-150",
                        isCollapsed && "-rotate-90",
                      )}
                    />
                    <span className="truncate">{label}</span>
                  </button>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {group.project && (
                      <button
                        type="button"
                        onClick={() => setEditingProjectId(group.project?.project_id ?? null)}
                        aria-label={`Project settings for ${group.project.name}`}
                        title="Project settings"
                        className="grid place-items-center w-[26px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-surface-soft/70 transition-colors"
                      >
                        <Settings size={ICON.SM} strokeWidth={2} />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void createSession(group.project?.project_id ?? null)}
                      aria-label={`New session in ${label}`}
                      title="New session"
                      className="grid place-items-center w-[26px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-surface-soft/70 transition-colors"
                    >
                      <Plus size={ICON.SM} strokeWidth={2} />
                    </button>
                  </div>
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
                        {group.sessions.map((session) => (
                          <SessionRow
                            key={session.session_id}
                            sessionId={session.session_id}
                            name={session.name ?? null}
                            lastActivity={session.last_activity}
                            active={session.session_id === currentSessionId}
                            streaming={
                              activeRunSessionIds.has(session.session_id) ||
                              backgroundedRunSessionIds.has(session.session_id)
                            }
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
          onMoveProject={async (projectId) => {
            const sessionId = menu.sessionId;
            closeMenu();
            try {
              await moveSessionToProject(sessionId, projectId);
            } catch {
              /* ignore */
            }
          }}
          projects={projects}
        />
      )}
      <ProjectSettingsModal project={editingProject} onClose={() => setEditingProjectId(null)} />
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

function HeaderIconButton({
  icon,
  label,
  title,
  active = false,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  title?: string;
  active?: boolean;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={title ?? label}
      className={clsx(
        "grid place-items-center w-[26px] h-[22px] rounded-[5px] transition-colors",
        active
          ? "text-ink bg-surface-soft/80"
          : "text-faint hover:text-ink hover:bg-surface-soft/70",
      )}
    >
      {icon}
    </button>
  );
}
