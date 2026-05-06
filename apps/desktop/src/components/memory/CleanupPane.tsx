import { useEffect, useMemo, useState } from "react";
import { Archive, ExternalLink, RefreshCw } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type MemoryPruneCandidate,
  type MemoryPruneDryRun,
  applyMemoryPruneApi,
  getMemoryPruneDryRunApi,
  listMemoryEventsApi,
} from "../../api";
import { formatAbs, formatRelativePast } from "../../lib/format";
import {
  MEMORY_MAINTENANCE_REVIEW_ACTION,
  type MemoryMaintenanceReview,
  latestMemoryMaintenanceReview,
} from "../../lib/memoryMaintenance";
import { DetailPlaceholder, ErrorPill, GhostBtn, ListColumn, PaneShell, Pill, PrimaryBtn, SearchInput } from "./shared";

export function CleanupPane({ onOpenPattern }: { onOpenPattern?: (patternId: number) => void }) {
  const config = useStore((s) => s.config);
  const [dryRun, setDryRun] = useState<MemoryPruneDryRun | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [maintenanceReview, setMaintenanceReview] = useState<MemoryMaintenanceReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    const [result, eventResult] = await Promise.all([
      getMemoryPruneDryRunApi(config),
      listMemoryEventsApi(config, 1, { action: MEMORY_MAINTENANCE_REVIEW_ACTION }),
    ]);
    setDryRun(result);
    setMaintenanceReview(latestMemoryMaintenanceReview(eventResult.events));
    setSelectedId((current) => current ?? result.candidates[0]?.id ?? null);
  }

  useEffect(() => {
    void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const filtered = useMemo(() => {
    if (!dryRun) return null;
    const q = query.trim().toLowerCase();
    if (!q) return dryRun.candidates;
    return dryRun.candidates.filter((candidate) =>
      candidate.summary.toLowerCase().includes(q) || candidate.reason.toLowerCase().includes(q)
    );
  }, [dryRun, query]);

  const selected = dryRun?.candidates.find((candidate) => candidate.id === selectedId) ?? null;

  async function archiveSelected() {
    if (!dryRun || !selected) return;
    if (!confirm("Archive this cleanup candidate?")) return;
    await apply(false, selected.id);
  }

  async function archiveAll() {
    if (!dryRun) return;
    if (!confirm(`Archive all ${dryRun.summary.total} currently matching cleanup candidates?`)) return;
    await apply(true);
  }

  async function apply(allMatching: boolean, observationId?: number) {
    if (!dryRun) return;
    setBusy(true);
    setError(null);
    try {
      const result = await applyMemoryPruneApi(config, {
        observation_ids: observationId ? [observationId] : [],
        all_matching: allMatching,
        older_than_days: dryRun.criteria.older_than_days,
        max_sources: dryRun.criteria.max_sources,
      });
      if (result.archived === 0) setError("No candidates were archived; the review criteria may no longer match.");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={
            <div className="grid w-full gap-2">
              <SearchInput value={query} onChange={setQuery} placeholder="Filter cleanup candidates" />
              <MaintenanceReviewNote review={maintenanceReview} />
            </div>
          }
          loading={dryRun === null && !error}
          empty="No cleanup candidates."
          totalLabel={dryRun ? `${filtered?.length ?? 0} of ${dryRun.summary.total}` : null}
          items={filtered ?? []}
          renderItem={(candidate) => (
            <CleanupRow
              key={candidate.id}
              candidate={candidate}
              selected={candidate.id === selectedId}
              onSelect={() => setSelectedId(candidate.id)}
            />
          )}
        />
      }
      detail={
        selected && dryRun ? (
          <CleanupDetail
            dryRun={dryRun}
            candidate={selected}
            busy={busy}
            error={error}
            onRefresh={() => void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)))}
            onOpenPattern={() => onOpenPattern?.(selected.id)}
            onArchiveSelected={() => void archiveSelected()}
            onArchiveAll={() => void archiveAll()}
            maintenanceReview={maintenanceReview}
          />
        ) : error ? (
          <DetailPlaceholder>{error}</DetailPlaceholder>
        ) : (
          <DetailPlaceholder>Select a cleanup candidate</DetailPlaceholder>
        )
      }
    />
  );
}

