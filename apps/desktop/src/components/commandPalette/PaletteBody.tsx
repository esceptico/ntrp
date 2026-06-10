import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Search } from "lucide-react";
import { ICON } from "../../lib/icons";
import { useListNav } from "../../lib/hooks";
import { EASE_EMPHASIZED, MOTION } from "../../lib/tokens/motion";
import { Breadcrumbs } from "./Breadcrumbs";
import { Row } from "./Row";
import { filterEntries, groupBySection } from "./filter";
import { useEntries } from "./useEntries";
import { SECTION_LABEL, type CommandEntry, type Crumb } from "./types";
import { ScrollFadeTop } from "../ScrollBlur";
import { SLIDE_PAGE_VARIANTS } from "../ui/TabPanels";

export function PaletteBody({
  query,
  setQuery,
  index,
  setIndex,
  crumbs,
  setCrumbs,
  onClose,
  morph = false,
}: {
  query: string;
  setQuery: (q: string) => void;
  index: number;
  setIndex: React.Dispatch<React.SetStateAction<number>>;
  crumbs: Crumb[];
  setCrumbs: React.Dispatch<React.SetStateAction<Crumb[]>>;
  onClose: () => void;
  morph?: boolean;
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

  // Page identity = the crumb path. Drives the AnimatePresence swap so each
  // hierarchy level mounts as a fresh panel. `depth` alone would be ambiguous
  // if two sibling sub-views ever shared a depth; the joined id chain is exact.
  const pageKey = crumbs.length === 0 ? "root" : crumbs.map((c) => c.id).join("/");
  const depth = crumbs.length;
  const prevDepth = useRef(depth);
  const direction = depth >= prevDepth.current ? 1 : -1;
  useEffect(() => {
    prevDepth.current = depth;
  }, [depth]);

  return (
    <>
      <motion.div layout={morph} className="relative px-4 pt-3 pb-2.5">
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
            className="flex-1 min-w-0 h-8 bg-transparent text-md text-ink placeholder:text-muted outline-none"
          />
        </div>
      </motion.div>

      {/* Scroll viewport is unchanged — keyboard nav, scrollIntoView, and
          ScrollBlur (which reads parentElement) all keep seeing this div as
          the scroller. The height MORPH happens on the panel itself (see
          CommandPalette.tsx `layout`): as the page content below changes
          height, the panel's box animates to match. Inside, page content is
          swapped directionally via AnimatePresence (mode="wait" so the two
          pages never overlap inside the scroll area). Pushing into a sub-view
          enters from the right (+1), popping back from the left (-1) — the
          shared SLIDE_PAGE_VARIANTS so palette pages and tab panels stay on
          one literal. overflow-x-hidden keeps the x-slide from spawning a
          horizontal scrollbar. */}
      <motion.div
        ref={listRef}
        layout={morph}
        layoutScroll
        className="overflow-y-auto overflow-x-hidden scroll-thin pb-2"
      >
        <ScrollFadeTop />
        <AnimatePresence mode="wait" custom={direction} initial={false}>
          <motion.div
            key={pageKey}
            custom={direction}
            variants={SLIDE_PAGE_VARIANTS}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: MOTION.palette, ease: EASE_EMPHASIZED }}
          >
            {filtered.length === 0 ? (
              <div className="grid place-items-center min-h-[120px] text-sm italic text-muted">
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
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </>
  );
}
