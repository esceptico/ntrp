import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { SPRING_MODAL } from "../../lib/tokens/motion";
import {
  approveLensProposal,
  approveMemoryProposal,
  deleteLens,
  deleteMemoryItem,
  generateLens,
  getMemoryGlobalGraph,
  getMemoryItem,
  getMemoryToday,
  listLensProposals,
  listMemoryDirectories,
  listMemoryItems,
  listMemorySkills,
  rejectLensProposal,
  rejectMemoryProposal,
  runLensPass,
  setMemorySkillEnabled,
  updateLens,
  updateMemoryItem,
  type LensProposal,
  type MemoryDirectory,
  type MemoryGlobalGraph,
  type MemoryItemDetail,
  type MemoryItemKind,
  type MemoryItemStatus,
  type MemoryItemSummary,
  type MemoryParentRole,
  type MemoryToday,
  type MemoryValidityFilter,
} from "../../api/memoryItems";
import type { AppConfig } from "../../api";
import { useStore } from "../../store";
import { KIND_COLOR, MemoryGraph, type CenterRequest } from "./MemoryGraph";

export interface Connection {
  item: MemoryItemSummary;
  role: MemoryParentRole;
  direction: "parent" | "child";
}
import {
  DangerBtn,
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ErrorPill,
  GhostBtn,
  ListColumn,
  ListError,
  MetaGrid,
  PaneShell,
  Pill,
  PrimaryBtn,
  SearchInput,
  Sep,
} from "./shared";
import { Markdown } from "../Markdown";

type Tab = "today" | "graph" | "directories" | "skills" | "search";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "today", label: "Today", hint: "review queue" },
  { id: "graph", label: "Graph", hint: "provenance" },
  { id: "directories", label: "Directories", hint: "lenses" },
  { id: "skills", label: "Skills", hint: "procedures" },
  { id: "search", label: "Search", hint: "hybrid" },
];
const KINDS: MemoryItemKind[] = ["episode", "observation", "claim", "skill", "proposal", "artifact_ref", "entity", "directory"];
const STATUSES: MemoryItemStatus[] = ["active", "superseded", "archived"];
const VALIDITY_FILTERS: MemoryValidityFilter[] = ["all", "current", "future", "expired"];

export function MemoryItemsPane() {
  const config = useStore((s) => s.config);
  const [tab, setTab] = useState<Tab>("today");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemoryItemDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const selectItem = useCallback((item: MemoryItemSummary, nextTab?: Tab) => {
    setSelectedId(item.id);
    if (nextTab) setTab(nextTab);
  }, []);

  const clearSelection = useCallback(() => setSelectedId(null), []);

  const reloadDetail = useCallback(() => setRefreshKey((value) => value + 1), []);

  useEffect(() => {
    if (!config || !selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailError(null);
    getMemoryItem(config, selectedId)
      .then((value) => {
        if (!cancelled) setDetail(value);
      })
      .catch((err) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [config, selectedId, refreshKey]);

  if (!config) return <DetailPlaceholder>Memory is unavailable until the app config loads.</DetailPlaceholder>;

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <nav className="flex flex-wrap items-center gap-1 border-b border-line-soft px-3 pb-2" aria-label="Memory sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setTab(entry.id)}
            className={[
              "rounded-lg px-3 py-2 text-left transition-colors",
              tab === entry.id
                ? "bg-surface-soft text-ink shadow-[inset_0_0_0_1px_var(--color-line-soft)]"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            ].join(" ")}
          >
            <div className="text-sm font-semibold tracking-[-0.01em]">{entry.label}</div>
            <div className="text-2xs text-faint">{entry.hint}</div>
          </button>
        ))}
      </nav>

      {tab === "graph" ? (
        <GraphView
          config={config}
          rootId={selectedId}
          onSelect={selectItem}
          clearSelection={clearSelection}
          detail={detail}
          detailError={detailError}
          onSkillChanged={reloadDetail}
        />
      ) : (
        <PaneShell
          list={
            <>
              {tab === "today" && <TodayList config={config} onSelect={selectItem} selectedId={selectedId} refreshKey={refreshKey} onMutate={reloadDetail} />}
              {tab === "directories" && <DirectoriesList config={config} onSelect={selectItem} selectedId={selectedId} refreshKey={refreshKey} />}
              {tab === "skills" && <SkillsList config={config} onSelect={selectItem} selectedId={selectedId} refreshKey={refreshKey} />}
              {tab === "search" && <SearchList config={config} onSelect={selectItem} selectedId={selectedId} refreshKey={refreshKey} />}
            </>
          }
          detail={
            <ItemDetail
              config={config}
              detail={detail}
              error={detailError}
              onOpenGraph={(item) => selectItem(item, "graph")}
              onSkillChanged={reloadDetail}
              onChanged={reloadDetail}
              onDeleted={() => { clearSelection(); reloadDetail(); }}
              onNavigate={(item) => selectItem(item)}
            />
          }
        />
      )}
    </div>
  );
}

