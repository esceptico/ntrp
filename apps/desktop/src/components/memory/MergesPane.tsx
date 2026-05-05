import { useEffect, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { useStore } from "../../store";
import {
  type SupersessionCandidate,
  applySupersessionApi,
  listSupersessionCandidatesApi,
} from "../../api";
import { useMountedRef, useMutationState } from "../../lib/hooks";
import { formatRelativePast } from "../../lib/format";
import { DangerBtn, Empty, ErrorPill, PrimaryBtn } from "./shared";

export function MergesPane() {
  const config = useStore((s) => s.config);
  const [items, setItems] = useState<SupersessionCandidate[] | null>(null);

  async function refresh() {
    const r = await listSupersessionCandidatesApi(config);
    setItems(r.candidates);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="grid grid-rows-[auto_minmax(0,1fr)] h-full">
      <div className="px-7 pt-5 pb-3">
        <h3 className="m-0 mb-1 text-[13px] font-semibold tracking-[-0.005em] text-ink">
          Merge candidates
        </h3>
        <p className="m-0 text-[12px] text-faint">
          Pairs of facts where the older row appears to be replaced by a newer one.
          Apply to mark the older as superseded.
        </p>
      </div>
      <div className="overflow-y-auto scroll-thin px-5 pb-5">
        {items === null ? (
          <Empty>Loading…</Empty>
        ) : items.length === 0 ? (
          <Empty>Nothing to merge.</Empty>
        ) : (
          <ul className="flex flex-col gap-2.5 m-0 p-0 list-none">
            {items.map((c, i) => (
              <CandidateCard
                key={`${c.older_fact.id}-${c.newer_fact.id}-${i}`}
                candidate={c}
                onApplied={refresh}
                onDismissed={() => {
                  setItems((prev) => prev?.filter((p) => p !== c) ?? null);
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function CandidateCard({
  candidate,
  onApplied,
  onDismissed,
}: {
  candidate: SupersessionCandidate;
  onApplied: () => Promise<void>;
  onDismissed: () => void;
}) {
  const config = useStore((s) => s.config);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);
  const [applied, setApplied] = useState(false);

  async function apply() {
    await run(async () => {
      await applySupersessionApi(config, candidate.older_fact.id, candidate.newer_fact.id);
      if (mounted.current) setApplied(true);
      await onApplied();
    });
  }

  return (
    <li className="rounded-[10px] border border-line-soft bg-bg-main/40 p-4">
      <div className="flex items-center gap-2 text-[11px] text-faint mb-2.5">
        <span className="uppercase tracking-[0.06em]">{candidate.kind}</span>
        <span aria-hidden>·</span>
        <span>{candidate.entity}</span>
        <span aria-hidden>·</span>
        <span className="italic">{candidate.reason}</span>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-3 items-center">
        <FactBox fact={candidate.older_fact} variant="older" />
        <ArrowRight size={14} strokeWidth={1.8} className="text-faint shrink-0" />
        <FactBox fact={candidate.newer_fact} variant="newer" />
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        {error && <ErrorPill message={error} />}
        {applied ? (
          <span className="inline-flex items-center gap-1.5 text-[12px] text-accent-strong">
            <Check size={12} strokeWidth={2} /> Applied
          </span>
        ) : (
          <>
            <DangerBtn onClick={onDismissed} disabled={busy}>
              Dismiss
            </DangerBtn>
            <PrimaryBtn onClick={() => void apply()} disabled={busy}>
              {busy ? "Applying…" : "Apply merge"}
            </PrimaryBtn>
          </>
        )}
      </div>
    </li>
  );
}

function FactBox({
  fact,
  variant,
}: {
  fact: { text: string; created_at: string; salience: number; id: number };
  variant: "older" | "newer";
}) {
  return (
    <div className="min-w-0 rounded-[8px] bg-surface px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-[0.08em] text-faint mb-1">
        {variant} · #{fact.id}
      </div>
      <div className="text-[12.5px] leading-snug text-ink-soft line-clamp-3">{fact.text}</div>
      <div className="mt-1 text-[11px] text-faint tabular-nums">
        created {formatRelativePast(fact.created_at)} · salience {fact.salience.toFixed(2)}
      </div>
    </div>
  );
}
