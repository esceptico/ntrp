import { useEffect, useMemo, useRef, useState } from "react";
import { Database, FileText, Pin, Search } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import clsx from "clsx";
import type { AppConfig } from "@/api/core";
import { IconButton } from "@/components/ui/IconButton";
import { Markdown } from "@/components/ui/Markdown";
import { WikiLinkContext, wikiSlug, type WikiLinkHandlers } from "@/lib/wikilink";
import { RISE_IN, RISE_SETTLED, ROW_EXIT, SPRING_ROW_ENTRY } from "@/lib/tokens/motion";
import { SegmentedControl, SegmentedControlItem } from "@/components/ui/SegmentedControl";
import { TabPanels } from "@/components/ui/TabPanels";
import {
  listMemoryArtifacts,
  readMemoryArtifact,
  rebuildMemoryArtifacts,
  type MemoryArtifact,
} from "@/api/memoryArtifacts";
import { listMemoryItems, setRecordPinned, type MemoryItem, type MemoryKind } from "@/api/memoryItems";
import { DetailPlaceholder, Empty } from "@/components/ui/EmptyState";
import { DetailShell } from "@/components/ui/DetailShell";
import { ListColumn, ListError, ListSkeleton } from "@/components/ui/ListColumn";
import { MetaGrid } from "@/components/ui/MetaGrid";
import { PaneShell } from "@/components/ui/PaneShell";
import { Pill } from "@/components/ui/Pill";
import { GhostBtn, Properties, relativeTime } from "@/features/memory/components/shared";
import {
  displayTitle,
  isRecordListPage,
  kindLabel,
  scopeLabel,
  searchMatches,
  stripCites,
  stripLeadingH1,
} from "@/features/memory/lib/format";
import { TimelineDisclosure } from "@/features/memory/components/MemoryTimelineDisclosure";
import { FlatRow, TreeRow, TreeSearch } from "@/features/memory/components/MemoryFileTree";
import {
  buildArtifactTree,
  collectDefaultFolderPaths,
  countFiles,
  flattenTreeFiles,
} from "@/features/memory/lib/artifactTree";
import { addAlias, isMissingArtifactError, preferredAlias } from "@/features/memory/lib/wikiResolution";
import { CopyPath } from "@/features/memory/components/CopyPath";

const RECORD_PAGE_SIZE = 100;

type MemoryViewMode = "files" | "records";

// ─── Main view ────────────────────────────────────────────────────────

