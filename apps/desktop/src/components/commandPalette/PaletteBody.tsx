import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { Search } from "lucide-react";
import { ICON } from "../../lib/icons";
import { useListNav } from "../../lib/hooks";
import { Breadcrumbs } from "./Breadcrumbs";
import { Row } from "./Row";
import { filterEntries, groupBySection } from "./filter";
import { useEntries } from "./useEntries";
import { SECTION_LABEL, type CommandEntry, type Crumb } from "./types";

export function PaletteBody({
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
  setIndex: React.Dispatch<React.SetStateAction<number>>;
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

  const nav = useListNav(
    filtered.length,
    (i) => {
      const entry = filtered[i];
      if (entry) activate(entry);
    },
    { index, setIndex },
  );
  const safe = nav.index;

  // Keep the highlighted row in view while arrow-navigating.
  useLayoutEffect(() => {
    activeRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [safe]);

  const grouped = useMemo(() => groupBySection(filtered), [filtered]);

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
              nav.onKeyDown(e);
            }}
            placeholder={view.placeholder}
            spellCheck={false}
            className="flex-1 min-w-0 h-8 bg-transparent text-md text-ink placeholder:text-faint outline-none"
          />
        </div>
      </div>

      <div ref={listRef} className="overflow-y-auto scroll-thin scroll-fade-top pb-2">
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
