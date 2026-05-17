import { useEffect, useMemo, useState } from "react";
import { Archive, ExternalLink, GitCompareArrows, RefreshCw } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type Fact,
  type MemoryPruneCandidate,
  type MemoryPruneDryRun,
  applyMemoryPruneApi,
  getMemoryPruneDryRunApi,
  listMemoryEventsApi,
} from "../../api";
import { formatAbs, formatRelativePast } from "../../lib/format";
import {
  MEMORY_MAINTENANCE_REVIEW_ACTION,
  type DuplicateMemoryCandidate,
  type MemoryMaintenanceReview,
  latestMemoryMaintenanceReview,
} from "../../lib/memoryMaintenance";
import { DetailPlaceholder, ErrorPill, GhostBtn, ListColumn, PaneShell, Pill, PrimaryBtn, SearchInput } from "./shared";
import { ICON } from "../../lib/icons";

type DuplicateCandidateKind = "fact" | "pattern";

type CleanupListItem =
  | { kind: "cleanup"; key: string; candidate: MemoryPruneCandidate }
  | {
      kind: "duplicate";
      duplicateKind: DuplicateCandidateKind;
      key: string;
      candidate: DuplicateMemoryCandidate;
    };

export function CleanupPane({
  onOpenFact,
  onOpenPattern,
}: {
  onOpenFact?: (fact: Fact | number) => void;
  onOpenPattern?: (patternId: number) => void;
}) {
  const config = useStore((s) => s.config);
  const [dryRun, setDryRun] = useState<MemoryPruneDryRun | null>(null);
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
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
  }

  useEffect(() => {
    void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const listItems = useMemo(() => buildCleanupListItems(dryRun, maintenanceReview), [dryRun, maintenanceReview]);

  useEffect(() => {
    setSelectedKey((current) => {
      if (current && listItems.some((item) => item.key === current)) return current;
      return listItems[0]?.key ?? null;
    });
  }, [listItems]);

  const filtered = useMemo(() => {
    if (!dryRun) return null;
    const q = query.trim().toLowerCase();
    if (!q) return listItems;
    return listItems.filter((item) => cleanupListItemText(item).toLowerCase().includes(q));
  }, [dryRun, listItems, query]);

  const selected = listItems.find((item) => item.key === selectedKey) ?? null;
  const selectedCleanup = selected?.kind === "cleanup" ? selected.candidate : null;

  async function archiveSelected() {
    if (!dryRun || !selectedCleanup) return;
    if (!confirm("Archive this cleanup candidate?")) return;
    await apply(false, selectedCleanup.id);
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
          empty="No maintenance candidates."
          totalLabel={dryRun ? `${filtered?.length ?? 0} of ${listItems.length}` : null}
          items={filtered ?? []}
          renderItem={(item) =>
            item.kind === "cleanup" ? (
              <CleanupRow
                key={item.key}
                candidate={item.candidate}
                selected={item.key === selectedKey}
                onSelect={() => setSelectedKey(item.key)}
              />
            ) : (
              <DuplicateCandidateRow
                key={item.key}
                item={item}
                selected={item.key === selectedKey}
                onSelect={() => setSelectedKey(item.key)}
              />
            )
          }
        />
      }
      detail={
        selected?.kind === "cleanup" && dryRun ? (
          <CleanupDetail
            dryRun={dryRun}
            candidate={selected.candidate}
            busy={busy}
            error={error}
            onRefresh={() => void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)))}
            onOpenPattern={() => onOpenPattern?.(selected.candidate.id)}
            onArchiveSelected={() => void archiveSelected()}
            onArchiveAll={() => void archiveAll()}
            maintenanceReview={maintenanceReview}
          />
        ) : selected?.kind === "duplicate" ? (
          <DuplicateCandidateDetail
            item={selected}
            error={error}
            onRefresh={() => void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)))}
            onOpenFact={onOpenFact}
            onOpenPattern={onOpenPattern}
          />
        ) : error ? (
          <DetailPlaceholder>{error}</DetailPlaceholder>
        ) : (
          <DetailPlaceholder>Select a maintenance candidate</DetailPlaceholder>
        )
      }
    />
  );
}