function MaintenanceReviewNote({ review }: { review: MemoryMaintenanceReview | null }) {
  if (!review) return null;
  const issueCount = review.storageIssues + review.provenanceIssues + review.relationIssues;
  return (
    <div className="rounded-md border border-line-soft bg-surface px-2.5 py-2">
      <div className="flex items-center justify-between gap-2 text-[11px] text-faint">
        <span>Maintenance</span>
        <span>{formatRelativePast(review.event.created_at)}</span>
      </div>
      <div className="mt-1 text-[12px] text-ink-soft">
        {review.cleanupCandidateCount} cleanup candidates
        {issueCount > 0 ? ` · ${issueCount} integrity issues` : ""}
      </div>
    </div>
  );
}

function CleanupRow({
  candidate,
  selected,
  onSelect,
}: {
  candidate: MemoryPruneCandidate;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "w-full rounded-md px-4 py-2.5 text-left transition-colors",
        selected ? "bg-surface-soft text-ink" : "text-ink-soft hover:bg-surface-soft/50",
      )}
    >
      <div className="text-[12.5px] leading-snug line-clamp-2">{candidate.summary}</div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-faint">
        <span>{candidate.evidence_count} sources</span>
        <span aria-hidden>·</span>
        <span>{candidate.chars.toLocaleString()} chars</span>
        <span aria-hidden>·</span>
        <span>{formatRelativePast(candidate.created_at)}</span>
      </div>
    </button>
  );
}

function CleanupDetail({
  dryRun,
  candidate,
  busy,
  error,
  onRefresh,
  onOpenPattern,
  onArchiveSelected,
  onArchiveAll,
  maintenanceReview,
}: {
  dryRun: MemoryPruneDryRun;
  candidate: MemoryPruneCandidate;
  busy: boolean;
  error: string | null;
  onRefresh: () => void;
  onOpenPattern: () => void;
  onArchiveSelected: () => void;
  onArchiveAll: () => void;
  maintenanceReview: MemoryMaintenanceReview | null;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="px-7 pt-6 pb-3">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="m-0 text-[15px] font-semibold tracking-[-0.01em] text-ink">Review cleanup candidate</h3>
          <Pill tone="warn">{candidate.reason}</Pill>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-faint">
          <span>older than {dryRun.criteria.older_than_days}d</span>
          <span aria-hidden>·</span>
          <span>max {dryRun.criteria.max_sources} sources</span>
          <span aria-hidden>·</span>
          <span>{dryRun.summary.total} candidates in dry-run</span>
          {maintenanceReview && (
            <>
              <span aria-hidden>·</span>
              <span>maintenance saw {maintenanceReview.cleanupCandidateCount}</span>
            </>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin px-7">
        <p className="m-0 whitespace-pre-wrap text-[14px] leading-relaxed text-ink">{candidate.summary}</p>
        <dl className="mt-6 grid grid-cols-[130px_minmax(0,1fr)] gap-y-2 text-[12px]">
          <dt className="text-faint">Created</dt>
          <dd className="text-ink-soft">{formatAbs(candidate.created_at)}</dd>
          <dt className="text-faint">Updated</dt>
          <dd className="text-ink-soft">{formatAbs(candidate.updated_at)}</dd>
          <dt className="text-faint">Access count</dt>
          <dd className="text-ink-soft">{candidate.access_count}</dd>
          <dt className="text-faint">Evidence count</dt>
          <dd className="text-ink-soft">{candidate.evidence_count}</dd>
          <dt className="text-faint">Length</dt>
          <dd className="text-ink-soft">{candidate.chars.toLocaleString()} chars</dd>
        </dl>
      </div>

      <div className="flex items-center justify-end gap-2 px-7 py-3">
        {error && <ErrorPill message={error} />}
        <GhostBtn onClick={onRefresh} disabled={busy}>
          <RefreshCw size={12} strokeWidth={1.8} /> Refresh
        </GhostBtn>
        <GhostBtn onClick={onOpenPattern} disabled={busy}>
          <ExternalLink size={12} strokeWidth={1.8} /> Open pattern
        </GhostBtn>
        <GhostBtn onClick={onArchiveAll} disabled={busy || dryRun.summary.total === 0}>
          <Archive size={12} strokeWidth={1.8} /> Archive all
        </GhostBtn>
        <PrimaryBtn onClick={onArchiveSelected} disabled={busy}>
          {busy ? "Archiving…" : "Archive selected"}
        </PrimaryBtn>
      </div>
    </div>
  );
}
