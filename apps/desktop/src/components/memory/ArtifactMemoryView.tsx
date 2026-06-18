import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Database, FileText, Folder, FolderOpen, Pin, Search, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import clsx from "clsx";
import type { AppConfig } from "../../api";
import { IconButton } from "../IconButton";
import { Markdown } from "../Markdown";
import { WikiLinkContext, wikiSlug, type WikiLinkHandlers } from "../wikilink";
import { ICON } from "../../lib/icons";
import { EASE_OUT, MOTION, RISE_IN, RISE_SETTLED, ROW_EXIT, SPRING_ROW_ENTRY, SPRING_TAP } from "../../lib/tokens/motion";
import { TabPanels } from "../ui/TabPanels";
import {
  listMemoryArtifacts,
  readMemoryArtifact,
  rebuildMemoryArtifacts,
  type MemoryArtifact,
} from "../../api/memoryArtifacts";
import { listMemoryItems, setRecordPinned, type MemoryItem, type MemoryKind } from "../../api/memoryItems";
import {
  DetailPlaceholder,
  DetailShell,
  Empty,
  GhostBtn,
  ListColumn,
  ListError,
  ListSkeleton,
  MetaGrid,
  PaneShell,
  Pill,
  relativeTime,
} from "./shared";

const RECORD_PAGE_SIZE = 100;

type MemoryViewMode = "files" | "records";

type TreeNode = {
  name: string;
  path: string;
  kind: "directory" | "file";
  artifact?: MemoryArtifact;
  children: TreeNode[];
};

const DIRECTORY_ORDER = ["memory", "facts", "entities", "projects", "sources", "files", "docs", "changelog"];

function displayFileName(a: MemoryArtifact) {
  const leaf = a.path.split("/").pop() ?? a.path;
  return leaf.replace(/\.md$/, "");
}

function displayTitle(a: MemoryArtifact) {
  return a.title || displayFileName(a);
}

function scopeLabel(scope: { kind: string; key: string | null }) {
  return scope.key ? `${scope.kind}:${scope.key}` : scope.kind;
}

// Plain user-facing words for internal kind values.
function kindLabel(kind: string) {
  return kind === "directive" ? "rule" : kind;
}

function directorySort(a: TreeNode, b: TreeNode) {
  if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1;
  const ai = DIRECTORY_ORDER.indexOf(a.name);
  const bi = DIRECTORY_ORDER.indexOf(b.name);
  return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi) || a.name.localeCompare(b.name);
}

function addNode(parent: TreeNode, parts: string[], artifact: MemoryArtifact, pathPrefix = "") {
  const [part, ...rest] = parts;
  if (!part) return;
  const nodePath = pathPrefix ? `${pathPrefix}/${part}` : part;
  if (rest.length === 0) {
    parent.children.push({ name: part, path: artifact.path, kind: "file", artifact, children: [] });
    return;
  }
  let child = parent.children.find((n) => n.kind === "directory" && n.name === part);
  if (!child) {
    child = { name: part, path: nodePath, kind: "directory", children: [] };
    parent.children.push(child);
  }
  addNode(child, rest, artifact, nodePath);
}

function buildArtifactTree(artifacts: MemoryArtifact[]) {
  const root: TreeNode = { name: "root", path: "", kind: "directory", children: [] };
  for (const artifact of artifacts) {
    const parts = artifact.path.includes("/") ? artifact.path.split("/") : ["memory", artifact.path];
    addNode(root, parts, artifact);
  }
  const sortRec = (node: TreeNode) => {
    node.children.sort(directorySort);
    node.children.forEach(sortRec);
  };
  sortRec(root);
  return root.children;
}