function buildCleanupListItems(
  dryRun: MemoryPruneDryRun | null,
  review: MemoryMaintenanceReview | null,
): CleanupListItem[] {
  const cleanupItems: CleanupListItem[] =
    dryRun?.candidates.map((candidate) => ({
      kind: "cleanup",
      key: `cleanup:${candidate.id}`,
      candidate,
    })) ?? [];
  const factDuplicates = (review?.duplicateFactCandidates ?? []).map((candidate) =>
    duplicateListItem("fact", candidate),
  );
  const patternDuplicates = (review?.duplicateObservationCandidates ?? []).map((candidate) =>
    duplicateListItem("pattern", candidate),
  );
  return [...cleanupItems, ...factDuplicates, ...patternDuplicates];
}

function duplicateListItem(
  duplicateKind: DuplicateCandidateKind,
  candidate: DuplicateMemoryCandidate,
): CleanupListItem {
  return {
    kind: "duplicate",
    duplicateKind,
    key: `duplicate:${duplicateKind}:${candidate.ids[0]}:${candidate.ids[1]}`,
    candidate,
  };
}

function cleanupListItemText(item: CleanupListItem): string {
  if (item.kind === "cleanup") {
    return `${item.candidate.summary} ${item.candidate.reason}`;
  }
  return `${item.duplicateKind} duplicate ${item.candidate.ids.join(" ")} ${item.candidate.left} ${item.candidate.right}`;
}

function MaintenanceReviewNote({ review }: { review: MemoryMaintenanceReview | null }) {
  if (!review) return null;
  const issueCount = review.storageIssues + review.provenanceIssues + review.relationIssues;
  const duplicateCount = review.duplicateFactCandidateCount + review.duplicateObservationCandidateCount;
  return (
    <div className="rounded-md border border-line-soft bg-surface px-2.5 py-2">
      <div className="flex items-center justify-between gap-2 text-xs text-faint">
        <span>Maintenance</span>
        <span>{formatRelativePast(review.event.created_at)}</span>
      </div>
      <div className="mt-1 text-sm text-ink-soft">
        {review.cleanupCandidateCount} cleanup candidates
        {duplicateCount > 0 ? ` · ${duplicateCount} duplicate candidates` : ""}
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
      <div className="text-sm leading-snug line-clamp-2">{candidate.summary}</div>
      <div className="mt-1 flex items-center gap-2 text-xs text-faint">
        <span>{candidate.evidence_count} sources</span>
        <span aria-hidden>·</span>
        <span>{candidate.chars.toLocaleString()} chars</span>
        <span aria-hidden>·</span>
        <span>{formatRelativePast(candidate.created_at)}</span>
      </div>
    </button>
  );
}

function DuplicateCandidateRow({
  item,
  selected,
  onSelect,
}: {
  item: Extract<CleanupListItem, { kind: "duplicate" }>;
  selected: boolean;
  onSelect: () => void;
}) {
  const label = item.duplicateKind === "fact" ? "duplicate facts" : "duplicate patterns";
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "w-full rounded-md px-4 py-2.5 text-left transition-colors",
        selected ? "bg-surface-soft text-ink" : "text-ink-soft hover:bg-surface-soft/50",
      )}
    >
      <div className="mb-1 flex items-center gap-1.5">
        <GitCompareArrows size={ICON.XS} strokeWidth={2} className="text-faint" />
        <span className="text-xs uppercase tracking-[0.06em] text-faint">{label}</span>
        <span className="text-xs tabular-nums text-faint">{Math.round(item.candidate.score * 100)}%</span>
      </div>
      <div className="text-sm leading-snug line-clamp-2">{item.candidate.left}</div>
      <div className="mt-1 text-xs leading-snug text-faint line-clamp-1">{item.candidate.right}</div>
    </button>
  );
}

