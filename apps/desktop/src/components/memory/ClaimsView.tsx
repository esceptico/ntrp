import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import type { AppConfig } from "../../api";
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
  Pill,
  SearchInput,
  Sep,
} from "./shared";
import { feedbackTone, provenanceLabel, provenanceTone, relativeTime, truncate } from "./lens";

const DEBOUNCE = 220;

export function ClaimsView({
  config,
  focusId,
  onProvenance,
}: {
  config: AppConfig;
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

  useEffect(() => {
    if (focusId) setSelectedId(focusId);
  }, [focusId]);

  const runDefault = useCallback(() => {
    setLoading(true);
    listMemoryItems(config, { kind: "claim", limit: 100 })
      .then((r) => {
        setItems(r.items);
        setDegraded(false);
        setError(null);
        setSelectedId((cur) => cur ?? r.items[0]?.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [config]);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      runDefault();
      return;
    }
    setLoading(true);
    const handle = setTimeout(() => {
      searchMemory(config, { q, mode: "fts", limit: 50 })
        .then((r: MemorySearchResponse) => {
          const list = r.mode === "fts" ? r.items : r.items.map((i) => i.item);
          setItems(list);
          setDegraded(r.degraded);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    }, DEBOUNCE);
    return () => clearTimeout(handle);
  }, [query, config, runDefault]);

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={<SearchInput value={query} onChange={setQuery} placeholder="Search claims…" />}
          items={items}
          loading={loading}
          error={error ? <ListError title="Search failed" message={error} /> : undefined}
          empty={query.trim() ? "No claims match." : "No claims yet."}
          totalLabel={
            degraded
              ? "FTS unavailable — showing raw matches"
              : items.length
                ? `${items.length} claim${items.length === 1 ? "" : "s"}`
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
          <ClaimDetail config={config} claimId={selectedId} onProvenance={() => onProvenance(selectedId)} />
        ) : (
          <DetailPlaceholder>Search your memory, or select a claim.</DetailPlaceholder>
        )
      }
    />
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
        <span className="flex items-center gap-1.5">
          <Badge tone={provenanceTone(item.provenance)} size="sm">
            {provenanceLabel(item.provenance)}
          </Badge>
          {item.invalid_at && (
            <Badge tone="neutral" size="sm">
              closed
            </Badge>
          )}
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
}: {
  config: AppConfig;
  claimId: string;
  onProvenance: () => void;
}) {
  const [item, setItem] = useState<MemoryItem | null>(null);
  const [parents, setParents] = useState<MemoryEdge[]>([]);
  const [children, setChildren] = useState<MemoryEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getMemoryItem(config, claimId)
      .then((d) => {
        setItem(d.item);
        setParents(d.parents);
        setChildren(d.children);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [config, claimId]);

  const lensMemberships = useMemo(() => parents.filter((e) => e.role === "member_of"), [parents]);
  const contradicts = useMemo(
    () => [...parents, ...children].filter((e) => e.role === "contradicts"),
    [parents, children],
  );
  const supersedes = useMemo(() => parents.filter((e) => e.role === "supersedes"), [parents]);

  if (loading && !item) return <DetailPlaceholder>Loading claim…</DetailPlaceholder>;
  if (error) return <div className="p-7"><ListError title="Couldn't load claim" message={error} /></div>;
  if (!item) return <DetailPlaceholder>Claim not found.</DetailPlaceholder>;

  const validity = item.invalid_at
    ? `closed ${relativeTime(item.invalid_at)}`
    : item.valid_from
      ? `current since ${relativeTime(item.valid_from)}`
      : "current";

  return (
    <DetailShell
      header={
        <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={SPRING_CARD}>
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
          </div>
        </motion.div>
      }
      body={
        <div className="mt-2 flex flex-col gap-6">
          {/* trust signals — four quiet stats, deliberately no single confidence score */}
          <div className="grid grid-cols-4 gap-2">
            <Stat label="provenance" value={provenanceLabel(item.provenance)} />
            <Stat label="corroboration" value={String(item.corroboration)} />
            <Stat label="last relevant" value={relativeTime(item.last_relevant_at)} />
            <Stat label="feedback" value={item.feedback} />
          </div>

          {lensMemberships.length > 0 && (
            <Section title="In lenses">
              <div className="flex flex-wrap gap-1.5">
                {lensMemberships.map((e) => (
                  <Pill key={e.parent_id} tone="accent">
                    {truncate(e.parent_id, 10)}
                  </Pill>
                ))}
              </div>
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
          className="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-sm text-ink-soft transition-colors hover:bg-surface-soft hover:text-ink"
        >
          View provenance →
        </button>
      }
    />
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-surface-soft/50 px-2.5 py-2">
      <div className="text-2xs uppercase tracking-wide text-faint">{label}</div>
      <div className="mt-0.5 truncate text-sm text-ink-soft tabular-nums">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">{title}</h3>
      {children}
    </div>
  );
}
