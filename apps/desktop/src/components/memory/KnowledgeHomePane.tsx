import { useEffect, useState } from "react";
import type { KnowledgeObject, KnowledgeSummary } from "../../api";
import { getKnowledgeSummaryApi, listKnowledgeObjectsApi } from "../../api";
import { useStore } from "../../store";
import { formatRelativePast } from "../../lib/format";
import { KNOWLEDGE_LIBRARY_TYPES, knowledgeSurfaceCount } from "../../lib/knowledgeViews";
import { ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";

export function KnowledgeHomePane({
  onOpenLibrary,
  onOpenReview,
  onOpenActivation,
}: {
  onOpenLibrary: () => void;
  onOpenReview: () => void;
  onOpenActivation: () => void;
}) {
  const config = useStore((s) => s.config);
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [recent, setRecent] = useState<KnowledgeObject[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [nextSummary, recentObjects] = await Promise.all([
        getKnowledgeSummaryApi(config),
        listKnowledgeObjectsApi(config, { limit: 8 }),
      ]);
      setSummary(nextSummary);
      setRecent(recentObjects.objects);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const reviewCount = summary
    ? knowledgeSurfaceCount(summary.surfaces, "procedure_candidate")
      + knowledgeSurfaceCount(summary.surfaces, "action_candidate")
      + knowledgeSurfaceCount(summary.surfaces, "artifact")
    : 0;

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      <div className="border-b border-line-soft px-7 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="m-0 text-base font-semibold text-ink">Overview</h3>
            <p className="m-0 mt-1 text-sm text-faint">Captured context, learned behavior, review queue, and activation state</p>
          </div>
          <GhostBtn onClick={() => void load()}>Refresh</GhostBtn>
        </div>
        {error && <div className="mt-2"><ErrorPill message={error} /></div>}
      </div>

      <div className="min-h-0 overflow-y-auto scroll-thin px-7 py-5">
        <ScrollBlurTop />
        {!summary ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Loading</div>
        ) : (
          <div className="grid gap-6">
            <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <OverviewButton
                title="Library"
                value={summary.surfaces.reduce((sum, surface) => sum + surface.count, 0)}
                detail="typed objects"
                onClick={onOpenLibrary}
              />
              <OverviewButton title="Review" value={reviewCount} detail="draft decisions" onClick={onOpenReview} />
              <OverviewButton
                title="Activation"
                value={knowledgeSurfaceCount(summary.surfaces, "outcome_feedback")}
                detail="context sends"
                onClick={onOpenActivation}
              />
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <h4 className="m-0 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Types</h4>
                <Pill>{summary.policy_version}</Pill>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {KNOWLEDGE_LIBRARY_TYPES.map((view) => (
                  <button
                    key={view.type}
                    type="button"
                    onClick={onOpenLibrary}
                    className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-left hover:bg-surface-soft transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-ink-soft">{view.label}</span>
                      <span className="font-mono text-sm text-muted">{knowledgeSurfaceCount(summary.surfaces, view.type)}</span>
                    </div>
                    <p className="m-0 mt-1 text-xs leading-snug text-faint">{view.description}</p>
                  </button>
                ))}
              </div>
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <h4 className="m-0 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Next</h4>
                <Pill>{summary.next_actions.length}</Pill>
              </div>
              {summary.next_actions.length === 0 ? (
                <div className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-sm italic text-faint">
                  No pending system suggestions
                </div>
              ) : (
                <ul className="m-0 grid list-none gap-2 p-0">
                  {summary.next_actions.map((action) => (
                    <li key={`${action.title}:${action.detail}`} className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Pill>{action.activation}</Pill>
                        <Pill>{action.proactiveness_level}</Pill>
                      </div>
                      <h5 className="m-0 mt-1 text-sm font-semibold text-ink-soft">{action.title}</h5>
                      <p className="m-0 mt-1 text-sm leading-snug text-faint">{action.detail}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <h4 className="m-0 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Recent</h4>
                <Pill>{recent?.length ?? 0}</Pill>
              </div>
              {recent === null ? (
                <div className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-sm italic text-faint">Loading</div>
              ) : recent.length === 0 ? (
                <div className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-sm italic text-faint">No knowledge objects yet</div>
              ) : (
                <ul className="m-0 grid list-none gap-2 p-0">
                  {recent.map((item) => (
                    <li key={item.id} className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Pill>{item.object_type}</Pill>
                        <Pill>{item.status}</Pill>
                        <span className="text-xs text-faint">{formatRelativePast(item.updated_at)}</span>
                      </div>
                      <h5 className="m-0 mt-1 text-sm font-semibold text-ink-soft">{item.title}</h5>
                      <p className="m-0 mt-1 line-clamp-2 text-sm leading-snug text-faint">{item.text}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function OverviewButton({
  title,
  value,
  detail,
  onClick,
}: {
  title: string;
  value: number;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-[8px] border border-line-soft bg-bg-main/50 px-4 py-3 text-left hover:bg-surface-soft transition-colors"
    >
      <div className="text-sm font-semibold text-ink-soft">{title}</div>
      <div className="mt-2 font-mono text-2xl leading-none text-ink">{value}</div>
      <div className="mt-1 text-xs text-faint">{detail}</div>
    </button>
  );
}