function DuplicateCandidateDetail({
  item,
  error,
  onRefresh,
  onOpenFact,
  onOpenPattern,
}: {
  item: Extract<CleanupListItem, { kind: "duplicate" }>;
  error: string | null;
  onRefresh: () => void;
  onOpenFact?: (fact: Fact | number) => void;
  onOpenPattern?: (patternId: number) => void;
}) {
  const label = item.duplicateKind === "fact" ? "duplicate fact candidate" : "duplicate pattern candidate";
  const noun = item.duplicateKind === "fact" ? "fact" : "pattern";
  const open = item.duplicateKind === "fact" ? onOpenFact : onOpenPattern;
  return (
    <div className="flex h-full flex-col">
      <div className="px-7 pt-6 pb-3">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="m-0 text-lg font-semibold tracking-[-0.01em] text-ink">Review {label}</h3>
          <Pill>review-only</Pill>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-faint">
          <span className="tabular-nums">score {(item.candidate.score * 100).toFixed(1)}%</span>
          <span aria-hidden>·</span>
          <span>
            {noun} #{item.candidate.ids[0]} and #{item.candidate.ids[1]}
          </span>
          <span aria-hidden>·</span>
          <span>no automatic merge</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin scroll-fade-top px-7">
        <div className="grid gap-3">
          <DuplicateSide
            label={`Left ${noun}`}
            id={item.candidate.ids[0]}
            text={item.candidate.left}
            onOpen={open ? () => open(item.candidate.ids[0]) : undefined}
          />
          <DuplicateSide
            label={`Right ${noun}`}
            id={item.candidate.ids[1]}
            text={item.candidate.right}
            onOpen={open ? () => open(item.candidate.ids[1]) : undefined}
          />
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 px-7 py-3">
        {error && <ErrorPill message={error} />}
        <GhostBtn onClick={onRefresh}>
          <RefreshCw size={ICON.SM} strokeWidth={2} /> Refresh
        </GhostBtn>
      </div>
    </div>
  );
}

function DuplicateSide({
  label,
  id,
  text,
  onOpen,
}: {
  label: string;
  id: number;
  text: string;
  onOpen?: () => void;
}) {
  return (
    <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs uppercase tracking-[0.06em] text-faint">
          {label} <span className="tabular-nums">#{id}</span>
        </div>
        {onOpen && (
          <button
            type="button"
            onClick={onOpen}
            className="text-xs font-medium text-muted transition-colors hover:text-ink"
          >
            Open
          </button>
        )}
      </div>
      <p className="m-0 whitespace-pre-wrap text-base leading-relaxed text-ink-soft">{text}</p>
    </section>
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
  const duplicateCandidateCount = maintenanceReview
    ? maintenanceReview.duplicateFactCandidateCount + maintenanceReview.duplicateObservationCandidateCount
    : 0;

  return (
    <div className="flex h-full flex-col">
      <div className="px-7 pt-6 pb-3">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="m-0 text-lg font-semibold tracking-[-0.01em] text-ink">Review cleanup candidate</h3>
          <Pill tone="warn">{candidate.reason}</Pill>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-faint">
          <span>older than {dryRun.criteria.older_than_days}d</span>
          <span aria-hidden>·</span>
          <span>max {dryRun.criteria.max_sources} sources</span>
          <span aria-hidden>·</span>
          <span>{dryRun.summary.total} candidates in dry-run</span>
          {maintenanceReview && (
            <>
              <span aria-hidden>·</span>
              <span>maintenance saw {maintenanceReview.cleanupCandidateCount}</span>
              {duplicateCandidateCount > 0 && (
                <>
                  <span aria-hidden>·</span>
                  <span>{duplicateCandidateCount} duplicate candidates</span>
                </>
              )}
            </>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin scroll-fade-top px-7">
        <p className="m-0 whitespace-pre-wrap text-md leading-relaxed text-ink">{candidate.summary}</p>
        <dl className="mt-6 grid grid-cols-[130px_minmax(0,1fr)] gap-y-2 text-sm">
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
          <RefreshCw size={ICON.SM} strokeWidth={2} /> Refresh
        </GhostBtn>
        <GhostBtn onClick={onOpenPattern} disabled={busy}>
          <ExternalLink size={ICON.SM} strokeWidth={2} /> Open pattern
        </GhostBtn>
        <GhostBtn onClick={onArchiveAll} disabled={busy || dryRun.summary.total === 0}>
          <Archive size={ICON.SM} strokeWidth={2} /> Archive all
        </GhostBtn>
        <PrimaryBtn onClick={onArchiveSelected} disabled={busy}>
          {busy ? "Archiving…" : "Archive selected"}
        </PrimaryBtn>
      </div>
    </div>
  );
}