function collectFolderPaths(nodes: TreeNode[]): string[] {
  const out: string[] = [];
  const walk = (ns: TreeNode[]) => {
    for (const n of ns) {
      if (n.kind === "directory") {
        out.push(n.path);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return out;
}

function countFiles(node: TreeNode): number {
  if (node.kind === "file") return 1;
  return node.children.reduce((sum, child) => sum + countFiles(child), 0);
}

/** File-leaf paths in the order the tree renders them (depth-first, already
 *  directory-sorted). Drives the detail-pane slide direction so it matches the
 *  visible list position — selecting a note further down slides in from the
 *  right, further up from the left. */
function flattenTreeFiles(nodes: TreeNode[]): string[] {
  const out: string[] = [];
  const walk = (ns: TreeNode[]) => {
    for (const n of ns) {
      if (n.kind === "file") out.push(n.path);
      else walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

function searchMatches(a: MemoryArtifact, q: string) {
  return [a.path, a.title, a.kind, a.directory, ...a.labels, a.source ?? "", a.snippet ?? ""]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

// ─── Detail header bits ───────────────────────────────────────────────

function CopyPath({ path }: { path: string }) {
  const [state, setState] = useState<"idle" | "copied" | "unavailable">("idle");

  const copy = async () => {
    let ok = false;
    try {
      // Electron's native clipboard (main process) — unlike navigator.clipboard
      // it doesn't fail when the document isn't focused.
      ok = (await window.ntrpDesktop?.clipboard?.writeText(path)) ?? false;
      if (!ok && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(path);
        ok = true;
      }
    } catch {
      ok = false;
    }
    setState(ok ? "copied" : "unavailable");
    window.setTimeout(() => setState("idle"), 1200);
  };

  return (
    <GhostBtn onClick={() => void copy()}>
      {state === "copied" ? "Copied" : state === "unavailable" ? "Copy unavailable" : "Copy path"}
    </GhostBtn>
  );
}

/** Full-bleed search header with a leading icon — the file-tree variant of
 *  SearchInput's chrome, sized to the 52px list header. */
function TreeSearch({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative flex-none h-[52px] border-b border-line-soft">
      <Search
        size={ICON.XS}
        strokeWidth={2}
        className="absolute left-4 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className="h-full w-full bg-transparent pl-10 pr-9 text-sm text-ink-soft placeholder:text-muted outline-none"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2.5 top-1/2 grid size-5 -translate-y-1/2 place-items-center rounded text-faint hover:bg-surface-soft hover:text-ink"
        >
          <X size={ICON.XS} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}

// ─── Tree rows ────────────────────────────────────────────────────────

function TreeRow({
  node,
  depth,
  expanded,
  onToggle,
  selectedPath,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  const indent = depth * 14;

  if (node.kind === "directory") {
    const open = expanded.has(node.path);
    return (
      <>
        <button
          type="button"
          onClick={() => onToggle(node.path)}
          title={node.name}
          className="group mt-1 flex h-8 min-w-0 items-center gap-1.5 rounded-[10px] pl-2 pr-3 text-left transition-colors hover:bg-surface-soft"
          style={{ marginLeft: indent }}
        >
          <ChevronRight
            className={clsx("h-3 w-3 shrink-0 text-faint transition-transform duration-200", open && "rotate-90")}
            strokeWidth={2.25}
          />
          {open ? <FolderOpen className="h-3.5 w-3.5 shrink-0 text-faint" /> : <Folder className="h-3.5 w-3.5 shrink-0 text-faint" />}
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink-soft group-hover:text-ink">{node.name}</span>
          <span className="shrink-0 text-2xs tabular-nums text-faint">{countFiles(node)}</span>
        </button>
        {/* grid-rows 0fr->1fr reveal — GPU-only, no JS height measure. */}
        <div
          className={clsx(
            "grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none",
            open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
          )}
        >
          <div className="overflow-hidden">
            <div className="flex flex-col gap-px">
              {node.children.map((child) => (
                <TreeRow
                  key={child.kind === "directory" ? `d:${child.path}` : `f:${child.path}`}
                  node={child}
                  depth={depth + 1}
                  expanded={expanded}
                  onToggle={onToggle}
                  selectedPath={selectedPath}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </div>
        </div>
      </>
    );
  }

  const a = node.artifact!;
  const active = selectedPath === a.path;
  return (
    <button
      type="button"
      onClick={() => onSelect(a.path)}
      title={`${displayTitle(a)} — ${a.path}`}
      className={clsx(
        "group flex h-8 min-w-0 items-center gap-1.5 rounded-[10px] pl-2 pr-3 text-left transition-colors",
        active ? "bg-surface-sunken" : "hover:bg-surface-soft",
      )}
      style={{ marginLeft: indent }}
    >
      <span className="w-3 shrink-0" aria-hidden />
      <FileText className={clsx("h-3.5 w-3.5 shrink-0", active ? "text-muted" : "text-faint")} />
      <span
        className={clsx(
          "min-w-0 flex-1 truncate text-sm",
          active ? "font-medium text-ink" : "text-ink-soft group-hover:text-ink",
        )}
      >
        {displayFileName(a)}
      </span>
    </button>
  );
}

function FlatRow({ a, active, onSelect }: { a: MemoryArtifact; active: boolean; onSelect: (path: string) => void }) {
  const segments = a.path.split("/");
  const leaf = segments[segments.length - 1].replace(/\.md$/, "");
  const parent = segments.slice(0, -1).join(" / ");
  return (
    <button
      type="button"
      onClick={() => onSelect(a.path)}
      title={a.path}
      className={clsx(
        "group flex min-w-0 items-start gap-2 rounded-[10px] px-2.5 py-1.5 text-left transition-colors",
        active ? "bg-surface-sunken" : "hover:bg-surface-soft",
      )}
    >
      <FileText className={clsx("mt-px h-3.5 w-3.5 shrink-0", active ? "text-muted" : "text-faint")} />
      <span className="min-w-0 flex-1">
        <span className={clsx("block truncate text-sm", active ? "font-medium text-ink" : "text-ink-soft group-hover:text-ink")}>
          {leaf}
        </span>
        {parent && <span className="block truncate text-2xs text-muted">{parent}</span>}
      </span>
    </button>
  );
}

// ─── Main view ────────────────────────────────────────────────────────

export function ArtifactMemoryView({ config }: { config: AppConfig }) {
  const reduce = useReducedMotion();

  const [artifacts, setArtifacts] = useState<MemoryArtifact[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [activeArtifact, setActiveArtifact] = useState<MemoryArtifact | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
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

  // Folders default ALL-EXPANDED on first load; keep user toggles afterward.
  useEffect(() => {
    if (seededExpansion.current || tree.length === 0) return;
    seededExpansion.current = true;
    setExpanded(new Set(collectFolderPaths(tree)));
  }, [tree]);

  const selectedMeta = filtered.find((a) => a.path === selected) ?? filtered[0] ?? null;
  const active = activeArtifact?.path === selectedMeta?.path ? activeArtifact : selectedMeta;

  // [[Subject]] → a topic page, resolved against the full artifact set (not the
  // search-filtered view, so a wikilink stays navigable even while a query is
  // active — navigating clears the query so the target is visible). Subjects
  // live under entities/ AND projects/, so check both (the server emits project
  // wikilinks too, e.g. [[Project inbox]] → projects/inbox.md).
  const artifactPaths = useMemo(() => new Set(artifacts.map((a) => a.path)), [artifacts]);
  const resolveWiki = useMemo(
    () => (target: string): string | null => {
      const t = target.trim();
      // A literal artifact path: `directives.md`, `changelog/2026.md`, `facts/index.md`.
      if (artifactPaths.has(t)) return t;
      // A directory reference (`entities/`) → its index page.
      if (t.endsWith("/") && artifactPaths.has(`${t}index.md`)) return `${t}index.md`;
      // A [[Subject]] name → its topic page under entities/ or projects/.
      const slug = wikiSlug(t);
      for (const path of [`entities/${slug}.md`, `projects/${slug}.md`]) {
        if (artifactPaths.has(path)) return path;
      }
      return null;
    },
    [artifactPaths],
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
        if (!cancelled) setContentError(e instanceof Error ? e.message : String(e));
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
    setSelected(path);
  };
  const riseTransition = reduce ? { duration: 0.1 } : { duration: MOTION.panel, ease: EASE_OUT };

  // ─── Mode toggle (shared by both panes' headers) ────────────────────
  const modeToggle = (
    <div className="flex items-center gap-1 rounded-full bg-surface-soft p-0.5 text-xs">
      {(["files", "records"] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => setMode(m)}
          className={clsx(
            "relative rounded-full px-3 py-1 capitalize transition-colors",
            mode === m ? "text-ink" : "text-muted hover:text-ink",
          )}
        >
          {mode === m && (
            <motion.span
              layoutId="memoryTab"
              transition={reduce ? { duration: 0 } : SPRING_TAP}
              className="absolute inset-0 -z-10 rounded-full bg-bg shadow-sm"
            />
          )}
          {m}
        </button>
      ))}
    </div>
  );

  // ─── Files list pane ────────────────────────────────────────────────
  const filesList = (
    <>
      <TreeSearch value={query} onChange={setQuery} placeholder="Search paths, titles, snippets…" />
      <div className="flex items-center justify-between gap-2 px-3 pt-3 pb-1">
        {modeToggle}
        <GhostBtn onClick={rebuild} disabled={rebuilding} title="Regenerate memory artifacts from the record substrate">
          {rebuilding ? "Rebuilding…" : "Rebuild"}
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
            hint="Memory notes are generated from your records."
            action={
              <GhostBtn onClick={rebuild} disabled={rebuilding}>
                {rebuilding ? "Rebuilding…" : "Rebuild memory"}
              </GhostBtn>
            }
          >
            No memory notes yet
          </Empty>
        ) : (
          <div className="flex flex-col gap-px">
            {tree.map((node) => (
              <TreeRow
                key={node.kind === "directory" ? `d:${node.path}` : `f:${node.path}`}
                node={node}
                depth={0}
                expanded={expanded}
                onToggle={toggleExpanded}
                selectedPath={selectedMeta?.path ?? null}
                onSelect={selectFile}
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
              onClick={() => setSelectedRecordId(record.id)}
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
              onClick={() => togglePinned(record)}
              className={clsx("absolute right-1 top-1", record.pinned ? "opacity-100" : "opacity-0 group-hover/row:opacity-100")}
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
      <DetailPlaceholder>{""}</DetailPlaceholder>
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
              <Markdown content={active.content} className="max-w-none" />
            </WikiLinkContext.Provider>
          )}
        </>
      }
      meta={
        <MetaGrid
          rows={[
            { label: "Kind", value: kindLabel(active.kind) },
            { label: "Scope", value: scopeLabel(active.scope) },
            { label: "Updated", value: relativeTime(active.updated_at) },
            active.record_count !== null && { label: "Records", value: String(active.record_count) },
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
        <motion.div
          key={selectedRecord.id}
          initial={reduce ? false : RISE_IN}
          animate={RISE_SETTLED}
          transition={riseTransition}
          className="min-w-0 whitespace-pre-wrap break-words text-base leading-relaxed text-ink"
        >
          {selectedRecord.content}
        </motion.div>
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
