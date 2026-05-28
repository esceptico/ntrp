import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getMemoryGraph,
  getMemoryItem,
  getMemoryToday,
  listMemoryItems,
  listMemorySkills,
  setMemorySkillEnabled,
  type MemoryGraph,
  type MemoryItemDetail,
  type MemoryItemKind,
  type MemoryItemStatus,
  type MemoryItemSummary,
  type MemoryToday,
  type MemoryValidityFilter,
} from "../../api/memoryItems";
import type { AppConfig } from "../../api";
import { useStore } from "../../store";
import {
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ErrorPill,
  GhostBtn,
  JsonBlock,
  ListColumn,
  ListError,
  MetaGrid,
  PaneShell,
  Pill,
  SearchInput,
  Sep,
} from "./shared";

type Tab = "today" | "graph" | "skills" | "search";
type Direction = "parents" | "children" | "both";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "today", label: "Today", hint: "review queue" },
  { id: "graph", label: "Graph", hint: "provenance" },
  { id: "skills", label: "Skills", hint: "procedures" },
  { id: "search", label: "Search", hint: "hybrid" },
];
const KINDS: MemoryItemKind[] = ["episode", "observation", "claim", "skill", "proposal", "artifact_ref"];
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
                ? "bg-surface-soft text-ink shadow-[inset_0_0_0_1px_var(--line-soft)]"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            ].join(" ")}
          >
            <div className="text-sm font-semibold tracking-[-0.01em]">{entry.label}</div>
            <div className="text-[11px] text-faint">{entry.hint}</div>
          </button>
        ))}
      </nav>

      <PaneShell
        list={
          <>
            {tab === "today" && <TodayList config={config} onSelect={selectItem} selectedId={selectedId} />}
            {tab === "graph" && <GraphList config={config} rootId={selectedId} onSelect={selectItem} selectedId={selectedId} />}
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
          />
        }
      />
    </div>
  );
}

function TodayList({ config, onSelect, selectedId }: { config: AppConfig; onSelect: (item: MemoryItemSummary, tab?: Tab) => void; selectedId: string | null }) {
  const [today, setToday] = useState<MemoryToday | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }, [config]);

  const rows = useMemo(() => flattenToday(today), [today]);
  return (
    <ListColumn
      toolbar={<SectionTitle title="Today" subtitle="proposals, corrections, weak claims" />}
      items={rows}
      loading={!today && !error}
      error={error ? <ListError title="Could not load Today" message={error} /> : null}
      empty="No memory review items."
      totalLabel={today ? `${rows.length} review items` : null}
      renderItem={(row) => (
        <MemoryRow
          key={`${row.section}:${row.item.id}`}
          item={row.item}
          eyebrow={row.section}
          selected={row.item.id === selectedId}
          onClick={() => onSelect(row.item, row.defaultTab)}
        />
      )}
    />
  );
}

