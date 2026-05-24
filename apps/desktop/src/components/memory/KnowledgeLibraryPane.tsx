import { useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";
import clsx from "clsx";
import type {
  ActivationBundle,
  ActivationCandidate,
  KnowledgeObject,
  KnowledgeObjectStatus,
  KnowledgeObjectType,
  KnowledgeSourceTraceResult,
  KnowledgeSummary,
} from "../../api";
import {
  getKnowledgeObjectSourcesApi,
  getKnowledgeSummaryApi,
  inspectKnowledgeActivationApi,
  listKnowledgeObjectsApi,
  updateKnowledgeObjectApi,
} from "../../api";
import { useStore } from "../../store";
import { formatRelativePast } from "../../lib/format";
import { KNOWLEDGE_LIBRARY_TYPES, knowledgeSurfaceAllStatusCount, knowledgeSurfaceStatusCount } from "../../lib/knowledgeViews";
import { ICON } from "../../lib/icons";
import { DangerBtn, DetailPlaceholder, ErrorPill, GhostBtn, Pill, SearchInput } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";

const LIBRARY_PAGE_SIZE = 250;
const LIBRARY_LIST_LIMIT = LIBRARY_PAGE_SIZE + 1;
export type LibraryTypeFilter = KnowledgeObjectType | "all";
type LibraryStatusFilter = Extract<KnowledgeObjectStatus, "active" | "archived"> | "all";

const ALL_LIBRARY_VIEW = {
  type: "all" as const,
  label: "All",
  description: "search across facts, lessons, artifacts, and episodes",
};

export function KnowledgeLibraryPane({
  initialType = "fact",
  focusVersion = 0,
}: {
  initialType?: LibraryTypeFilter;
  focusVersion?: number;
}) {
  const config = useStore((s) => s.config);
  const [selectedType, setSelectedType] = useState<LibraryTypeFilter>(initialType);
  const [statusFilter, setStatusFilter] = useState<LibraryStatusFilter>("active");
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [items, setItems] = useState<KnowledgeObject[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [sources, setSources] = useState<KnowledgeSourceTraceResult | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [previewQuery, setPreviewQuery] = useState("");
  const [activationPreview, setActivationPreview] = useState<ActivationBundle | null>(null);
  const [activationPreviewLoading, setActivationPreviewLoading] = useState(false);
  const [activationPreviewError, setActivationPreviewError] = useState<string | null>(null);
  const listGenerationRef = useRef(0);
  const activationPreviewGenerationRef = useRef(0);

  const selected = useMemo(
    () => items?.find((item) => item.id === selectedId) ?? items?.[0] ?? null,
    [items, selectedId],
  );

  async function copyText(key: string, value: string) {
    if (!value.trim()) return;
    try {
      await window.ntrpDesktop?.clipboard?.writeText(value);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey((current) => (current === key ? null : current)), 1200);
    } catch {
      // Copy is best-effort; keep the memory inspector usable if clipboard access is unavailable.
    }
  }

  function updatePreviewQuery(value: string) {
    setPreviewQuery(value);
    if (!value.trim()) {
      activationPreviewGenerationRef.current += 1;
      setActivationPreview(null);
      setActivationPreviewError(null);
      setActivationPreviewLoading(false);
    }
  }

  async function runActivationPreview() {
    const trimmed = previewQuery.trim();
    if (!trimmed) return;
    const generation = ++activationPreviewGenerationRef.current;
    setActivationPreviewLoading(true);
    setActivationPreviewError(null);
    try {
      const result = await inspectKnowledgeActivationApi(config, trimmed);
      if (generation === activationPreviewGenerationRef.current) setActivationPreview(result);
    } catch (e) {
      if (generation === activationPreviewGenerationRef.current) setActivationPreviewError(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === activationPreviewGenerationRef.current) setActivationPreviewLoading(false);
    }
  }

  function invalidateListRequests() {
    listGenerationRef.current += 1;
    setLoadingMore(false);
  }

  async function load(type: LibraryTypeFilter = selectedType, status = statusFilter, searchQuery = query) {
    const generation = ++listGenerationRef.current;
    setError(null);
    setSources(null);
    setSourcesError(null);
    try {
      const [nextSummary, nextItems] = await Promise.all([
        getKnowledgeSummaryApi(config),
        listKnowledgeObjectsApi(config, {
          object_type: type === "all" ? undefined : type,
          status: status === "all" ? undefined : status,
          query: searchQuery,
          limit: LIBRARY_LIST_LIMIT,
        }),
      ]);
      if (generation !== listGenerationRef.current) return;
      const visibleObjects = nextItems.objects.slice(0, LIBRARY_PAGE_SIZE);
      setSummary(nextSummary);
      setItems(visibleObjects);
      setHasMore(nextItems.objects.length > LIBRARY_PAGE_SIZE);
      setSelectedId(visibleObjects[0]?.id ?? null);
    } catch (e) {
      if (generation === listGenerationRef.current) {
        setError(e instanceof Error ? e.message : String(e));
        setItems([]);
        setHasMore(false);
        setSelectedId(null);
        setSourcesLoading(false);
      }
    }
  }

  async function loadMore() {
    if (!items || loadingMore || !hasMore) return;
    const generation = listGenerationRef.current;
    const offset = items.length;
    setLoadingMore(true);
    setError(null);
    try {
      const nextItems = await listKnowledgeObjectsApi(config, {
        object_type: selectedType === "all" ? undefined : selectedType,
        status: statusFilter === "all" ? undefined : statusFilter,
        query,
        limit: LIBRARY_LIST_LIMIT,
        offset,
      });
      if (generation !== listGenerationRef.current) return;
      const visibleObjects = nextItems.objects.slice(0, LIBRARY_PAGE_SIZE);
      setItems((current) => (current ? [...current, ...visibleObjects] : visibleObjects));
      setHasMore(nextItems.objects.length > LIBRARY_PAGE_SIZE);
    } catch (e) {
      if (generation === listGenerationRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === listGenerationRef.current) setLoadingMore(false);
    }
  }

  function resetListForFilterChange() {
    invalidateListRequests();
    setItems(null);
    setSelectedId(null);
    setSources(null);
    setSourcesError(null);
    setSourcesLoading(false);
    setHasMore(false);
  }

  function handleQueryChange(nextQuery: string) {
    setQuery(nextQuery);
    resetListForFilterChange();
  }

  function selectType(type: LibraryTypeFilter) {
    setSelectedType(type);
    resetListForFilterChange();
  }

  function selectStatus(status: LibraryStatusFilter) {
    setStatusFilter(status);
    resetListForFilterChange();
  }

  async function moveSelected(nextStatus: Extract<KnowledgeObjectStatus, "active" | "archived">) {
    if (!selected) return;
    const verb = nextStatus === "archived" ? "Archive" : "Restore";
    const detail = nextStatus === "archived" ? "leave the active memory set" : "return to the active memory set";
    const ok = window.confirm(`${verb} memory object “${selected.title}”? It will ${detail}.`);
    if (!ok) return;
    setStatusUpdating(true);
    setError(null);
    try {
      const updated = await updateKnowledgeObjectApi(config, selected.id, { status: nextStatus });
      if (statusFilter === "all") {
        setItems((current) => current?.map((item) => (item.id === selected.id ? updated.object : item)) ?? []);
        setSelectedId(updated.object.id);
      } else {
        const remaining = items?.filter((item) => item.id !== selected.id) ?? [];
        setItems(remaining);
        setSelectedId(remaining[0]?.id ?? null);
        setSources(null);
        setSourcesError(null);
        setSourcesLoading(false);
      }
      setSummary(await getKnowledgeSummaryApi(config));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStatusUpdating(false);
    }
  }

  useEffect(() => {
    invalidateListRequests();
    setSelectedType(initialType);
    setStatusFilter("active");
    setSelectedId(null);
    setQuery("");
    setSources(null);
    setSourcesError(null);
    activationPreviewGenerationRef.current += 1;
    setActivationPreview(null);
    setActivationPreviewError(null);
    setActivationPreviewLoading(false);
  }, [focusVersion, initialType]);

  useEffect(() => {
    const delay = query.trim() ? 250 : 0;
    const handle = window.setTimeout(() => {
      void load(selectedType, statusFilter, query);
    }, delay);
    return () => window.clearTimeout(handle);
  }, [selectedType, statusFilter, query, focusVersion]);

  useEffect(() => {
    activationPreviewGenerationRef.current += 1;
    setPreviewQuery(selected ? selected.title : "");
    setActivationPreview(null);
    setActivationPreviewError(null);
    setActivationPreviewLoading(false);
  }, [selected?.id]);

  useEffect(() => {
    let cancelled = false;
    setSources(null);
    setSourcesError(null);
    setSourcesLoading(Boolean(selected));
    if (!selected) return;
    void getKnowledgeObjectSourcesApi(config, selected.id)
      .then((result) => {
        if (!cancelled) setSources(result);
      })
      .catch((e) => {
        if (!cancelled) setSourcesError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setSourcesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, selected?.id]);

  return (
    <div className="grid h-full grid-cols-[250px_minmax(280px,360px)_minmax(0,1fr)]">
      <aside className="min-h-0 overflow-y-auto border-r border-line-soft px-3 py-3 scroll-thin">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="m-0 text-sm font-semibold text-ink">Library</h3>
          <GhostBtn onClick={() => void load(selectedType, statusFilter, query)}>Refresh</GhostBtn>
        </div>
        <p className="m-0 mb-3 text-xs leading-snug text-faint">
          Browse the simplified memory set: facts, lessons, artifacts, and rolling episodes.
        </p>
        <div className="mb-3 grid grid-cols-3 gap-1 rounded-[9px] border border-line-soft bg-bg-main/50 p-1">
          {(["active", "archived", "all"] as const).map((status) => (
            <button
              key={status}
              type="button"
              aria-pressed={statusFilter === status}
              onClick={() => selectStatus(status)}
              className={clsx(
                "rounded-[7px] px-2 py-1.5 text-xs font-medium capitalize transition-colors",
                statusFilter === status ? "bg-surface-soft text-ink" : "text-faint hover:bg-surface-soft hover:text-ink",
              )}
            >
              {status}
            </button>
          ))}
        </div>
        <ul className="m-0 grid list-none gap-1 p-0">
          {[ALL_LIBRARY_VIEW, ...KNOWLEDGE_LIBRARY_TYPES].map((view) => {
            const active = selectedType === view.type;
            const count = summary ? libraryViewCount(summary, view.type, statusFilter) : null;
            return (
              <li key={view.type}>
                <button
                  type="button"
                  aria-current={active ? "page" : undefined}
                  onClick={() => selectType(view.type)}
                  className={clsx(
                    "w-full rounded-[8px] px-3 py-2 text-left transition-colors",
                    active ? "bg-surface-soft text-ink" : "text-muted hover:bg-surface-soft hover:text-ink",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{view.label}</span>
                    {count !== null && <span className="font-mono text-xs">{count}</span>}
                  </div>
                  <div className="mt-1 text-xs text-faint">{view.description}</div>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <section className="min-h-0 overflow-y-auto border-r border-line-soft px-3 py-3 scroll-thin">
        {error && <div className="mb-2"><ErrorPill message={error} /></div>}
        <div className="mb-3 flex items-center gap-2">
          <SearchInput value={query} onChange={handleQueryChange} placeholder={`Search ${selectedTypeLabel(selectedType)}`} ariaLabel="Search memory library" />
          {items && (
            <span className="shrink-0 font-mono text-2xs text-faint">
              {items.length}{hasMore ? "+" : ""}
            </span>
          )}
        </div>
        {items === null ? (
          <DetailPlaceholder>Loading</DetailPlaceholder>
        ) : items.length === 0 ? (
          <DetailPlaceholder>{error ? "Could not load memories" : query.trim() ? "No search matches" : noObjectsLabel(statusFilter)}</DetailPlaceholder>
        ) : (
          <div className="grid gap-3">
            <ul className="m-0 grid list-none gap-1 p-0">
              {items.map((item) => {
                const active = selected?.id === item.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      aria-current={active ? "true" : undefined}
                      onClick={() => setSelectedId(item.id)}
                      className={clsx(
                        "w-full rounded-[8px] px-3 py-2 text-left transition-colors",
                        active ? "bg-surface-soft" : "hover:bg-surface-soft",
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        {selectedType === "all" && <Pill>{item.object_type}</Pill>}
                        <Pill>{item.status}</Pill>
                        {item.scope && <Pill>{item.scope}</Pill>}
                      </div>
                      <h4 className="m-0 mt-1 line-clamp-2 text-sm font-semibold text-ink-soft">{item.title}</h4>
                      <p className="m-0 mt-1 line-clamp-2 text-xs leading-snug text-faint">{item.text}</p>
                    </button>
                  </li>
                );
              })}
            </ul>
            {hasMore && (
              <GhostBtn onClick={() => void loadMore()} disabled={loadingMore}>
                {loadingMore ? "Loading" : "Load more"}
              </GhostBtn>
            )}
          </div>
        )}
      </section>

      <section className="min-h-0 overflow-y-auto px-7 py-5 scroll-thin">
        <ScrollBlurTop />
        {!selected ? (
          <DetailPlaceholder>Select an object</DetailPlaceholder>
        ) : (
          <div className="grid gap-5">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <Pill>{selected.object_type}</Pill>
                <Pill>{selected.status}</Pill>
                <Pill>{selected.activation}</Pill>
                <Pill>{selected.proactiveness_level}</Pill>
                <span className="text-xs text-faint">updated {formatRelativePast(selected.updated_at)}</span>
              </div>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h3 className="m-0 text-xl font-semibold text-ink">{selected.title}</h3>
                {selected.status === "archived" ? (
                  <GhostBtn onClick={() => void moveSelected("active")} disabled={statusUpdating}>
                    {statusUpdating ? "Restoring" : "Restore active"}
                  </GhostBtn>
                ) : (
                  <DangerBtn onClick={() => void moveSelected("archived")} disabled={statusUpdating}>
                    {statusUpdating ? "Archiving" : "Archive"}
                  </DangerBtn>
                )}
              </div>
              <CopyableBlock
                label="Content"
                value={selected.text}
                copied={copiedKey === "content"}
                onCopy={() => void copyText("content", selected.text)}
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <Pill>score {selected.score.toFixed(2)}</Pill>
              <Pill>sources {selected.source_ids.length}</Pill>
              {selected.scope && <Pill>scope {selected.scope}</Pill>}
              {selected.reviewed_at && <Pill>reviewed {formatRelativePast(selected.reviewed_at)}</Pill>}
            </div>

            <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
              <h4 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Object details</h4>
              <MetadataRows
                metadata={{
                  id: selected.id,
                  type: selected.object_type,
                  status: selected.status,
                  scope: selected.scope,
                  activation: selected.activation,
                  proactiveness_level: selected.proactiveness_level,
                  score: selected.score,
                  created_at: selected.created_at,
                  updated_at: selected.updated_at,
                  reviewed_at: selected.reviewed_at,
                }}
              />
            </section>

            <ActivationPreviewSection
              selected={selected}
              query={previewQuery}
              onQueryChange={updatePreviewQuery}
              preview={activationPreview}
              loading={activationPreviewLoading}
              error={activationPreviewError}
              onRun={() => void runActivationPreview()}
            />

            <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h4 className="m-0 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Source IDs</h4>
                {selected.source_ids.length > 0 && (
                  <TinyCopyButton copied={copiedKey === "source-ids"} onClick={() => void copyText("source-ids", selected.source_ids.join("\n"))} />
                )}
              </div>
              {selected.source_ids.length === 0 ? (
                <p className="m-0 text-sm italic text-faint">No source IDs</p>
              ) : (
                <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-[7px] border border-line-soft bg-surface-soft/50 p-3 font-mono text-2xs leading-relaxed text-ink-soft scroll-thin">
                  {selected.source_ids.join("\n")}
                </pre>
              )}
            </section>

            <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
              <h4 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Source trace</h4>
              {sourcesLoading ? (
                <p className="m-0 text-sm italic text-faint">Loading sources</p>
              ) : sourcesError ? (
                <ErrorPill message={sourcesError} />
              ) : !sources || sources.sources.length === 0 ? (
                <p className="m-0 text-sm italic text-faint">No source trace</p>
              ) : (
                <ul className="m-0 grid list-none gap-2 p-0">
                  {sources.sources.map((source) => (
                    <li key={source.source_id} className="rounded-[7px] border border-line-soft bg-surface-soft/50 px-3 py-2">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5">
                        <Pill>{sourceKind(source.source_id)}</Pill>
                        <span className="break-all font-mono text-2xs text-faint">{source.source_id}</span>
                      </div>
                      {source.object ? (
                        <div>
                          <div className="text-sm font-semibold text-ink-soft">{source.object.title}</div>
                          <div className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-snug text-faint scroll-thin">{source.object.text}</div>
                        </div>
                      ) : (
                        <div className="text-xs text-faint">External/source-native reference; no local object yet.</div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
              <h4 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Metadata</h4>
              <MetadataRows metadata={selected.metadata} />
              <CopyableBlock
                label="Raw metadata"
                value={formatMetadataJson(selected.metadata)}
                copied={copiedKey === "metadata"}
                onCopy={() => void copyText("metadata", formatMetadataJson(selected.metadata))}
                collapsed
              />
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

function ActivationPreviewSection({
  selected,
  query,
  onQueryChange,
  preview,
  loading,
  error,
  onRun,
}: {
  selected: KnowledgeObject;
  query: string;
  onQueryChange: (query: string) => void;
  preview: ActivationBundle | null;
  loading: boolean;
  error: string | null;
  onRun: () => void;
}) {
  const allCandidates = preview ? [...preview.candidates, ...preview.omitted] : [];
  const selectedCandidate = allCandidates.find((candidate) => candidate.object_id === String(selected.id)) ?? null;
  const selectedRank = preview?.candidates.findIndex((candidate) => candidate.object_id === String(selected.id)) ?? -1;
  const otherCandidates = preview?.candidates.filter((candidate) => candidate.object_id !== String(selected.id)).slice(0, 4) ?? [];
  const helpId = `activation-preview-help-${selected.id}`;

  return (
    <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="m-0 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Activation preview</h4>
          <p id={helpId} className="m-0 mt-1 text-xs text-faint">Run a query and see whether this object would be recalled, with reasons/signals. Press Ctrl/⌘+Enter to preview.</p>
        </div>
        <GhostBtn onClick={onRun} disabled={loading || !query.trim()}>{loading ? "Checking..." : "Preview recall"}</GhostBtn>
      </div>
      <div className="relative">
        <textarea
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && query.trim() && !loading) {
              event.preventDefault();
              onRun();
            }
          }}
          rows={2}
          aria-label="Activation preview query"
          aria-describedby={helpId}
          className="min-h-[64px] w-full resize-y rounded-[8px] border border-line-soft bg-surface-soft/70 px-3 py-2 pr-9 text-sm leading-snug text-ink outline-none transition focus:border-accent/50"
          placeholder="Query to test activation…"
        />
        {query && (
          <button
            type="button"
            onClick={() => onQueryChange("")}
            aria-label="Clear activation preview query"
            className="absolute right-2.5 top-2.5 grid size-5 place-items-center rounded text-faint hover:bg-surface-soft hover:text-ink"
          >
            <X size={ICON.XS} strokeWidth={2} />
          </button>
        )}
      </div>
      {error && <div className="mt-2"><ErrorPill message={error} /></div>}
      {preview && !error && (
        <div className="mt-3 grid gap-3">
          <div className="flex flex-wrap gap-2">
            <Pill>returned {preview.candidates.length}</Pill>
            <Pill>omitted {preview.omitted.length}</Pill>
            <Pill>used {preview.used_chars}/{preview.budget_chars} chars</Pill>
            <Pill>{selectedCandidate ? (selectedRank >= 0 ? `selected rank ${selectedRank + 1}` : "selected omitted") : "selected not matched"}</Pill>
          </div>
          {selectedCandidate ? (
            <ActivationCandidateCard candidate={selectedCandidate} label="This object" />
          ) : (
            <p className="m-0 rounded-[7px] border border-line-soft bg-surface-soft/50 px-3 py-2 text-sm italic text-faint">
              This object was not returned for that query. Try a more direct phrase from the memory content.
            </p>
          )}
          {otherCandidates.length > 0 && (
            <div>
              <h5 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Top other matches</h5>
              <ul className="m-0 grid list-none gap-2 p-0">
                {otherCandidates.map((candidate) => (
                  <li key={candidate.object_id}>
                    <ActivationCandidateCard candidate={candidate} muted />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ActivationCandidateCard({ candidate, label, muted = false }: { candidate: ActivationCandidate; label?: string; muted?: boolean }) {
  return (
    <div className="rounded-[7px] border border-line-soft bg-surface-soft/50 px-3 py-2">
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        {label && <Pill>{label}</Pill>}
        <Pill>{candidate.object_type}</Pill>
        <Pill>{candidate.activation}</Pill>
        <Pill>{candidate.proactiveness_level}</Pill>
        <span className="text-xs text-faint">score {candidate.score.toFixed(2)}</span>
      </div>
      <div className="text-sm font-semibold text-ink-soft">{candidate.title}</div>
      {candidate.reasons.length > 0 && <div className="mt-1 text-xs leading-snug text-faint">Why: {candidate.reasons.join(", ")}</div>}
      <div className={clsx("mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-xs leading-snug scroll-thin", muted ? "text-faint" : "text-ink-soft")}>
        {candidate.text}
      </div>
      {candidate.signals.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {candidate.signals.slice(0, 8).map((signal) => (
            <Pill key={`${signal.name}:${signal.reason}`}>{signal.name}: {String(signal.value)}</Pill>
          ))}
        </div>
      )}
    </div>
  );
}


function libraryViewCount(summary: KnowledgeSummary, type: LibraryTypeFilter, status: LibraryStatusFilter): number {
  if (status === "all") {
    if (type === "all") {
      return KNOWLEDGE_LIBRARY_TYPES.reduce(
        (total, view) => total + knowledgeSurfaceAllStatusCount(summary.surfaces, view.type),
        0,
      );
    }
    return knowledgeSurfaceAllStatusCount(summary.surfaces, type);
  }

  if (type === "all") {
    return KNOWLEDGE_LIBRARY_TYPES.reduce(
      (total, view) => total + knowledgeSurfaceStatusCount(summary.surfaces, view.type, status),
      0,
    );
  }
  return knowledgeSurfaceStatusCount(summary.surfaces, type, status);
}

function selectedTypeLabel(type: LibraryTypeFilter): string {
  return type === "all" ? "all memories" : type.replaceAll("_", " ");
}

function noObjectsLabel(status: LibraryStatusFilter): string {
  if (status === "all") return "No objects";
  return `No ${status} objects`;
}

function sourceKind(sourceId: string): string {
  const prefix = sourceId.includes(":") ? sourceId.split(":", 1)[0] : "source";
  if (prefix === "knowledge") return "memory";
  return prefix;
}

function CopyableBlock({
  label,
  value,
  copied,
  onCopy,
  collapsed = false,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
  collapsed?: boolean;
}) {
  return (
    <section className="mt-3 rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h4 className="m-0 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">{label}</h4>
        <TinyCopyButton copied={copied} onClick={onCopy} />
      </div>
      <pre
        className={clsx(
          "m-0 overflow-auto whitespace-pre-wrap break-words rounded-[7px] border border-line-soft bg-surface-soft/50 p-3 text-xs leading-relaxed text-ink-soft scroll-thin",
          collapsed ? "max-h-56 font-mono" : "max-h-[42vh] font-sans",
        )}
      >
        {value || "—"}
      </pre>
    </section>
  );
}

function TinyCopyButton({ copied, onClick }: { copied: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-line-soft bg-surface-soft px-2.5 py-1 text-2xs font-medium text-faint transition hover:border-accent/50 hover:text-ink"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function formatMetadataJson(metadata: Record<string, unknown>): string {
  try {
    return JSON.stringify(metadata, null, 2);
  } catch {
    return String(metadata);
  }
}

function MetadataRows({ metadata }: { metadata: Record<string, unknown> }) {
  const rows = Object.entries(metadata)
    .filter(([key]) => key !== "entity_graph" && key !== "entities")
    .map(([key, value]) => [key, formatMetadataValue(value)] as const)
    .filter(([, value]) => value.length > 0);

  if (rows.length === 0) {
    return <p className="m-0 text-sm italic text-faint">No extra details</p>;
  }

  return (
    <dl className="m-0 grid gap-2">
      {rows.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[160px_minmax(0,1fr)] gap-3 rounded-[7px] border border-line-soft px-3 py-2">
          <dt className="font-mono text-2xs text-faint">{humanizeKey(key)}</dt>
          <dd className="m-0 whitespace-pre-wrap break-words text-sm text-ink-soft">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function humanizeKey(key: string): string {
  return key.replaceAll("_", " ");
}

function formatMetadataValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(formatMetadataValue).filter(Boolean).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${humanizeKey(key)}: ${formatMetadataValue(nested)}`)
      .filter((line) => !line.endsWith(": "))
      .join("\n");
  }
  return String(value);
}
