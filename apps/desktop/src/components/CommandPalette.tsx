import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import {
  Archive,
  Bot,
  Brain,
  ChevronRight,
  GitBranch,
  Layers,
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
import {
  archiveSession,
  branchAtMessage,
  createSession,
  switchSession,
  updateServerConfig,
} from "../actions";
import { apiWithConfig } from "../api";
import { formatRelativePast } from "../lib/format";
import { ICON } from "../lib/icons";
import { EASE_EMPHASIZED, EASE_OUT, MOTION } from "../lib/motion";

const BACKDROP_DURATION = 0.16;
const PANEL_DURATION = 0.18;
const EASE = EASE_OUT;

/** A palette entry. Either an executable leaf (`run`) or a folder
 *  (`children`) that opens a sub-view via breadcrumb drill-down. */
interface CommandEntry {
  id: string;
  section: "suggested" | "open" | "session" | "provider" | "model";
  label: string;
  hint?: string;
  shortcut?: string;
  icon: LucideIcon;
  /** Leaf action. Mutually exclusive with `children`. */
  run?: () => void | Promise<void>;
  /** Folder. Returning a view defers entries until drilled into. */
  children?: () => CommandView;
  /** Lower-cased haystack used for fuzzy matching. */
  search: string;
}

/** One level of the drill-down tree. `placeholder` swaps the input
 *  placeholder so the user knows what to type for. The crumb chip
 *  itself reuses the parent entry's label — no separate copy. */
interface CommandView {
  placeholder: string;
  entries: CommandEntry[];
}

interface Crumb {
  id: string;
  label: string;
}

export function CommandPalette() {
  const open = useStore((s) => s.paletteOpen);
  const close = useStore((s) => s.closePalette);
  const togglePalette = useStore((s) => s.togglePalette);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);

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
      setCrumbs([]);
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
            className="glass-pane-thick w-[min(660px,calc(100vw-80px))] max-h-[62vh] grid grid-rows-[auto_minmax(0,1fr)] rounded-[16px] overflow-hidden origin-top"
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
              crumbs={crumbs}
              setCrumbs={setCrumbs}
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
  crumbs,
  setCrumbs,
  onClose,
}: {
  query: string;
  setQuery: (q: string) => void;
  index: number;
  setIndex: (n: number) => void;
  crumbs: Crumb[];
  setCrumbs: React.Dispatch<React.SetStateAction<Crumb[]>>;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const activeRowRef = useRef<HTMLButtonElement>(null);
  const rootEntries = useEntries();

  // Resolve the active view by following the crumb path from root.
  // If any segment goes stale (e.g. server data refreshed and an entry
  // disappeared), we collapse back to root rather than show a dead view.
  const { view, staleCrumbs } = useMemo(() => {
    let entries = rootEntries;
    let placeholder = "Search commands, sessions, memory...";
    for (let i = 0; i < crumbs.length; i++) {
      const crumb = crumbs[i];
      const folder = entries.find((e) => e.id === crumb.id && e.children);
      if (!folder || !folder.children) {
        return {
          view: { placeholder, entries: rootEntries },
          staleCrumbs: true,
        };
      }
      const next = folder.children();
      entries = next.entries;
      placeholder = next.placeholder;
    }
    return {
      view: { placeholder, entries },
      staleCrumbs: false,
    };
  }, [rootEntries, crumbs]);

  // Drop stale path silently — caller never sees the inconsistency.
  useEffect(() => {
    if (staleCrumbs) setCrumbs([]);
  }, [staleCrumbs, setCrumbs]);

  const filtered = useMemo(() => filterEntries(view.entries, query), [view.entries, query]);
  const safe = Math.min(index, Math.max(0, filtered.length - 1));

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Reset index when filter or path changes.
  useEffect(() => {
    setIndex(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, crumbs.length]);

  // Clear stale query when descending into a sub-view — otherwise the
  // user's "switch model" query immediately filters the provider list
  // to nothing.
  const pushCrumb = useCallback(
    (entry: CommandEntry) => {
      setCrumbs((prev) => [...prev, { id: entry.id, label: entry.label }]);
      setQuery("");
    },
    [setCrumbs, setQuery],
  );

  const popCrumb = useCallback(() => {
    setCrumbs((prev) => (prev.length === 0 ? prev : prev.slice(0, -1)));
    setQuery("");
  }, [setCrumbs, setQuery]);

  const popTo = useCallback(
    (depth: number) => {
      setCrumbs((prev) => (prev.length <= depth ? prev : prev.slice(0, depth)));
      setQuery("");
    },
    [setCrumbs, setQuery],
  );

  // Keep the highlighted row in view while arrow-navigating.
  useEffect(() => {
    activeRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [safe]);

  const grouped = useMemo(() => groupBySection(filtered), [filtered]);

  function activate(entry: CommandEntry) {
    if (entry.children) {
      pushCrumb(entry);
      return;
    }
    if (entry.run) {
      onClose();
      void entry.run();
    }
  }

  return (
    <>
      <div className="relative px-4 pt-3 pb-2.5">
        <Search
          size={ICON.MD}
          strokeWidth={2}
          className="absolute left-4 top-[22px] text-faint pointer-events-none"
        />
        <div className="flex items-center gap-1.5 pl-6">
          <Breadcrumbs crumbs={crumbs} onJump={popTo} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Backspace" && query.length === 0 && crumbs.length > 0) {
                e.preventDefault();
                popCrumb();
                return;
              }
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
                activate(filtered[safe]);
              }
            }}
            placeholder={view.placeholder}
            spellCheck={false}
            className="flex-1 min-w-0 h-8 bg-transparent text-md text-ink placeholder:text-faint outline-none"
          />
        </div>
      </div>

      <div ref={listRef} className="overflow-y-auto scroll-thin pb-2 border-t border-line-soft/60">
        {filtered.length === 0 ? (
          <div className="grid place-items-center min-h-[120px] text-sm italic text-faint">
            Nothing matches.
          </div>
        ) : (
          grouped.map(({ section, items }) => (
            <div key={section}>
              <div className="px-4 pt-3 pb-1 text-2xs font-medium uppercase tracking-[0.10em] text-faint">
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
                      onClick={() => activate(entry)}
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

/** Breadcrumb trail rendered inline with the input. Each chip pops the
 *  stack back to that depth. Animates in with a tiny stagger and slides
 *  from -4px; popping reverses via AnimatePresence. */
function Breadcrumbs({
  crumbs,
  onJump,
}: {
  crumbs: Crumb[];
  onJump: (depth: number) => void;
}) {
  if (crumbs.length === 0) return null;
  return (
    <div className="flex items-center gap-1 shrink-0">
      <AnimatePresence initial={false} mode="popLayout">
        {crumbs.map((crumb, i) => (
          <motion.div
            key={`${i}:${crumb.id}`}
            layout
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -4 }}
            transition={{
              duration: MOTION.check,
              ease: EASE_EMPHASIZED,
              delay: i * 0.02,
            }}
            className="flex items-center gap-1"
          >
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onJump(i)}
              className="h-6 px-2 rounded-[6px] bg-surface-soft text-xs text-ink-soft hover:text-ink hover:bg-surface-sunken transition-colors whitespace-nowrap"
            >
              {crumb.label}
            </button>
            <ChevronRight
              size={ICON.XS}
              strokeWidth={2}
              className="text-faint shrink-0"
              aria-hidden
            />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
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
        onMouseDown={(e) => e.preventDefault()}
        onClick={onClick}
        data-active={active ? "true" : undefined}
        className="app-row w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-[8px] text-ink-soft text-left"
      >
        <span
          className={clsx(
            "grid place-items-center w-5 h-5 rounded-md shrink-0 transition-colors",
            active ? "bg-accent-soft text-accent-strong" : "text-muted",
          )}
        >
          <Icon size={ICON.SM} strokeWidth={2} />
        </span>
        <span className="text-base text-ink truncate flex-1">{entry.label}</span>
        {entry.hint && (
          <span className="text-xs text-faint tabular-nums shrink-0">{entry.hint}</span>
        )}
        {entry.shortcut && (
          <kbd className="text-2xs text-faint font-mono shrink-0 ml-1">{entry.shortcut}</kbd>
        )}
        {entry.children && (
          <ChevronRight
            size={ICON.XS}
            strokeWidth={2}
            className="text-faint shrink-0 ml-1"
            aria-hidden
          />
        )}
      </button>
    </li>
  );
}

const SECTION_LABEL: Record<CommandEntry["section"], string> = {
  suggested: "Suggested",
  open: "Navigation",
  session: "Sessions",
  provider: "Providers",
  model: "Models",
};

const SECTION_ORDER: CommandEntry["section"][] = [
  "suggested",
  "open",
  "provider",
  "model",
  "session",
];

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
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const order = useStore((s) => s.order);
  const serverModels = useStore((s) => s.serverModels);
  const serverConfig = useStore((s) => s.serverConfig);
  const currentChatModel = serverConfig?.chat_model;

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
      label: sidebarHidden ? "Show sidebar" : "Hide sidebar",
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

    // Switch model — drill-down. Hidden when /models hasn't returned
    // anything yet so the chevron doesn't lie about navigable content.
    if (serverModels && serverModels.groups.length > 0) {
      entries.push({
        id: "open:switch-model",
        section: "open",
        label: "Switch model",
        hint: currentChatModel,
        icon: Bot,
        children: () => buildProviderView(serverModels.groups, currentChatModel),
        search: "switch model chat provider anthropic openai",
      });
    }

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
    sidebarHidden,
    order,
    serverModels,
    currentChatModel,
  ]);
}

/** Provider-level view: one row per provider, drills into model list. */
function buildProviderView(
  groups: { provider: string; models: string[] }[],
  currentModel: string | undefined,
): CommandView {
  return {
    placeholder: "Filter providers...",
    entries: groups.map((g) => ({
      id: `provider:${g.provider}`,
      section: "provider" as const,
      label: prettyProvider(g.provider),
      hint: `${g.models.length} model${g.models.length === 1 ? "" : "s"}`,
      icon: Layers,
      children: () => buildModelView(g.provider, g.models, currentModel),
      search: `${g.provider.toLowerCase()} provider`,
    })),
  };
}

/** Model-level view: leaf rows that apply chat_model on Enter. */
function buildModelView(
  provider: string,
  models: string[],
  currentModel: string | undefined,
): CommandView {
  return {
    placeholder: `Filter ${prettyProvider(provider)} models...`,
    entries: models.map((model) => ({
      id: `model:${model}`,
      section: "model" as const,
      label: stripProviderPrefix(model, provider),
      hint: model === currentModel ? "current" : undefined,
      icon: Bot,
      run: async () => {
        if (model === currentModel) return;
        try {
          await updateServerConfig({ chat_model: model });
        } catch {
          /* surfaced via the global error path */
        }
      },
      search: `${model.toLowerCase()} model`,
    })),
  };
}

function prettyProvider(provider: string): string {
  if (!provider) return "Unknown";
  if (provider === "openai") return "OpenAI";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function stripProviderPrefix(model: string, provider: string): string {
  const prefix = `${provider}/`;
  return model.startsWith(prefix) ? model.slice(prefix.length) : model;
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
