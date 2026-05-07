import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import {
  Archive,
  Brain,
  GitBranch,
  MessageSquare,
  PanelLeft,
  Pencil,
  Search,
  Settings as SettingsIcon,
  Sparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { archiveSession, branchAtMessage, createSession, switchSession } from "../actions";
import { apiWithConfig } from "../api";
import { formatRelativePast } from "../lib/format";
import { trackHoverDish } from "../lib/hoverDish";

const BACKDROP_DURATION = 0.16;
const PANEL_DURATION = 0.18;
const EASE = [0.2, 0.8, 0.2, 1] as const;

interface CommandEntry {
  id: string;
  section: "suggested" | "open" | "session";
  label: string;
  hint?: string;
  shortcut?: string;
  icon: LucideIcon;
  run: () => void | Promise<void>;
  /** Lower-cased haystack used for fuzzy matching. */
  search: string;
}

export function CommandPalette() {
  const open = useStore((s) => s.paletteOpen);
  const close = useStore((s) => s.closePalette);
  const togglePalette = useStore((s) => s.togglePalette);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);

  // Global Cmd/Ctrl+K toggle + Esc close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        togglePalette();
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, togglePalette, close]);

  // Reset state on open.
  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
    }
  }, [open]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette"
          className="absolute inset-0 z-[60] grid place-items-start justify-center pt-[14vh] p-8 bg-[rgba(0,0,0,0.28)] backdrop-blur-xl"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: BACKDROP_DURATION, ease: EASE }}
          onClick={close}
        >
          <motion.div
            className="w-[min(660px,calc(100vw-80px))] max-h-[62vh] grid grid-rows-[auto_minmax(0,1fr)] rounded-[16px] bg-surface shadow-[var(--shadow-pop)] overflow-hidden border border-line-soft origin-top"
            initial={{ opacity: 0, scale: 0.96, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -6 }}
            transition={{ duration: PANEL_DURATION, ease: EASE }}
            onClick={(e) => e.stopPropagation()}
          >
            <PaletteBody
              query={query}
              setQuery={setQuery}
              index={index}
              setIndex={setIndex}
              onClose={close}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}