export function ArtifactMemoryView({ config }: { config: AppConfig }) {
  const reduce = useReducedMotion();

  const [artifacts, setArtifacts] = useState<MemoryArtifact[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [activeArtifact, setActiveArtifact] = useState<MemoryArtifact | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [contentNotice, setContentNotice] = useState<string | null>(null);
  const [contentRefreshKey, setContentRefreshKey] = useState(0);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<MemoryViewMode>("files");
  const [records, setRecords] = useState<MemoryItem[]>([]);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordKind, setRecordKind] = useState<MemoryKind | "">("");
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [pinningId, setPinningId] = useState<string | null>(null);
  const [serverQuery, setServerQuery] = useState("");
  const [recordsRefreshKey, setRecordsRefreshKey] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [filesDirection, setFilesDirection] = useState(1);
  const [recordsDirection, setRecordsDirection] = useState(1);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadRequestId = useRef(0);
  const recordsRequestId = useRef(0);
  const seededExpansion = useRef(false);

  const load = (q = serverQuery) => {
    const requestId = ++loadRequestId.current;
    setLoading(true);
    setError(null);
    return listMemoryArtifacts(config, { q: q || undefined })
      .then((r) => {
        if (requestId !== loadRequestId.current) return [];
        setArtifacts(r.artifacts);
        setSelected((prev) => (prev && r.artifacts.some((a) => a.path === prev) ? prev : r.artifacts[0]?.path ?? null));
        return r.artifacts;
      })
      .catch((e) => {
        if (requestId !== loadRequestId.current) return [];
        setError(e instanceof Error ? e.message : String(e));
        return [];
      })
      .finally(() => {
        if (requestId === loadRequestId.current) setLoading(false);
      });
  };

  useEffect(() => {
    const t = window.setTimeout(() => setServerQuery(query.trim()), 180);
    return () => window.clearTimeout(t);
  }, [query]);

  useEffect(() => {
    void load(serverQuery);
  }, [config, serverQuery]);

  useEffect(() => {
    if (mode !== "records") return;
    const requestId = ++recordsRequestId.current;
    setRecordsLoading(true);
    setRecordsError(null);
    listMemoryItems(config, {
      limit: RECORD_PAGE_SIZE,
      offset: 0,
      q: query.trim() || undefined,
      kind: recordKind || undefined,
      status: "active",
    })
      .then((res) => {
        if (recordsRequestId.current === requestId) {
          setRecords(res.items);
          setSelectedRecordId((prev) => (prev && res.items.some((item) => item.id === prev) ? prev : res.items[0]?.id ?? null));
        }
      })
      .catch((err) => {
        if (recordsRequestId.current === requestId) setRecordsError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (recordsRequestId.current === requestId) setRecordsLoading(false);
      });
  }, [config, mode, query, recordKind, recordsRefreshKey]);

  const trimmedQuery = query.trim().toLowerCase();

  const filtered = useMemo(() => {
    if (!trimmedQuery) return artifacts;
    // Once the debounced server content search has caught up, trust its result
    // set — re-filtering hides matches whose term only appears in full content.
    if (serverQuery.toLowerCase() === trimmedQuery) return artifacts;
    return artifacts.filter((a) => searchMatches(a, trimmedQuery));
  }, [artifacts, trimmedQuery, serverQuery]);

  const tree = useMemo(() => buildArtifactTree(filtered), [filtered]);

  // Search-active → flat filtered list (leaf + dimmed parent path).
  const flatMatches = useMemo(() => {
    if (!trimmedQuery) return null;
    return [...filtered].sort((a, b) => a.path.localeCompare(b.path));
  }, [filtered, trimmedQuery]);

  // Default-open only hot context folders; changelog/references stay collapsed
  // until the user asks for provenance or audit history.
  useEffect(() => {
    if (seededExpansion.current || tree.length === 0) return;
    seededExpansion.current = true;
    setExpanded(new Set(collectDefaultFolderPaths(tree)));
  }, [tree]);

  const selectedMeta = filtered.find((a) => a.path === selected) ?? filtered[0] ?? null;
  const active = activeArtifact?.path === selectedMeta?.path ? activeArtifact : selectedMeta;

  // [[Subject]] → a generated note, resolved against the full artifact set
  // (not the search-filtered view, so links remain navigable while searching).
  // Accept exact paths, directory indexes, titles, slugs, and file stems.
  const artifactPaths = useMemo(() => new Set(artifacts.map((a) => a.path)), [artifacts]);
  const artifactAliasMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const artifact of artifacts) {
      const path = artifact.path;
      const leaf = path.split("/").pop()?.replace(/\.md$/, "") ?? path;
      addAlias(map, path, path);
      addAlias(map, path.replace(/\.md$/, ""), path);
      addAlias(map, artifact.title, path);
      addAlias(map, wikiSlug(artifact.title), path);
      addAlias(map, leaf, path);
      addAlias(map, wikiSlug(leaf), path);
    }
    return map;
  }, [artifacts]);
  const resolveWiki = useMemo(
    () => (target: string): string | null => {
      const t = target.trim();
      // A literal artifact path: `directives.md`, `changelog/2026.md`, `facts/index.md`.
      if (artifactPaths.has(t)) return t;
      // A directory reference (`entities/` or `entities`) → its index page.
      const directory = t.replace(/\/+$/, "");
      if (directory && artifactPaths.has(`${directory}/index.md`)) return `${directory}/index.md`;
      const exact = preferredAlias(artifactAliasMap, t);
      if (exact) return exact;
      const slug = preferredAlias(artifactAliasMap, wikiSlug(t));
      if (slug) return slug;
      return null;
    },
    [artifactAliasMap, artifactPaths],
  );
  const wikiHandlers = useMemo<WikiLinkHandlers>(
    () => ({
      exists: (target) => resolveWiki(target) !== null,
      onNavigate: (target) => {
        const path = resolveWiki(target);
        if (!path) return;
        setQuery("");
        setSelected(path);
      },
    }),
    [resolveWiki],
  );

  useEffect(() => {
    let cancelled = false;
    if (!selectedMeta) {
      setActiveArtifact(null);
      return;
    }
    setContentLoading(true);
    setContentError(null);
    readMemoryArtifact(config, selectedMeta.path)
      .then((r) => {
        if (!cancelled) setActiveArtifact(r.artifact);
      })
      .catch((e) => {
        if (cancelled) return;
        if (isMissingArtifactError(e)) {
          const missingPath = selectedMeta.path;
          setArtifacts((prev) => prev.filter((artifact) => artifact.path !== missingPath));
          setSelected((prev) => (prev === missingPath ? null : prev));
          setActiveArtifact(null);
          setContentNotice("That generated memory note changed or disappeared; refreshed the list.");
          void load(serverQuery);
          return;
        }
        setContentError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, selectedMeta?.path, contentRefreshKey]);

  const toggleExpanded = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const selectedRecord = records.find((record) => record.id === selectedRecordId) ?? records[0] ?? null;

  const togglePinned = (record: MemoryItem) => {
    const next = !record.pinned;
    setPinningId(record.id);
    setRecords((prev) => prev.map((r) => (r.id === record.id ? { ...r, pinned: next } : r)));
    setRecordPinned(config, record.id, next)
      .catch((e) => {
        setRecords((prev) => prev.map((r) => (r.id === record.id ? { ...r, pinned: record.pinned } : r)));
        setRecordsError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setPinningId((id) => (id === record.id ? null : id)));
  };

  const rebuild = () => {
    const selectedBefore = selected;
    setRebuilding(true);
    setContentNotice(null);
    rebuildMemoryArtifacts(config)
      .then(() => load(serverQuery))
      .then((refreshed) => {
        const nextSelected = selectedBefore && refreshed.some((a) => a.path === selectedBefore) ? selectedBefore : refreshed[0]?.path ?? null;
        setSelected(nextSelected);
        setActiveArtifact(null);
        setContentRefreshKey((key) => key + 1);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setRebuilding(false));
  };

  const filesOrder = useMemo(
    () => (flatMatches ? flatMatches.map((a) => a.path) : flattenTreeFiles(tree)),
    [flatMatches, tree],
  );
  const selectFile = (path: string) => {
    const from = filesOrder.indexOf(selectedMeta?.path ?? selected ?? "");
    const to = filesOrder.indexOf(path);
    if (from !== -1 && to !== -1 && from !== to) setFilesDirection(to > from ? 1 : -1);
    setContentNotice(null);
    setSelected(path);
  };
  const selectRecord = (id: string) => {
    const order = records.map((r) => r.id);
    const from = order.indexOf(selectedRecord?.id ?? "");
    const to = order.indexOf(id);
    if (from !== -1 && to !== -1 && from !== to) setRecordsDirection(to > from ? 1 : -1);
    setSelectedRecordId(id);
  };

  // ─── Mode toggle (shared by both panes' headers) ────────────────────
  const modeToggle = (
    <SegmentedControl
      size="sm"
      value={mode}
      onChange={(v) => setMode(v as MemoryViewMode)}
    >
      <SegmentedControlItem value="files">Files</SegmentedControlItem>
      <SegmentedControlItem value="records">Records</SegmentedControlItem>
    </SegmentedControl>
  );

  // ─── Files list pane ────────────────────────────────────────────────
  const filesList = (
    <>
      <TreeSearch value={query} onChange={setQuery} placeholder="Search paths, titles, snippets…" />
      <div className="flex items-center justify-between gap-2 px-3 pt-3 pb-1">
        {modeToggle}
        <GhostBtn onClick={rebuild} disabled={rebuilding} title="Reload memory pages from disk (pick up edits made in Obsidian)">
          {rebuilding ? "Reloading…" : "Reload"}
        </GhostBtn>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin scroll-fade-bottom px-3 pb-3 pt-1">
        {loading && artifacts.length === 0 ? (
          <ListSkeleton />
        ) : error ? (
          <div className="px-1 py-3">
            <ListError title="Couldn't load memory artifacts" message={error} onRetry={() => void load(serverQuery)} />
          </div>
        ) : flatMatches !== null ? (
          flatMatches.length === 0 ? (
            <Empty
              icon={Search}
              hint={<>No memory notes match “{query.trim()}”.</>}
              action={
                <GhostBtn onClick={() => setQuery("")}>Clear search</GhostBtn>
              }
            >
              No matches
            </Empty>
          ) : (
            <div className="flex flex-col gap-px">
              {flatMatches.map((a) => (
                <FlatRow key={a.path} a={a} active={selectedMeta?.path === a.path} onSelect={selectFile} />
              ))}
            </div>
          )
        ) : tree.length === 0 ? (
          <Empty
            icon={FileText}
            hint="Memory pages are written as you chat and synthesized nightly."
            action={
              <GhostBtn onClick={rebuild} disabled={rebuilding}>
                {rebuilding ? "Reloading…" : "Reload"}
              </GhostBtn>
            }
          >
            No memory notes yet
          </Empty>
        ) : (
          <div role="tree" aria-label="Memory notes" className="flex flex-col gap-px">
            {tree.map((node) => (
              <TreeRow
                key={node.kind === "directory" ? `d:${node.path}` : `f:${node.path}`}
                node={node}
                depth={0}
                expanded={expanded}
                onToggle={toggleExpanded}
                selectedPath={selectedMeta?.path ?? null}
                onSelect={selectFile}
                reduce={!!reduce}
                countFiles={countFiles}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );

  // ─── Records list pane ──────────────────────────────────────────────
  const recordKindToolbar = (
    <select
      value={recordKind}
      onChange={(e) => setRecordKind(e.target.value as MemoryKind | "")}
      aria-label="Filter by record kind"
      className="h-7 rounded-[10px] bg-surface-soft px-2 text-sm text-ink-soft outline-none"
    >
      <option value="">All kinds</option>
      <option value="fact">Facts</option>
      <option value="directive">Rules</option>
      <option value="source">Sources</option>
    </select>
  );

  const recordsList = (
    <>
      <TreeSearch value={query} onChange={setQuery} placeholder="Search raw DB facts/records…" />
      <div className="flex items-center justify-between gap-2 px-3 pt-3 pb-1">
        {modeToggle}
        {recordKindToolbar}
      </div>
      <ListColumn
        toolbar={null}
        items={records}
        loading={recordsLoading}
        skeleton
        error={
          recordsError ? (
            <ListError
              title="Couldn't load memory records"
              message={recordsError}
              onRetry={() => setRecordsRefreshKey((k) => k + 1)}
            />
          ) : undefined
        }
        empty={query.trim() ? "No records match your search" : "No memory records yet"}
        emptyIcon={query.trim() ? Search : Database}
        emptyAction={query.trim() ? <GhostBtn onClick={() => setQuery("")}>Clear search</GhostBtn> : undefined}
        totalLabel={records.length ? `${records.length} records` : null}
        wrapItems={(children) => <AnimatePresence initial={false}>{children}</AnimatePresence>}
        renderItem={(record) => (
          <motion.li
            key={record.id}
            layout={!reduce}
            initial={reduce ? false : RISE_IN}
            animate={RISE_SETTLED}
            exit={reduce ? { opacity: 0 } : ROW_EXIT}
            transition={SPRING_ROW_ENTRY}
            className="group/row relative"
          >
            <button
              type="button"
              onClick={() => selectRecord(record.id)}
              className={clsx(
                "w-full rounded-[10px] p-2 pr-7 text-left transition-colors",
                selectedRecordId === record.id ? "bg-surface-sunken" : "hover:bg-surface-soft",
              )}
            >
              <div className="line-clamp-2 text-sm text-ink">{record.content}</div>
              <div className="mt-1.5 flex items-center gap-1.5 text-2xs text-muted">
                <span className="font-medium">{kindLabel(record.kind)}</span>
                {record.scope?.kind && record.scope.kind !== "global" && (
                  <>
                    <span className="text-faint">·</span>
                    <span>{scopeLabel(record.scope)}</span>
                  </>
                )}
                {record.pinned && (
                  <>
                    <span className="text-faint">·</span>
                    <span>pinned</span>
                  </>
                )}
                <span className="text-faint">·</span>
                <span className="tabular-nums">{relativeTime(record.updated_at)}</span>
              </div>
            </button>
            <IconButton
              size="xs"
              tone="faint"
              disabled={pinningId === record.id}
              title={record.pinned ? "Unpin — drop from always-on Profile" : "Pin — always keep in context"}
              aria-label={record.pinned ? "Unpin — drop from always-on Profile" : "Pin — always keep in context"}
              aria-pressed={record.pinned}
              onClick={() => togglePinned(record)}
              className={clsx("absolute right-1 top-1 focus-visible:opacity-100", record.pinned ? "opacity-100" : "opacity-0 group-hover/row:opacity-100 group-focus-within/row:opacity-100")}
            >
              <Pin className="h-3.5 w-3.5" fill={record.pinned ? "currentColor" : "none"} strokeWidth={2} />
            </IconButton>
          </motion.li>
        )}
      />
    </>
  );

  // ─── Files detail pane ──────────────────────────────────────────────
  const filesDetail = !active ? (
    loading ? (
      <DetailPlaceholder>Loading…</DetailPlaceholder>
    ) : (
      <DetailPlaceholder icon={FileText} hint="Pick a note from the list to read it.">
        Nothing selected
      </DetailPlaceholder>
    )
  ) : (
    <TabPanels
      value={active.path}
      direction={filesDirection}
      className="h-full min-h-0 grid-rows-[minmax(0,1fr)] overflow-hidden"
    >
    <DetailShell
      header={
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-medium tracking-tight text-ink truncate">{displayTitle(active)}</h1>
            <div className="mt-1 font-mono text-xs text-muted break-all">{active.path}</div>
          </div>
          <CopyPath path={active.path} />
        </div>
      }
      body={
        <>
          {active.readonly_reason && (
            <div className="mb-4 rounded-[10px] bg-surface-soft px-3 py-2 text-sm text-muted">
              {active.readonly_reason}
            </div>
          )}
          {contentNotice && (
            <div className="mb-4 rounded-[10px] bg-surface-soft px-3 py-2 text-sm text-muted">
              {contentNotice}
            </div>
          )}
          {contentError && !active.content ? (
            <ListError
              title="Couldn't load this note"
              message={contentError}
              onRetry={() => setContentRefreshKey((k) => k + 1)}
            />
          ) : contentLoading && !active.content ? (
            <DetailPlaceholder>Loading artifact…</DetailPlaceholder>
          ) : (
            <WikiLinkContext.Provider value={wikiHandlers}>
              <Properties frontmatter={active.frontmatter} />
              <Markdown content={stripLeadingH1(stripCites(active.content))} className="max-w-none" />
              {/* Record-list pages (directives/lessons/references/insights) already render
                  their records as the body — don't repeat them in the timeline disclosure. */}
              {!isRecordListPage(active.path) && <TimelineDisclosure timeline={active.timeline} />}
            </WikiLinkContext.Provider>
          )}
        </>
      }
      meta={
        <MetaGrid
          rows={[
            // record count lives in the Timeline disclosure header — don't repeat it here
            !!active.source && { label: "Source", value: active.source! },
            !active.editable && { label: "Access", value: "read-only" },
          ]}
        />
      }
      actions={
        active.labels.length > 0 ? (
          <div className="mr-auto flex flex-wrap items-center gap-1">
            {active.labels.map((label) => (
              <Pill key={label} tone="neutral">
                {label}
              </Pill>
            ))}
          </div>
        ) : null
      }
    />
    </TabPanels>
  );

  // ─── Records detail pane ────────────────────────────────────────────
  const recordsDetail = !selectedRecord ? (
    <DetailPlaceholder icon={Database} hint="Pick a record from the list to inspect it.">
      Nothing selected
    </DetailPlaceholder>
  ) : (
    <TabPanels
      value={selectedRecord.id}
      direction={recordsDirection}
      className="h-full min-h-0 grid-rows-[minmax(0,1fr)] overflow-hidden"
    >
    <DetailShell
      header={
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-medium capitalize tracking-tight text-ink">{kindLabel(selectedRecord.kind)}</h1>
            <div className="mt-1 font-mono text-xs text-muted break-all">{selectedRecord.id}</div>
          </div>
          <GhostBtn
            onClick={() => togglePinned(selectedRecord)}
            disabled={pinningId === selectedRecord.id}
            title={selectedRecord.pinned ? "Drop from the always-on Profile block" : "Always keep this record in context"}
          >
            <Pin className="h-3.5 w-3.5" fill={selectedRecord.pinned ? "currentColor" : "none"} strokeWidth={2} />
            {selectedRecord.pinned ? "Pinned" : "Pin"}
          </GhostBtn>
        </div>
      }
      body={
        <div className="min-w-0 whitespace-pre-wrap break-words text-base leading-relaxed text-ink">
          {selectedRecord.content}
        </div>
      }
      meta={
        <MetaGrid
          rows={[
            { label: "Kind", value: kindLabel(selectedRecord.kind) },
            { label: "Scope", value: scopeLabel(selectedRecord.scope) },
            { label: "Status", value: selectedRecord.status },
            { label: "Updated", value: relativeTime(selectedRecord.updated_at) },
            selectedRecord.source_refs.length > 0 && {
              label: "Sources",
              value: selectedRecord.source_refs.map((s) => `${s.kind}: ${s.ref}`).join("\n"),
              mono: true,
            },
          ]}
        />
      }
      actions={
        selectedRecord.labels.length > 0 ? (
          <div className="mr-auto flex flex-wrap items-center gap-1">
            {selectedRecord.labels.map((label) => (
              <Pill key={label} tone="neutral">
                {label}
              </Pill>
            ))}
          </div>
        ) : null
      }
    />
    </TabPanels>
  );

  return (
    <div className="h-full min-h-0 border-t border-line-soft">
      <PaneShell
        fixedList
        scrollDetail={false}
        list={mode === "files" ? filesList : recordsList}
        detail={mode === "files" ? filesDetail : recordsDetail}
      />
    </div>
  );
}
