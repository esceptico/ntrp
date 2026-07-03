import { useEffect, useMemo, useRef, useState } from "react";
import { FileText, Search } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useStore } from "@/stores";
import type { AppConfig } from "@/api/core";
import { wikiSlug, type WikiLinkHandlers } from "@/lib/wikilink";
import { SegmentedControl, SegmentedControlItem } from "@/components/ui/SegmentedControl";
import {
  listMemoryArtifacts,
  readMemoryArtifact,
  rebuildMemoryArtifacts,
  type MemoryArtifact,
} from "@/api/memoryArtifacts";
import { listMemoryItems, setRecordPinned, type MemoryItem, type MemoryKind } from "@/api/memoryItems";
import { Empty } from "@/components/ui/EmptyState";
import { ListError, ListSkeleton } from "@/components/ui/ListColumn";
import { PaneShell } from "@/components/ui/PaneShell";
import { ScrollFadeBottom } from "@/components/ui/ScrollBlur";
import { GhostBtn } from "@/features/memory/components/shared";
import { searchMatches } from "@/features/memory/lib/format";
import { FlatRow, TreeRow, TreeSearch } from "@/features/memory/components/MemoryFileTree";
import {
  buildArtifactTree,
  collectDefaultFolderPaths,
  countFiles,
  flattenTreeFiles,
} from "@/features/memory/lib/artifactTree";
import { addAlias, isMissingArtifactError, preferredAlias } from "@/features/memory/lib/wikiResolution";
import { FileDetailPane } from "@/features/memory/components/FileDetailPane";
import { RecordDetailPane } from "@/features/memory/components/RecordDetailPane";
import { RecordListPane } from "@/features/memory/components/RecordListPane";

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

  // Live vault: the server absorbed on-disk edits (Obsidian, a feed run, a
  // maintenance pass). Refetch what we're showing — silently: the list/detail
  // skeletons only render when there's nothing on screen yet.
  const memoryVaultVersion = useStore((s) => s.memoryVaultVersion);
  useEffect(() => {
    if (memoryVaultVersion === 0) return;
    void load(serverQuery);
    setContentRefreshKey((k) => k + 1);
    if (mode === "records") setRecordsRefreshKey((k) => k + 1);
  }, [memoryVaultVersion]);

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
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin px-3 pb-3 pt-1">
        <ScrollFadeBottom />
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
  const recordsList = (
    <RecordListPane
      query={query}
      onQueryChange={setQuery}
      modeToggle={modeToggle}
      recordKind={recordKind}
      onRecordKindChange={setRecordKind}
      records={records}
      recordsLoading={recordsLoading}
      recordsError={recordsError}
      selectedRecordId={selectedRecordId}
      pinningId={pinningId}
      reduce={!!reduce}
      onSelectRecord={selectRecord}
      onTogglePinned={togglePinned}
      onRetry={() => setRecordsRefreshKey((k) => k + 1)}
    />
  );

  // ─── Files detail pane ──────────────────────────────────────────────
  const filesDetail = (
    <FileDetailPane
      active={active}
      loading={loading}
      direction={filesDirection}
      contentNotice={contentNotice}
      contentError={contentError}
      contentLoading={contentLoading}
      wikiHandlers={wikiHandlers}
      onRetry={() => setContentRefreshKey((k) => k + 1)}
    />
  );

  // ─── Records detail pane ────────────────────────────────────────────
  const recordsDetail = (
    <RecordDetailPane
      record={selectedRecord}
      direction={recordsDirection}
      pinningId={pinningId}
      onTogglePinned={togglePinned}
    />
  );

  return (
    <div className="h-full min-h-0">
      <PaneShell
        fixedList
        scrollDetail={false}
        list={mode === "files" ? filesList : recordsList}
        detail={mode === "files" ? filesDetail : recordsDetail}
      />
    </div>
  );
}