function GraphList({ config, rootId, onSelect, selectedId }: { config: AppConfig; rootId: string | null; onSelect: (item: MemoryItemSummary) => void; selectedId: string | null }) {
  const [input, setInput] = useState(rootId ?? "");
  const [direction, setDirection] = useState<Direction>("both");
  const [graph, setGraph] = useState<MemoryGraph | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (rootId) setInput(rootId);
  }, [rootId]);

  const load = useCallback((idOverride?: string) => {
    const id = (idOverride ?? input).trim();
    if (!id) return;
    setError(null);
    getMemoryGraph(config, id, 3, direction)
      .then(setGraph)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [config, direction, input]);

  useEffect(() => {
    if (rootId) load(rootId);
  }, [load, rootId]);

  const edgeSummary = graph ? `${graph.nodes.length} nodes · ${graph.edges.length} edges` : null;
  return (
    <ListColumn
      toolbar={
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <SectionTitle title="Graph" subtitle="real parent DAG neighborhood" />
          <div className="flex items-center gap-2">
            <SearchInput value={input} onChange={setInput} placeholder="root memory id" />
            <FilterSelect value={direction} onChange={(value) => setDirection(value as Direction)} options={["both", "parents", "children"]} label="direction" />
            <GhostBtn onClick={() => load()} disabled={!input.trim()}>Load</GhostBtn>
          </div>
        </div>
      }
      items={graph?.nodes ?? []}
      loading={false}
      error={error ? <ListError title="Could not load graph" message={error} /> : null}
      empty={input.trim() ? "No graph nodes found." : "Select a memory item or paste an id."}
      totalLabel={edgeSummary}
      renderItem={(item) => (
        <MemoryRow key={item.id} item={item} selected={item.id === selectedId} onClick={() => onSelect(item)} graph={graph ?? undefined} />
      )}
    />
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
              className="h-7 min-w-0 rounded-md border border-transparent bg-[rgba(0,0,0,0.04)] px-2 text-sm text-ink-soft outline-none transition-[background-color,border-color] placeholder:text-faint focus:border-line-soft focus:bg-[rgba(0,0,0,0.06)]"
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

function ItemDetail({
  config,
  detail,
  error,
  onOpenGraph,
  onSkillChanged,
}: {
  config: AppConfig;
  detail: MemoryItemDetail | null;
  error: string | null;
  onOpenGraph: (item: MemoryItemSummary) => void;
  onSkillChanged: () => void;
}) {
  const [saving, setSaving] = useState(false);

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
          <h2 className="text-lg font-semibold leading-snug tracking-[-0.012em] text-ink">{shortTitle(item.content)}</h2>
          <DetailMeta>
            <span className="font-mono">{item.id}</span>
            <Sep />
            <span>{formatDate(item.created_at)}</span>
          </DetailMeta>
        </div>
      }
      body={
        <div className="space-y-5">
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Content</h3>
            <div className="whitespace-pre-wrap rounded-[10px] border border-line-soft bg-surface-soft px-3 py-2 text-sm leading-relaxed text-ink-soft">
              {item.content}
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
          {detail.parents.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Parents</h3>
              <div className="space-y-2">
                {detail.parents.map((parent) => (
                  <div key={`${parent.role}:${parent.parent_id}`} className="rounded-[10px] border border-line-soft bg-surface-soft px-3 py-2">
                    <div className="mb-1 flex items-center gap-2">
                      <Pill>{parent.role}</Pill>
                      <span className="truncate font-mono text-xs text-faint">{parent.parent_id}</span>
                    </div>
                    {parent.parent && <p className="line-clamp-2 text-sm text-ink-soft">{parent.parent.content}</p>}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      }
      meta={
        <div className="space-y-3">
          {item.tags.length > 0 && <JsonBlock value={{ tags: item.tags }} />}
          {item.source_refs.length > 0 && <JsonBlock value={{ source_refs: item.source_refs }} />}
          {item.artifact_ref ? <JsonBlock value={{ artifact_ref: item.artifact_ref }} /> : null}
        </div>
      }
      actions={
        <>
          {item.kind === "skill" && <GhostBtn onClick={toggleSkill} disabled={saving}>{enabled ? "Disable" : "Enable"}</GhostBtn>}
          <GhostBtn onClick={() => onOpenGraph(item)}>Open graph</GhostBtn>
        </>
      }
    />
  );
}

function MemoryRow({ item, selected, onClick, eyebrow, graph }: { item: MemoryItemSummary; selected: boolean; onClick: () => void; eyebrow?: string; graph?: MemoryGraph }) {
  const edgeCount = graph ? graph.edges.filter((edge) => edge.child_id === item.id || edge.parent_id === item.id).length : null;
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={[
          "w-full rounded-[10px] px-3 py-2.5 text-left transition-colors",
          selected ? "bg-surface-soft shadow-[inset_0_0_0_1px_var(--line-soft)]" : "hover:bg-surface-soft",
        ].join(" ")}
      >
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          {eyebrow && <span className="mr-1 text-[11px] font-medium uppercase tracking-wide text-faint">{eyebrow}</span>}
          <Pill tone="accent">{item.kind}</Pill>
          <Pill tone={statusTone(item.status)}>{item.status}</Pill>
          <Pill>{item.scope}</Pill>
          {edgeCount !== null && <Pill>{edgeCount} edges</Pill>}
        </div>
        <div className="line-clamp-3 text-sm leading-snug text-ink-soft">{item.content}</div>
        <div className="mt-1 truncate font-mono text-[11px] text-faint">{item.id}</div>
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
      className="h-7 min-w-0 rounded-md border border-transparent bg-[rgba(0,0,0,0.04)] px-2 text-sm text-ink-soft outline-none transition-[background-color,border-color] focus:border-line-soft focus:bg-[rgba(0,0,0,0.06)]"
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
    ...today.low_confidence_claims.map((item) => ({ section: "low confidence", item, defaultTab: "graph" as Tab })),
    ...today.recent_corrections.map((item) => ({ section: "correction", item, defaultTab: "graph" as Tab })),
  ];
}

function statusTone(status: MemoryItemStatus): "neutral" | "ok" | "warn" | "bad" {
  if (status === "active") return "ok";
  if (status === "superseded") return "warn";
  return "neutral";
}

function shortTitle(content: string): string {
  const compact = content.replace(/\s+/g, " ").trim();
  return compact.length > 140 ? `${compact.slice(0, 140)}…` : compact || "Untitled memory item";
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
