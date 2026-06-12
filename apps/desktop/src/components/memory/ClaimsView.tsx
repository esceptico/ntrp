import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { X } from "lucide-react";
import type { AppConfig } from "../../api";
import { ICON } from "../../lib/icons";
import {
  getMemoryItem,
  listMemoryItems,
  searchMemory,
  type MemoryEdge,
  type MemoryItem,
  type MemorySearchResponse,
} from "../../api/memoryItems";
import { SPRING_CARD } from "../../lib/tokens/motion";
import { Badge } from "../Badge";
import {
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ListColumn,
  ListError,
  MetaGrid,
  PaneShell,
  SearchInput,
  Sep,
} from "./shared";
import { feedbackTone, provenanceLabel, provenanceTone, relativeTime, truncate } from "./lens";

const DEBOUNCE = 220;

export function ClaimsView({
  config,
  scope,
  focusId,
  onProvenance,
}: {
  config: AppConfig;
  /** null = all scopes (one connected view); a value filters to that scope. */
  scope: { kind: "user" | "project" | "session"; key: string | null } | null;
  /** External request to open a specific claim (peel-in from a lens). */
  focusId: string | null;
  onProvenance: (claimId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [degraded, setDegraded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(focusId);
  // The one split that IS the model: everything / observed (ground) / inferred.
  const [epistemic, setEpistemic] = useState<"all" | "ground" | "inferred">("all");
  // Label filter is client-side over item.labels — set by clicking a chip in
  // the detail, cleared from the toolbar chip (or by toggling the same chip).
  const [labelFilter, setLabelFilter] = useState<string | null>(null);

  useEffect(() => {
    if (focusId) setSelectedId(focusId);
  }, [focusId]);

  const runDefault = useCallback(() => {
    setLoading(true);
    listMemoryItems(config, { limit: 100, scope_kind: scope?.kind, scope_key: scope?.key ?? undefined })
      .then((r) => {
        setItems(r.items);
        setDegraded(false);
        setError(null);
        setSelectedId((cur) => cur ?? r.items[0]?.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [config, scope?.kind, scope?.key]);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      runDefault();
      return;
    }
    setLoading(true);
    // Debounce only prevents overlap within the window; slower typing leaves two
    // fetches in flight, and a slow earlier query's response can land last and
    // overwrite newer results. Drop stale responses (same guard as ClaimDetail).
    let alive = true;
    const handle = setTimeout(() => {
      searchMemory(config, { q, mode: "fts", limit: 50, scope_kind: scope?.kind, scope_key: scope?.key ?? undefined })
        .then((r: MemorySearchResponse) => {
          if (!alive) return;
          const list = r.mode === "fts" ? r.items : r.items.map((i) => i.item);
          setItems(list);
          setDegraded(r.degraded);
          setError(null);
        })
        .catch((e) => {
          if (alive) setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, DEBOUNCE);
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [query, config, runDefault, scope?.kind, scope?.key]);

  const inferredCount = useMemo(
    () => items.filter((i) => i.provenance === "inferred").length,
    [items],
  );
  const shown = items.filter(
    (i) =>
      (epistemic === "all" ||
        (epistemic === "inferred" ? i.provenance === "inferred" : i.provenance !== "inferred")) &&
      (!labelFilter || i.labels.includes(labelFilter)),
  );

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={
            <div className="flex flex-col gap-2">
              <SearchInput value={query} onChange={setQuery} placeholder="Search claims…" />
              <div className="flex flex-wrap items-center gap-1">
                <FilterChip label="All" count={items.length} active={epistemic === "all"} onClick={() => setEpistemic("all")} />
                <FilterChip label="Observed" count={items.length - inferredCount} active={epistemic === "ground"} onClick={() => setEpistemic("ground")} />
                <FilterChip label="Inferred" count={inferredCount} active={epistemic === "inferred"} onClick={() => setEpistemic("inferred")} />
                {labelFilter && (
                  <button
                    type="button"
                    onClick={() => setLabelFilter(null)}
                    title="Clear label filter"
                    className="inline-flex h-6 items-center gap-1 rounded-full bg-accent-soft px-2 text-2xs font-medium tracking-[-0.005em] text-accent-strong transition-[background-color,color,scale] duration-check ease-out select-none active:scale-[0.97]"
                  >
                    {labelFilter}
                    <X size={ICON.XS} strokeWidth={2} />
                  </button>
                )}
              </div>
            </div>
          }
          items={shown}
          loading={loading}
          error={error ? <ListError title="Search failed" message={error} /> : undefined}
          empty={query.trim() || labelFilter ? "No claims match." : "No claims yet."}
          totalLabel={
            degraded
              ? "FTS unavailable — showing raw matches"
              : shown.length
                ? `${shown.length} ${epistemic === "inferred" ? "inference" : "record"}${shown.length === 1 ? "" : "s"}${labelFilter ? ` · ${labelFilter}` : ""}`
                : null
          }
          renderItem={(item) => (
            <ClaimRow
              key={item.id}
              item={item}
              active={item.id === selectedId}
              onSelect={() => setSelectedId(item.id)}
            />
          )}
        />
      }
      detail={
        selectedId ? (
          <ClaimDetail
            config={config}
            claimId={selectedId}
            onProvenance={() => onProvenance(selectedId)}
            activeLabel={labelFilter}
            onLabelFilter={(label) => setLabelFilter((cur) => (cur === label ? null : label))}
            onOpenClaim={setSelectedId}
          />
        ) : (
          <DetailPlaceholder>Search your memory, or select a claim.</DetailPlaceholder>
        )
      }
    />
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-6 px-2 rounded-full text-2xs font-medium tracking-[-0.005em] transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] select-none ${
        active ? "bg-accent-soft text-accent-strong" : "text-muted hover:bg-surface-soft hover:text-ink"
      }`}
    >
      {label} <span className="tabular-nums opacity-60">{count}</span>
    </button>
  );
}

function ClaimRow({ item, active, onSelect }: { item: MemoryItem; active: boolean; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-selected={active}
        className="app-row group flex w-full flex-col gap-1 rounded-md px-2.5 py-2 text-left"
      >
        <span className="line-clamp-2 text-sm leading-snug text-ink">{truncate(item.content, 140)}</span>
        <span className="flex flex-wrap items-center gap-1.5">
          <Badge tone={provenanceTone(item.provenance)} size="sm">
            {provenanceLabel(item.provenance)}
          </Badge>
          {item.standing === "unresolved" && (
            <Badge tone="warn" size="sm">
              re-checking
            </Badge>
          )}
          {item.invalid_at && (
            <Badge tone="neutral" size="sm">
              closed
            </Badge>
          )}
          {item.labels.map((label) => (
            <Badge key={label} tone="neutral" size="sm">
              {label}
            </Badge>
          ))}
          {item.corroboration > 0 && (
            <span className="text-2xs text-faint tabular-nums">×{item.corroboration}</span>
          )}
        </span>
      </button>
    </li>
  );
}

function ClaimDetail({
  config,
  claimId,
  onProvenance,
  activeLabel,
  onLabelFilter,
  onOpenClaim,
}: {
  config: AppConfig;
  claimId: string;
  onProvenance: () => void;
  /** The list's current label filter — its chip renders accented here. */
  activeLabel: string | null;
  /** Clicking a label chip filters the list to that label (toggles off). */
  onLabelFilter: (label: string) => void;
  /** Walk the derivation DAG: open a premise/dependent claim in this pane. */
  onOpenClaim: (id: string) => void;
}) {
  const [item, setItem] = useState<MemoryItem | null>(null);
  const [parents, setParents] = useState<MemoryEdge[]>([]);
  const [children, setChildren] = useState<MemoryEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // ClaimDetail is reused (no key prop) across selection changes, so rapid
    // A→B→C clicks fire overlapping fetches. Drop any response that resolves
    // after the selection moved on, else a slow earlier reply overwrites the
    // current claim (same alive-flag pattern as GraphView/LensesView).
    let alive = true;
    setLoading(true);
    // Clear stale state for the previous selection so a prior fetch's error (or the
    // old claim's content) doesn't render while this one is in flight.
    setError(null);
    setItem(null);
    getMemoryItem(config, claimId)
      .then((d) => {
        if (!alive) return;
        setItem(d.item);
        setParents(d.parents);
        setChildren(d.children);
        setError(null);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [config, claimId]);

  const contradicts = useMemo(
    () => [...parents, ...children].filter((e) => e.role === "contradicts"),
    [parents, children],
  );
  const supersedes = useMemo(() => parents.filter((e) => e.role === "supersedes"), [parents]);
  const premises = useMemo(() => parents.filter((e) => e.role === "evidence"), [parents]);
  const dependents = useMemo(() => children.filter((e) => e.role === "evidence"), [children]);

  if (loading && !item) return <DetailPlaceholder>Loading claim…</DetailPlaceholder>;
  if (error) return <div className="p-7"><ListError title="Couldn't load claim" message={error} /></div>;
  if (!item) return <DetailPlaceholder>Claim not found.</DetailPlaceholder>;

  const validity = item.invalid_at
    ? `closed ${relativeTime(item.invalid_at)}`
    : item.valid_from
      ? `current since ${relativeTime(item.valid_from)}`
      : "current";

  return (
    // One entrance for the whole detail — header, stats, and sections rise as
    // a unit (remounts via the loading placeholder on each selection).
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={SPRING_CARD}
      className="h-full"
    >
      <DetailShell
        header={
          <div>
            <p className="text-base leading-[1.5] text-ink">{item.content}</p>
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              <Badge tone={provenanceTone(item.provenance)} size="md">
                {provenanceLabel(item.provenance)}
              </Badge>
              {item.feedback !== "none" && (
                <Badge tone={feedbackTone(item.feedback)} size="md">
                  {item.feedback}
                </Badge>
              )}
              <Badge tone={item.invalid_at ? "neutral" : "ok"} size="md">
                {validity}
              </Badge>
              {item.standing && item.standing !== "active" && (
                <Badge tone={item.standing === "unresolved" ? "warn" : "neutral"} size="md">
                  {item.standing === "unresolved" ? "premise changed — re-checking" : "retired"}
                </Badge>
              )}
            </div>
          </div>
        }
        body={
          <div className="mt-2 flex flex-col gap-6">
            {/* trust signals — four quiet stats, deliberately no single confidence score */}
            <div className="grid grid-cols-4 gap-2">
              <Stat label="provenance" value={provenanceLabel(item.provenance)} />
              <Stat
                label={item.provenance === "inferred" ? "depth" : "corroboration"}
                value={String(item.provenance === "inferred" ? (item.depth ?? 1) : item.corroboration)}
              />
              <Stat label="last relevant" value={relativeTime(item.last_relevant_at)} />
              <Stat label="feedback" value={item.feedback} />
            </div>

            {item.labels.length > 0 && (
              <Section title="Labels">
                <div className="flex flex-wrap gap-1.5">
                  {item.labels.map((label) => (
                    <button
                      key={label}
                      type="button"
                      onClick={() => onLabelFilter(label)}
                      title={activeLabel === label ? "Clear label filter" : `Filter claims labeled ${label}`}
                      className="transition-[scale] duration-check ease-out active:scale-[0.97]"
                    >
                      <Badge
                        tone={activeLabel === label ? "accent" : "neutral"}
                        size="md"
                        className="cursor-pointer transition-colors hover:bg-accent-soft hover:text-accent-strong"
                      >
                        {label}
                      </Badge>
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {premises.length > 0 && (
              <Section title="Because of">
                <EdgeList edges={premises} pick={(e) => e.parent_id} config={config} onOpen={onOpenClaim} />
              </Section>
            )}

            {dependents.length > 0 && (
              <Section title="Supports">
                <EdgeList edges={dependents} pick={(e) => e.child_id} config={config} onOpen={onOpenClaim} />
              </Section>
            )}

            {supersedes.length > 0 && (
              <Section title="Supersedes">
                {supersedes.map((e) => (
                  <div key={e.parent_id} className="text-sm text-faint">
                    → {truncate(e.parent_id, 18)}
                  </div>
                ))}
              </Section>
            )}

            {contradicts.length > 0 && (
              <Section title="Contradicted by">
                {contradicts.map((e) => {
                  const otherId = e.child_id === item.id ? e.parent_id : e.child_id;
                  return (
                    <div key={`${e.child_id}-${e.parent_id}`} className="text-sm text-bad">
                      ⚠ {truncate(otherId, 18)}
                    </div>
                  );
                })}
              </Section>
            )}

            {item.source_refs.length > 0 && (
              <Section title="Sources">
                <MetaGrid
                  rows={item.source_refs.map((r) => ({
                    label: r.kind,
                    value: `${truncate(r.ref, 40)} · ${relativeTime(r.captured_at)}`,
                    mono: true,
                  }))}
                />
              </Section>
            )}
          </div>
        }
        meta={
          <DetailMeta>
            <span className="font-mono">{item.id}</span>
            <Sep />
            <span>created {relativeTime(item.created_at)}</span>
          </DetailMeta>
        }
        actions={
          <button
            type="button"
            onClick={onProvenance}
            className="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-sm text-ink-soft transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] hover:bg-surface-soft hover:text-ink"
          >
            View provenance →
          </button>
        }
      />
    </motion.div>
  );
}

/** Premise/dependent rows of the derivation DAG — each fetches its claim text
 *  and opens it in this pane on click ("what do I know and why", walkable). */
function EdgeList({
  edges,
  pick,
  config,
  onOpen,
}: {
  edges: MemoryEdge[];
  pick: (e: MemoryEdge) => string;
  config: AppConfig;
  onOpen: (id: string) => void;
}) {
  const [texts, setTexts] = useState<Record<string, string>>({});
  useEffect(() => {
    let alive = true;
    const ids = [...new Set(edges.map(pick))];
    Promise.all(
      ids.map((id) =>
        getMemoryItem(config, id)
          .then((d) => [id, d.item.content] as const)
          .catch(() => [id, id] as const),
      ),
    ).then((pairs) => {
      if (alive) setTexts(Object.fromEntries(pairs));
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, edges.map(pick).join("|")]);

  return (
    <div className="flex flex-col gap-1">
      {[...new Set(edges.map(pick))].map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onOpen(id)}
          className="app-row rounded-md px-2 py-1.5 text-left text-sm leading-snug text-muted hover:text-ink"
          title="Open this claim"
        >
          {truncate(texts[id] ?? "…", 120)}
        </button>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-surface-soft/50 px-2.5 py-2">
      <div className="text-2xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-0.5 truncate text-sm text-ink-soft tabular-nums">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      {children}
    </div>
  );
}