function TodayList({
  config,
  onSelect,
  selectedId,
  refreshKey,
  onMutate,
}: {
  config: AppConfig;
  onSelect: (item: MemoryItemSummary, tab?: Tab) => void;
  selectedId: string | null;
  refreshKey: number;
  onMutate: () => void;
}) {
  const [today, setToday] = useState<MemoryToday | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getMemoryToday(config)
      .then((value) => {
        if (!cancelled) setToday(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [config, reload, refreshKey]);

  const act = useCallback(
    async (item: MemoryItemSummary, fn: () => Promise<unknown>) => {
      setBusyId(item.id);
      try {
        await fn();
        setReload((v) => v + 1);
        onMutate();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusyId(null);
      }
    },
    [onMutate],
  );

  const rows = useMemo(() => flattenToday(today), [today]);
  return (
    <ListColumn
      toolbar={<SectionTitle title="Today" subtitle="what changed that you might care about" />}
      items={rows}
      loading={!today && !error}
      error={error ? <ListError title="Could not load Today" message={error} /> : null}
      empty="Nothing to review — memory is quiet."
      totalLabel={today ? `${rows.length} review items` : null}
      renderItem={(row) => (
        <TodayCard
          key={`${row.section}:${row.item.id}`}
          item={row.item}
          section={row.section}
          selected={row.item.id === selectedId}
          busy={busyId === row.item.id}
          onClick={() => onSelect(row.item, row.defaultTab)}
          approveLabel={row.section === "low confidence" ? "Confirm" : "Approve"}
          rejectLabel={row.section === "low confidence" ? "Dismiss" : "Reject"}
          onApprove={
            row.section === "proposal"
              ? () => act(row.item, () => approveMemoryProposal(config, row.item.id))
              : row.section === "low confidence"
                ? () => act(row.item, () => updateMemoryItem(config, row.item.id, { confidence: 0.7 }))
                : undefined
          }
          onReject={
            row.section === "proposal"
              ? () => act(row.item, () => rejectMemoryProposal(config, row.item.id))
              : row.section === "low confidence"
                ? () => act(row.item, () => updateMemoryItem(config, row.item.id, { status: "archived" }))
                : undefined
          }
        />
      )}
    />
  );
}

const SECTION_LABEL: Record<string, { label: string; tone: "accent" | "ok" | "warn" | "neutral" }> = {
  proposal: { label: "proposal", tone: "accent" },
  skill: { label: "new skill", tone: "ok" },
  "low confidence": { label: "needs confirmation", tone: "warn" },
  correction: { label: "correction", tone: "neutral" },
};

function TodayCard({
  item,
  section,
  selected,
  busy,
  onClick,
  onApprove,
  onReject,
  approveLabel = "Approve",
  rejectLabel = "Reject",
}: {
  item: MemoryItemSummary;
  section: string;
  selected: boolean;
  busy: boolean;
  onClick: () => void;
  onApprove?: () => void;
  onReject?: () => void;
  approveLabel?: string;
  rejectLabel?: string;
}) {
  const meta = SECTION_LABEL[section] ?? { label: section, tone: "neutral" as const };
  return (
    <li>
      <div
        className={[
          "rounded-[12px] border px-3 py-2.5 transition-colors",
          selected ? "border-line-strong bg-surface-soft" : "border-line-soft hover:bg-surface-soft",
        ].join(" ")}
      >
        <button type="button" onClick={onClick} className="block w-full text-left">
          <div className="mb-1.5 flex items-center gap-1.5">
            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: KIND_COLOR[item.kind] }} />
            <Pill tone={meta.tone}>{meta.label}</Pill>
            {item.status === "superseded" && <Pill tone="warn">superseded</Pill>}
          </div>
          {item.title && <div className="mb-0.5 line-clamp-1 text-sm font-medium leading-snug text-ink">{item.title}</div>}
          <div className="line-clamp-3 text-sm leading-snug text-ink-soft">{item.content}</div>
        </button>
        {(onApprove || onReject) && (
          <div className="mt-2 flex items-center gap-1.5">
            {onApprove && (
              <PrimaryBtn onClick={onApprove} disabled={busy}>
                {approveLabel}
              </PrimaryBtn>
            )}
            {onReject && (
              <DangerBtn onClick={onReject} disabled={busy}>
                {rejectLabel}
              </DangerBtn>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function GraphView({
  config,
  rootId,
  onSelect,
  clearSelection,
  detail,
  detailError,
  onSkillChanged,
}: {
  config: AppConfig;
  rootId: string | null;
  onSelect: (item: MemoryItemSummary, tab?: Tab) => void;
  clearSelection: () => void;
  detail: MemoryItemDetail | null;
  detailError: string | null;
  onSkillChanged: () => void;
}) {
  const [includeUnlinked, setIncludeUnlinked] = useState(false);
  const [graph, setGraph] = useState<MemoryGlobalGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [centerRequest, setCenterRequest] = useState<CenterRequest | null>(null);
  const [reload, setReload] = useState(0);
  const reloadGraph = useCallback(() => setReload((v) => v + 1), []);
  const nonce = useRef(0);

  const nodeById = useMemo(() => {
    const map = new Map<string, MemoryItemSummary>();
    if (graph) for (const node of graph.nodes) map.set(node.id, node);
    return map;
  }, [graph]);

  const selectedId = detail?.item.id ?? rootId;
  const connections = useMemo<Connection[]>(() => {
    if (!graph || !selectedId) return [];
    const out: Connection[] = [];
    for (const edge of graph.edges) {
      if (edge.child_id === selectedId) {
        const parent = nodeById.get(edge.parent_id);
        if (parent) out.push({ item: parent, role: edge.role, direction: "parent" });
      } else if (edge.parent_id === selectedId) {
        const child = nodeById.get(edge.child_id);
        if (child) out.push({ item: child, role: edge.role, direction: "child" });
      }
    }
    return out;
  }, [graph, selectedId, nodeById]);

  const navigate = useCallback(
    (item: MemoryItemSummary) => {
      onSelect(item);
      nonce.current += 1;
      setCenterRequest({ id: item.id, nonce: nonce.current });
    },
    [onSelect],
  );

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setLoading(true);
    getMemoryGlobalGraph(config, includeUnlinked)
      .then((value) => {
        if (!cancelled) setGraph(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, includeUnlinked, reload]);

  const stat = graph ? `${graph.nodes.length} nodes · ${graph.edges.length} edges` : null;

  return (
    <div className="relative h-full min-h-0">
      {graph && graph.nodes.length > 0 ? (
        <MemoryGraph graph={graph} rootId={selectedId} selectedId={selectedId} onSelect={(item) => onSelect(item)} centerRequest={centerRequest} />
      ) : (
        <div className="grid h-full place-items-center px-6 text-center text-base italic text-faint">
          {loading ? "Loading graph…" : error ? error : "No memory items yet."}
        </div>
      )}

      {/* floating controls */}
      <div className="absolute left-3 top-3 flex items-center gap-2 rounded-lg border border-line-soft bg-surface/80 p-1.5 backdrop-blur-sm">
        <label className="flex items-center gap-1.5 px-1 text-xs text-ink-soft cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeUnlinked}
            onChange={(e) => setIncludeUnlinked(e.target.checked)}
            className="accent-ink"
          />
          unlinked episodes
        </label>
        {stat && <span className="px-1 text-2xs tabular-nums text-faint">{stat}</span>}
      </div>

      {/* drawer inspector — graph is the hub, this is the focused detail */}
      <AnimatePresence>
        {(detail || detailError) && (
          <motion.div
            key="memory-drawer"
            initial={{ x: 28, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 28, opacity: 0 }}
            transition={SPRING_MODAL}
            className="absolute right-3 top-3 bottom-3 w-[360px] overflow-hidden rounded-xl border border-line-soft bg-surface/95 shadow-lg backdrop-blur-sm"
          >
            <button
              type="button"
              onClick={clearSelection}
              aria-label="Close inspector"
              className="absolute right-2 top-2 z-10 grid size-7 place-items-center rounded-md text-faint transition-colors hover:bg-surface-soft hover:text-ink"
            >
              <svg viewBox="0 0 16 16" width={14} height={14} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
            <ItemDetail
              config={config}
              detail={detail}
              error={detailError}
              onOpenGraph={(item) => onSelect(item, "graph")}
              onSkillChanged={onSkillChanged}
              onChanged={() => { onSkillChanged(); reloadGraph(); }}
              onDeleted={() => { clearSelection(); reloadGraph(); }}
              connections={connections}
              onNavigate={navigate}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DirectoriesList({ config, onSelect, selectedId, refreshKey }: { config: AppConfig; onSelect: (item: MemoryItemSummary) => void; selectedId: string | null; refreshKey: number }) {
  const [directories, setDirectories] = useState<MemoryDirectory[]>([]);
  const [proposals, setProposals] = useState<LensProposal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [running, setRunning] = useState(false);
  const [query, setQuery] = useState("");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([listMemoryDirectories(config), listLensProposals(config)])
      .then(([dirs, props]) => {
        if (cancelled) return;
        setDirectories(dirs.directories);
        setProposals(props.proposals);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, refreshKey, reload]);

  const runPass = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      await runLensPass(config);
      setReload((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [config]);

  const generate = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setGenerating(true);
    setError(null);
    try {
      const proposal = await generateLens(config, q);
      setProposals((prev) => [{ ...proposal, created_at: null }, ...prev]);
      setQuery("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  }, [config, query]);

  const approve = useCallback(async (proposalId: string) => {
    setError(null);
    try {
      await approveLensProposal(config, proposalId);
      setProposals((prev) => prev.filter((p) => p.proposal_id !== proposalId));
      setReload((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [config]);

  const reject = useCallback(async (proposalId: string) => {
    setError(null);
    try {
      await rejectLensProposal(config, proposalId);
      setProposals((prev) => prev.filter((p) => p.proposal_id !== proposalId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [config]);

  const saveLens = useCallback(async (slug: string, markdown: string) => {
    setError(null);
    try {
      await updateLens(config, slug, markdown);
      setReload((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  }, [config]);

  const removeLens = useCallback(async (slug: string) => {
    setError(null);
    try {
      await deleteLens(config, slug);
      setReload((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [config]);

  return (
    <>
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
          <SectionTitle title="Directories" subtitle="entity groups shaped by lenses" />
          <GhostBtn onClick={runPass} disabled={running}>{running ? "Running…" : "Run lenses"}</GhostBtn>
        </div>
      </div>
      <div className="flex items-center gap-2 px-3 pb-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") generate(); }}
          placeholder="Describe a group to create… e.g. people I talk to, by company"
          className="h-7 min-w-0 flex-1 rounded-md bg-surface-soft px-2.5 text-sm text-ink placeholder:text-faint focus:outline-none focus:shadow-[inset_0_0_0_1px_var(--color-line)]"
        />
        <PrimaryBtn onClick={generate} disabled={generating || !query.trim()}>{generating ? "Generating…" : "Generate"}</PrimaryBtn>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin scroll-fade-bottom px-2 pb-3">
        {loading ? (
          <div className="px-3 py-3 text-sm text-faint">Loading…</div>
        ) : error ? (
          <div className="px-1 py-3"><ListError title="Directories error" message={error} /></div>
        ) : (
          <>
            {proposals.length > 0 && (
              <ul className="mb-2 space-y-1.5 px-1">
                {proposals.map((p) => (
                  <LensProposalCard key={p.proposal_id} proposal={p} onApprove={approve} onReject={reject} />
                ))}
              </ul>
            )}
            {directories.length === 0 && proposals.length === 0 ? (
              <div className="px-3 py-3 text-sm text-faint">No directories yet. Describe a group above, or add a lens file in ~/.ntrp/memory/lenses/.</div>
            ) : (
              <ul className="flex flex-col gap-px">
                {directories.map((dir) => (
                  <DirectoryGroup key={dir.directory.id} dir={dir} selectedId={selectedId} onSelect={onSelect} onSave={saveLens} onDelete={removeLens} />
                ))}
              </ul>
            )}
          </>
        )}
      </div>
      {!loading && <div className="px-4 py-2 text-xs text-faint tabular-nums">{directories.length} directories · {proposals.length} pending</div>}
    </>
  );
}

function LensProposalCard({ proposal, onApprove, onReject }: { proposal: LensProposal; onApprove: (id: string) => void; onReject: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const wrap = (fn: (id: string) => void) => async () => {
    setBusy(true);
    try {
      await fn(proposal.proposal_id);
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="rounded-[10px] border border-dashed border-line bg-surface-soft/50 px-3 py-2.5">
      <div className="flex items-center gap-1.5">
        <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: KIND_COLOR.directory }} />
        <span className="truncate text-sm font-semibold tracking-[-0.01em] text-ink">{proposal.directory}</span>
        {proposal.entity_type && <Pill>{proposal.entity_type}</Pill>}
        <span className="ml-auto text-2xs uppercase tracking-wide text-faint">proposed</span>
      </div>
      <pre className="mt-1.5 max-h-40 overflow-y-auto scroll-thin whitespace-pre-wrap rounded-md bg-surface px-2 py-1.5 text-2xs leading-[1.5] text-ink-soft">{proposal.markdown}</pre>
      <div className="mt-1.5 flex items-center justify-end gap-1.5">
        <DangerBtn onClick={wrap(onReject)} disabled={busy}>Reject</DangerBtn>
        <PrimaryBtn onClick={wrap(onApprove)} disabled={busy}>Approve &amp; run</PrimaryBtn>
      </div>
    </li>
  );
}

function DirectoryGroup({ dir, selectedId, onSelect, onSave, onDelete }: { dir: MemoryDirectory; selectedId: string | null; onSelect: (item: MemoryItemSummary) => void; onSave: (slug: string, markdown: string) => Promise<void>; onDelete: (slug: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(dir.markdown ?? "");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const editable = dir.slug != null && dir.markdown != null;

  const save = async () => {
    if (dir.slug == null) return;
    setBusy(true);
    try {
      await onSave(dir.slug, draft);
      setEditing(false);
    } catch {
      // error surfaced by parent
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="mb-2">
      <div
        className={[
          "group/dir flex w-full items-center gap-1.5 rounded-[10px] px-3 py-2 transition-colors",
          dir.directory.id === selectedId ? "bg-surface-soft shadow-[inset_0_0_0_1px_var(--color-line-soft)]" : "hover:bg-surface-soft",
        ].join(" ")}
      >
        <button type="button" onClick={() => onSelect(dir.directory)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
          <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: KIND_COLOR.directory }} />
          <span className="truncate text-sm font-semibold tracking-[-0.01em] text-ink">{dir.directory.title ?? dir.directory.content}</span>
          {dir.entity_type && <Pill>{dir.entity_type}</Pill>}
        </button>
        <span className="text-2xs tabular-nums text-faint">{dir.members.length}</span>
        {editable && (
          <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover/dir:opacity-100">
            <button
              type="button"
              title="Edit lens"
              onClick={() => { setDraft(dir.markdown ?? ""); setEditing((v) => !v); setConfirmDelete(false); }}
              className="rounded px-1 py-0.5 text-2xs text-faint hover:bg-surface hover:text-ink"
            >
              Edit
            </button>
            <button
              type="button"
              title="Delete lens"
              onClick={() => (confirmDelete ? onDelete(dir.slug as string) : setConfirmDelete(true))}
              className={["rounded px-1 py-0.5 text-2xs", confirmDelete ? "text-bad hover:bg-bad-soft" : "text-faint hover:bg-surface hover:text-ink"].join(" ")}
            >
              {confirmDelete ? "Confirm?" : "Delete"}
            </button>
          </div>
        )}
      </div>
      {editing && editable && (
        <div className="mt-1 px-1">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            rows={10}
            className="w-full resize-y rounded-md bg-surface px-2 py-1.5 font-mono text-2xs leading-[1.5] text-ink scroll-thin focus:outline-none focus:shadow-[inset_0_0_0_1px_var(--color-line)]"
          />
          <div className="mt-1 flex items-center justify-end gap-1.5">
            <GhostBtn onClick={() => setEditing(false)} disabled={busy}>Cancel</GhostBtn>
            <PrimaryBtn onClick={save} disabled={busy || !draft.trim()}>{busy ? "Saving…" : "Save & run"}</PrimaryBtn>
          </div>
        </div>
      )}
      <ul className="mt-1 space-y-0.5 border-l border-line-soft pl-2">
        {dir.members.length === 0 ? (
          <li className="px-2 py-1 text-xs text-faint">No members yet.</li>
        ) : (
          dir.members.map((member) => (
            <li key={member.id}>
              <button
                type="button"
                onClick={() => onSelect(member)}
                className={[
                  "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors",
                  member.id === selectedId ? "bg-surface-soft shadow-[inset_0_0_0_1px_var(--color-line-soft)]" : "hover:bg-surface-soft",
                ].join(" ")}
              >
                <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: KIND_COLOR.entity }} />
                <span className="truncate text-sm text-ink-soft">{member.title ?? member.content}</span>
              </button>
            </li>
          ))
        )}
      </ul>
    </li>
  );
}

function SkillsList({ config, onSelect, selectedId, refreshKey }: { config: AppConfig; onSelect: (item: MemoryItemSummary) => void; selectedId: string | null; refreshKey: number }) {
  const [skills, setSkills] = useState<MemoryItemSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listMemorySkills(config, true)
      .then((value) => {
        if (!cancelled) setSkills(value.skills);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, refreshKey]);

  return (
    <ListColumn
      toolbar={<SectionTitle title="Skills" subtitle="accepted toolable procedures" />}
      items={skills}
      loading={loading}
      error={error ? <ListError title="Could not load skills" message={error} /> : null}
      empty="No skills yet."
      totalLabel={!loading ? `${skills.length} skills` : null}
      renderItem={(item) => <MemoryRow key={item.id} item={item} selected={item.id === selectedId} onClick={() => onSelect(item)} />}
    />
  );
}

function SearchList({ config, onSelect, selectedId, refreshKey }: { config: AppConfig; onSelect: (item: MemoryItemSummary) => void; selectedId: string | null; refreshKey: number }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<MemoryItemKind | "">("");
  const [status, setStatus] = useState<MemoryItemStatus | "active">("active");
  const [scope, setScope] = useState("");
  const [validity, setValidity] = useState<MemoryValidityFilter>("all");
  const [items, setItems] = useState<MemoryItemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listMemoryItems(config, {
      kinds: kind ? [kind] : undefined,
      statuses: status ? [status] : undefined,
      scope: scope || undefined,
      query: query.trim() || undefined,
      validity,
      limit: 60,
    })
      .then((page) => {
        if (!cancelled) {
          setItems(page.items);
          setTotal(page.total);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, kind, query, refreshKey, scope, status, validity]);

  return (
    <ListColumn
      toolbar={
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <SearchInput value={query} onChange={setQuery} placeholder="Search memory" />
          <div className="grid grid-cols-4 gap-2">
            <FilterSelect value={kind} onChange={(value) => setKind(value as MemoryItemKind | "")} options={["", ...KINDS]} label="kind" emptyLabel="all kinds" />
            <FilterSelect value={status} onChange={(value) => setStatus(value as MemoryItemStatus | "active")} options={STATUSES} label="status" />
            <FilterSelect value={validity} onChange={(value) => setValidity(value as MemoryValidityFilter)} options={VALIDITY_FILTERS} label="validity" />
            <input
              value={scope}
              onChange={(event) => setScope(event.target.value)}
              placeholder="scope"
              className="h-7 min-w-0 rounded-md border border-transparent bg-surface-soft px-2 text-sm text-ink-soft outline-none transition-[background-color,border-color] placeholder:text-faint focus:border-line-soft focus:bg-surface-sunken"
            />
          </div>
        </div>
      }
      items={items}
      loading={loading}
      error={error ? <ListError title="Could not search memory" message={error} /> : null}
      empty="No matching memory items."
      totalLabel={!loading ? `${items.length} of ${total}` : null}
      renderItem={(item) => <MemoryRow key={item.id} item={item} selected={item.id === selectedId} onClick={() => onSelect(item)} />}
    />
  );
}

interface EditDraft {
  content: string;
  title: string;
  confidence: number;
  scope: string;
  status: MemoryItemStatus;
  tags: string;
}

function ItemDetail({
  config,
  detail,
  error,
  onOpenGraph,
  onSkillChanged,
  onChanged,
  onDeleted,
  connections,
  onNavigate,
}: {
  config: AppConfig;
  detail: MemoryItemDetail | null;
  error: string | null;
  onOpenGraph: (item: MemoryItemSummary) => void;
  onSkillChanged: () => void;
  onChanged?: () => void;
  onDeleted?: () => void;
  connections?: Connection[];
  onNavigate?: (item: MemoryItemSummary) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);

  const itemId = detail?.item.id;
  useEffect(() => {
    setEditing(false);
    setConfirmDelete(false);
    setEditError(null);
  }, [itemId]);

  if (error) {
    return <DetailPlaceholder><ErrorPill message={error} /></DetailPlaceholder>;
  }
  if (!detail) {
    return <DetailPlaceholder>Select a memory item to inspect source refs and provenance.</DetailPlaceholder>;
  }

  const item = detail.item;
  const enabled = !item.tags.includes("disabled:true");
  const toggleSkill = async () => {
    if (item.kind !== "skill") return;
    setSaving(true);
    try {
      await setMemorySkillEnabled(config, item.id, !enabled);
      onSkillChanged();
    } finally {
      setSaving(false);
    }
  };

  const startEdit = () => {
    setDraft({
      content: item.content,
      title: item.title ?? "",
      confidence: item.confidence,
      scope: item.scope,
      status: item.status,
      tags: item.tags.join(", "),
    });
    setEditError(null);
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!draft) return;
    setSaving(true);
    setEditError(null);
    try {
      await updateMemoryItem(config, item.id, {
        content: draft.content,
        title: draft.title.trim() === "" ? null : draft.title.trim(),
        confidence: draft.confidence,
        scope: draft.scope.trim(),
        status: draft.status,
        tags: draft.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setEditing(false);
      onChanged?.();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setSaving(true);
    setEditError(null);
    try {
      await deleteMemoryItem(config, item.id);
      onDeleted?.();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  };

  return (
    <DetailShell
      header={
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="accent">{item.kind}</Pill>
            <Pill tone={statusTone(item.status)}>{item.status}</Pill>
            <Pill>{item.scope}</Pill>
            {item.confidence < 0.5 && <Pill tone="warn">low confidence</Pill>}
          </div>
          <h2 className="text-lg font-semibold leading-snug tracking-[-0.012em] text-ink">{item.title ?? shortTitle(item.content)}</h2>
          <DetailMeta>
            <span className="font-mono">{item.id}</span>
            <Sep />
            <span>{formatDate(item.created_at)}</span>
          </DetailMeta>
        </div>
      }
      body={
        editing && draft ? (
          <ItemEditForm draft={draft} setDraft={setDraft} error={editError} />
        ) : (
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Content</h3>
              <div className="rounded-[10px] border border-line-soft bg-surface-soft px-3 py-2">
                <Markdown content={item.content} className="text-sm leading-relaxed text-ink-soft" />
              </div>
            </section>
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Provenance</h3>
              <MetaGrid
                rows={[
                  { label: "provenance", value: item.provenance },
                  { label: "confidence", value: item.confidence.toFixed(2) },
                  { label: "valid from", value: formatDate(item.valid_from) },
                  item.invalid_at ? { label: "invalid at", value: formatDate(item.invalid_at) } : null,
                  { label: "embedding", value: item.has_embedding ? "yes" : "no" },
                ]}
              />
            </section>
            <ConnectionsSection detail={detail} connections={connections} onNavigate={onNavigate} />
          </div>
        )
      }
      meta={
        <div className="space-y-4">
          {item.tags.length > 0 && (
            <MetaSection title="Tags">
              <div className="flex flex-wrap gap-1.5">
                {item.tags.map((tag) => (
                  <Pill key={tag}>{tag}</Pill>
                ))}
              </div>
            </MetaSection>
          )}
          {item.source_refs.length > 0 && (
            <MetaSection title="Source refs">
              <ul className="space-y-1.5">
                {item.source_refs.map((ref, index) => (
                  <SourceRefRow key={index} value={ref} />
                ))}
              </ul>
            </MetaSection>
          )}
          {item.artifact_ref ? (
            <MetaSection title="Artifact ref">
              <ArtifactRef value={item.artifact_ref} />
            </MetaSection>
          ) : null}
        </div>
      }
      actions={
        editing ? (
          <>
            <GhostBtn onClick={() => setEditing(false)} disabled={saving}>Cancel</GhostBtn>
            <PrimaryBtn onClick={saveEdit} disabled={saving || !draft?.content.trim()}>{saving ? "Saving…" : "Save"}</PrimaryBtn>
          </>
        ) : (
          <>
            {onDeleted && (
              <DangerBtn onClick={remove} disabled={saving}>{confirmDelete ? "Confirm delete" : "Delete"}</DangerBtn>
            )}
            {item.kind === "skill" && <GhostBtn onClick={toggleSkill} disabled={saving}>{enabled ? "Disable" : "Enable"}</GhostBtn>}
            {onChanged && <GhostBtn onClick={startEdit} disabled={saving}>Edit</GhostBtn>}
            <GhostBtn onClick={() => onOpenGraph(item)}>Open graph</GhostBtn>
          </>
        )
      }
    />
  );
}

function ItemEditForm({
  draft,
  setDraft,
  error,
}: {
  draft: EditDraft;
  setDraft: (d: EditDraft) => void;
  error: string | null;
}) {
  const field = "h-7 w-full rounded-md bg-surface-soft px-2.5 text-sm text-ink focus:outline-none focus:shadow-[inset_0_0_0_1px_var(--color-line)]";
  const label = "mb-1 block text-2xs font-semibold uppercase tracking-wide text-faint";
  return (
    <div className="space-y-3.5">
      {error && <ErrorPill message={error} />}
      <div>
        <span className={label}>Content</span>
        <textarea
          value={draft.content}
          onChange={(e) => setDraft({ ...draft, content: e.target.value })}
          rows={8}
          className="w-full resize-y rounded-md bg-surface-soft px-2.5 py-1.5 text-sm leading-relaxed text-ink scroll-thin focus:outline-none focus:shadow-[inset_0_0_0_1px_var(--color-line)]"
        />
      </div>
      <div>
        <span className={label}>Title</span>
        <input type="text" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className={field} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <span className={label}>Confidence</span>
          <input
            type="number" min={0} max={1} step={0.05} value={draft.confidence}
            onChange={(e) => setDraft({ ...draft, confidence: Math.min(1, Math.max(0, Number(e.target.value))) })}
            className={`${field} tabular-nums`}
          />
        </div>
        <div>
          <span className={label}>Status</span>
          <select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as MemoryItemStatus })} className={field}>
            <option value="active">active</option>
            <option value="superseded">superseded</option>
            <option value="archived">archived</option>
          </select>
        </div>
      </div>
      <div>
        <span className={label}>Scope</span>
        <input type="text" value={draft.scope} onChange={(e) => setDraft({ ...draft, scope: e.target.value })} className={field} />
      </div>
      <div>
        <span className={label}>Tags (comma-separated)</span>
        <input type="text" value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} className={field} placeholder="tag-a, tag-b" />
      </div>
    </div>
  );
}

function ConnectionsSection({
  detail,
  connections,
  onNavigate,
}: {
  detail: MemoryItemDetail;
  connections?: Connection[];
  onNavigate?: (item: MemoryItemSummary) => void;
}) {
  if (connections) {
    const parents = connections.filter((c) => c.direction === "parent");
    const children = connections.filter((c) => c.direction === "child");
    if (parents.length === 0 && children.length === 0) return null;
    return (
      <>
        {parents.length > 0 && <ConnectionGroup title="Parents" items={parents} onNavigate={onNavigate} />}
        {children.length > 0 && <ConnectionGroup title="Children" items={children} onNavigate={onNavigate} />}
      </>
    );
  }
  if (detail.parents.length === 0) return null;
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Parents</h3>
      <div className="space-y-2">
        {detail.parents.map((parent) => (
          <ConnectionRow
            key={`${parent.role}:${parent.parent_id}`}
            role={parent.role}
            item={parent.parent}
            fallbackId={parent.parent_id}
            onNavigate={onNavigate}
          />
        ))}
      </div>
    </section>
  );
}

function ConnectionGroup({ title, items, onNavigate }: { title: string; items: Connection[]; onNavigate?: (item: MemoryItemSummary) => void }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">{title}</h3>
      <div className="space-y-2">
        {items.map((c) => (
          <ConnectionRow key={`${c.direction}:${c.role}:${c.item.id}`} role={c.role} item={c.item} fallbackId={c.item.id} onNavigate={onNavigate} />
        ))}
      </div>
    </section>
  );
}

function ConnectionRow({
  role,
  item,
  fallbackId,
  onNavigate,
}: {
  role: MemoryParentRole;
  item: MemoryItemSummary | null;
  fallbackId: string;
  onNavigate?: (item: MemoryItemSummary) => void;
}) {
  const inner = (
    <>
      <div className="mb-1 flex items-center gap-2">
        {item && <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: KIND_COLOR[item.kind] }} />}
        <Pill>{role}</Pill>
        <span className="truncate font-mono text-2xs text-faint">{item?.id ?? fallbackId}</span>
      </div>
      {item && <p className="line-clamp-2 text-sm text-ink-soft">{item.title ?? item.content}</p>}
    </>
  );
  if (!item || !onNavigate) {
    return <div className="rounded-[10px] border border-line-soft bg-surface-soft px-3 py-2">{inner}</div>;
  }
  return (
    <button
      type="button"
      onClick={() => onNavigate(item)}
      className="block w-full rounded-[10px] border border-line-soft bg-surface-soft px-3 py-2 text-left transition-colors hover:border-line-strong hover:bg-surface"
    >
      {inner}
    </button>
  );
}

function MemoryRow({ item, selected, onClick }: { item: MemoryItemSummary; selected: boolean; onClick: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={[
          "w-full rounded-[10px] px-3 py-2.5 text-left transition-colors",
          selected ? "bg-surface-soft shadow-[inset_0_0_0_1px_var(--color-line-soft)]" : "hover:bg-surface-soft",
        ].join(" ")}
      >
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: KIND_COLOR[item.kind] }} />
          <Pill tone="accent">{item.kind}</Pill>
          <Pill tone={statusTone(item.status)}>{item.status}</Pill>
          <Pill>{item.scope}</Pill>
        </div>
        <div className="line-clamp-3 text-sm leading-snug text-ink-soft">{item.content}</div>
        <div className="mt-1 truncate font-mono text-2xs text-faint">{item.id}</div>
      </button>
    </li>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="min-w-0">
      <div className="text-sm font-semibold tracking-[-0.01em] text-ink">{title}</div>
      <div className="truncate text-xs text-faint">{subtitle}</div>
    </div>
  );
}

function FilterSelect({ value, onChange, options, label, emptyLabel }: { value: string; onChange: (value: string) => void; options: string[]; label: string; emptyLabel?: string }) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-7 min-w-0 rounded-md border border-transparent bg-surface-soft px-2 text-sm text-ink-soft outline-none transition-[background-color,border-color] focus:border-line-soft focus:bg-surface-sunken"
    >
      {options.map((option) => (
        <option key={option || "__empty"} value={option}>
          {option || emptyLabel || "all"}
        </option>
      ))}
    </select>
  );
}

function flattenToday(today: MemoryToday | null): { section: string; item: MemoryItemSummary; defaultTab?: Tab }[] {
  if (!today) return [];
  return [
    ...today.pending_proposals.map((item) => ({ section: "proposal", item })),
    ...today.new_skills.map((item) => ({ section: "skill", item, defaultTab: "skills" as Tab })),
    ...today.low_confidence_claims.map((item) => ({ section: "low confidence", item })),
    ...today.recent_corrections.map((item) => ({ section: "correction", item })),
  ];
}

function statusTone(status: MemoryItemStatus): "neutral" | "ok" | "warn" | "bad" {
  if (status === "active") return "ok";
  if (status === "superseded") return "warn";
  return "neutral";
}

function MetaSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">{title}</h3>
      {children}
    </section>
  );
}

type SourceRef = { kind?: string; ref?: string; captured_at?: string };

function SourceRefRow({ value }: { value: unknown }) {
  const ref = (value ?? {}) as SourceRef;
  const hasFields = ref.kind || ref.ref || ref.captured_at;
  if (!hasFields) {
    return (
      <li className="rounded-[8px] border border-line-soft bg-surface-soft px-2.5 py-1.5 font-mono text-2xs text-ink-soft break-all">
        {JSON.stringify(value)}
      </li>
    );
  }
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-[8px] border border-line-soft bg-surface-soft px-2.5 py-1.5">
      {ref.kind && <Pill>{ref.kind}</Pill>}
      {ref.ref && <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink-soft">{ref.ref}</span>}
      {ref.captured_at && <span className="shrink-0 text-2xs text-faint">{formatRelative(ref.captured_at)}</span>}
    </li>
  );
}

function ArtifactRef({ value }: { value: unknown }) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-y-1.5 text-sm">
        {entries.map(([key, val]) => (
          <div key={key} className="contents">
            <dt className="text-faint">{key}</dt>
            <dd className="min-w-0 break-all font-mono text-xs text-ink-soft">
              {typeof val === "string" ? val : JSON.stringify(val)}
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <div className="break-all font-mono text-xs text-ink-soft">{String(value)}</div>;
}

function shortTitle(content: string): string {
  const lines = content.split("\n").map((line) => line.trim());
  const heading = lines.find((line) => /^#{1,6}\s+/.test(line));
  const firstNonEmpty = lines.find((line) => line.length > 0) ?? "";
  const source = heading ?? firstNonEmpty;
  const cleaned = stripMarkdown(source);
  const title = cleaned.split(/(?<=[.!?])\s/)[0]?.trim() || cleaned;
  if (!title) return "Untitled memory item";
  return title.length > 140 ? `${title.slice(0, 140)}…` : title;
}

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/, "")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatRelative(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (abs < hour) return rtf.format(Math.round(diffMs / minute), "minute");
  if (abs < day) return rtf.format(Math.round(diffMs / hour), "hour");
  if (abs < 30 * day) return rtf.format(Math.round(diffMs / day), "day");
  return date.toLocaleDateString();
}