function PaletteBody({
  query,
  setQuery,
  index,
  setIndex,
  onClose,
}: {
  query: string;
  setQuery: (q: string) => void;
  index: number;
  setIndex: (n: number) => void;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const activeRowRef = useRef<HTMLButtonElement>(null);
  const entries = useEntries();
  const filtered = useMemo(() => filterEntries(entries, query), [entries, query]);
  const safe = Math.min(index, Math.max(0, filtered.length - 1));

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Reset index when filter changes.
  useEffect(() => {
    setIndex(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  // Keep the highlighted row in view while arrow-navigating.
  useEffect(() => {
    activeRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [safe]);

  const grouped = useMemo(() => groupBySection(filtered), [filtered]);

  function execute(entry: CommandEntry) {
    onClose();
    void entry.run();
  }

  return (
    <>
      <div className="relative px-4 pt-3 pb-2.5">
        <Search
          size={15}
          strokeWidth={1.8}
          className="absolute left-4 top-[22px] text-faint pointer-events-none"
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (filtered.length === 0) return;
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setIndex((safe + 1) % filtered.length);
              return;
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setIndex((safe - 1 + filtered.length) % filtered.length);
              return;
            }
            if (e.key === "Enter") {
              e.preventDefault();
              execute(filtered[safe]);
            }
          }}
          placeholder="Search commands, sessions, memory..."
          spellCheck={false}
          className="w-full h-8 pl-6 bg-transparent text-[14px] text-ink placeholder:text-faint outline-none"
        />
      </div>

      <div ref={listRef} className="overflow-y-auto scroll-thin pb-2 border-t border-line-soft/60">
        {filtered.length === 0 ? (
          <div className="grid place-items-center min-h-[120px] text-[12.5px] italic text-faint">
            Nothing matches.
          </div>
        ) : (
          grouped.map(({ section, items }) => (
            <div key={section}>
              <div className="px-4 pt-3 pb-1 text-[10.5px] font-medium uppercase tracking-[0.10em] text-faint">
                {SECTION_LABEL[section]}
              </div>
              <ul className="m-0 px-1.5 list-none">
                {items.map((entry) => {
                  const isActive = entry === filtered[safe];
                  return (
                    <Row
                      key={entry.id}
                      entry={entry}
                      active={isActive}
                      activeRef={isActive ? activeRowRef : undefined}
                      onHover={() => setIndex(filtered.indexOf(entry))}
                      onClick={() => execute(entry)}
                    />
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </div>
    </>
  );
}

function Row({
  entry,
  active,
  activeRef,
  onHover,
  onClick,
}: {
  entry: CommandEntry;
  active: boolean;
  activeRef?: React.RefObject<HTMLButtonElement | null>;
  onHover: () => void;
  onClick: () => void;
}) {
  const Icon = entry.icon;
  return (
    <li>
      <button
        ref={activeRef}
        type="button"
        onMouseEnter={onHover}
        onMouseMove={trackHoverDish}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onClick}
        className={clsx(
          "hover-dish w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-[8px] text-left transition-colors",
          active ? "bg-surface-soft text-ink" : "hover:bg-surface-soft/60",
        )}
      >
        <span
          className={clsx(
            "grid place-items-center w-5 h-5 rounded-md shrink-0 transition-colors",
            active ? "bg-accent-soft text-accent-strong" : "text-muted",
          )}
        >
          <Icon size={14} strokeWidth={1.7} />
        </span>
        <span className="text-[13px] text-ink truncate flex-1">{entry.label}</span>
        {entry.hint && (
          <span className="text-[11.5px] text-faint tabular-nums shrink-0">{entry.hint}</span>
        )}
        {entry.shortcut && (
          <kbd className="text-[10.5px] text-faint font-mono shrink-0 ml-1">{entry.shortcut}</kbd>
        )}
      </button>
    </li>
  );
}

const SECTION_LABEL: Record<CommandEntry["section"], string> = {
  suggested: "Suggested",
  open: "Navigation",
  session: "Sessions",
};

const SECTION_ORDER: CommandEntry["section"][] = ["suggested", "open", "session"];

// ─── Entry sources ───────────────────────────────────────────────────

function useEntries(): CommandEntry[] {
  const sessions = useStore((s) => s.sessions);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const config = useStore((s) => s.config);
  const openSettings = useStore((s) => s.openSettings);
  const openAutomations = useStore((s) => s.openAutomations);
  const openArchive = useStore((s) => s.openArchive);
  const openMemory = useStore((s) => s.openMemory);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const sidebarCollapsed = useStore((s) => s.prefs.sidebarCollapsed);
  const order = useStore((s) => s.order);

  return useMemo(() => {
    const entries: CommandEntry[] = [];

    // Suggested
    entries.push({
      id: "suggested:new-session",
      section: "suggested",
      label: "New session",
      icon: Pencil,
      shortcut: "⌘N",
      run: () => createSession(),
      search: "new session create chat",
    });
    entries.push({
      id: "suggested:toggle-sidebar",
      section: "suggested",
      label: sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar",
      icon: PanelLeft,
      shortcut: "⌘B",
      run: toggleSidebar,
      search: "sidebar panel toggle hide show",
    });
    entries.push({
      id: "suggested:compact",
      section: "suggested",
      label: "Compact context",
      icon: Sparkles,
      run: async () => {
        if (!currentSessionId) return;
        try {
          await apiWithConfig(config, "/compact", {
            method: "POST",
            body: JSON.stringify({ session_id: currentSessionId }),
          });
        } catch {
          /* surfaced via the global error path */
        }
      },
      search: "compact context summarize",
    });
    if (currentSessionId) {
      entries.push({
        id: "suggested:archive-current",
        section: "suggested",
        label: "Archive current session",
        icon: Archive,
        run: async () => {
          if (!confirm("Archive this session? You can restore it later.")) return;
          try {
            await archiveSession(currentSessionId);
          } catch {
            /* ignore */
          }
        },
        search: "archive current session",
      });
      // Branch from the most recent assistant message.
      const lastAssistant = lastAssistantId(order, useStore.getState().messages);
      if (lastAssistant) {
        entries.push({
          id: "suggested:branch-last",
          section: "suggested",
          label: "Branch from last assistant message",
          icon: GitBranch,
          run: () => branchAtMessage(lastAssistant),
          search: "branch fork split",
        });
      }
    }

    // Navigation
    entries.push({
      id: "open:memory",
      section: "open",
      label: "Memory",
      icon: Brain,
      run: openMemory,
      search: "memory facts observations patterns",
    });
    entries.push({
      id: "open:automations",
      section: "open",
      label: "Automations",
      icon: Zap,
      run: openAutomations,
      search: "automations cron scheduled",
    });
    entries.push({
      id: "open:archive",
      section: "open",
      label: "Archived sessions",
      icon: Archive,
      run: openArchive,
      search: "archive archived",
    });
    entries.push({
      id: "open:settings",
      section: "open",
      label: "Settings",
      icon: SettingsIcon,
      shortcut: "⌘,",
      run: openSettings,
      search: "settings preferences config mcp models",
    });

    // Sessions — recent first, skip the active one.
    for (const s of sessions) {
      if (s.session_id === currentSessionId) continue;
      const label = s.name?.trim() || "untitled";
      entries.push({
        id: `session:${s.session_id}`,
        section: "session",
        label,
        hint: formatRelativePast(s.last_activity),
        icon: MessageSquare,
        run: () => switchSession(s.session_id),
        search: `${label.toLowerCase()} session`,
      });
    }

    return entries;
  }, [
    sessions,
    currentSessionId,
    config,
    openSettings,
    openAutomations,
    openArchive,
    openMemory,
    toggleSidebar,
    sidebarCollapsed,
    order,
  ]);
}

function lastAssistantId(
  order: string[],
  messages: Map<string, { role: string }>,
): string | null {
  for (let i = order.length - 1; i >= 0; i--) {
    const id = order[i];
    if (messages.get(id)?.role === "assistant") return id;
  }
  return null;
}

function filterEntries(entries: CommandEntry[], query: string): CommandEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    // No query → show actions and open targets first, then a few recent
    // sessions. Keeps the default view useful as a "what can I do" list.
    const acts = entries.filter((e) => e.section !== "session");
    const sess = entries.filter((e) => e.section === "session").slice(0, 6);
    return [...acts, ...sess];
  }
  const tokens = q.split(/\s+/);
  return entries.filter((e) => tokens.every((t) => e.search.includes(t)));
}

function groupBySection(entries: CommandEntry[]): {
  section: CommandEntry["section"];
  items: CommandEntry[];
}[] {
  const buckets = new Map<CommandEntry["section"], CommandEntry[]>();
  for (const e of entries) {
    const arr = buckets.get(e.section) ?? [];
    arr.push(e);
    buckets.set(e.section, arr);
  }
  const out: { section: CommandEntry["section"]; items: CommandEntry[] }[] = [];
  for (const section of SECTION_ORDER) {
    const items = buckets.get(section);
    if (items && items.length > 0) out.push({ section, items });
  }
  return out;
}
