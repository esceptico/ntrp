import { useEffect, useMemo, useRef, useState } from "react";
import type { KnowledgeObject, KnowledgeObjectType, KnowledgeSummary } from "../../api";
import { getKnowledgeSummaryApi, listKnowledgeObjectsApi } from "../../api";
import { useStore } from "../../store";
import { formatRelativePast } from "../../lib/format";
import {
  KNOWLEDGE_LIBRARY_TYPES,
  KNOWLEDGE_REVIEW_TYPES,
  knowledgeSurfaceCount,
  shouldReviewKnowledgeObject,
} from "../../lib/knowledgeViews";
import { ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";

export function KnowledgeHomePane({
  onOpenLibrary,
  onOpenReview,
  onOpenActivation,
}: {
  onOpenLibrary: (type?: KnowledgeObjectType | "all") => void;
  onOpenReview: () => void;
  onOpenActivation: () => void;
}) {
  const config = useStore((s) => s.config);
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [recent, setRecent] = useState<KnowledgeObject[] | null>(null);
  const [reviewCount, setReviewCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const loadGenerationRef = useRef(0);

  const libraryCount = useMemo(() => {
    if (!summary) return 0;
    return KNOWLEDGE_LIBRARY_TYPES.reduce((sum, view) => sum + knowledgeSurfaceCount(summary.surfaces, view.type), 0);
  }, [summary]);

  async function load() {
    const generation = ++loadGenerationRef.current;
    setError(null);
    try {
      const [nextSummary, recentObjects, reviewResults] = await Promise.all([
        getKnowledgeSummaryApi(config),
        listKnowledgeObjectsApi(config, { limit: 8 }),
        Promise.all(
          KNOWLEDGE_REVIEW_TYPES.map((type) =>
            listKnowledgeObjectsApi(config, { object_type: type, status: "draft", limit: 250 }),
          ),
        ),
      ]);
      if (generation !== loadGenerationRef.current) return;
      setSummary(nextSummary);
      setRecent(recentObjects.objects);
      setReviewCount(reviewResults.flatMap((result) => result.objects).filter(shouldReviewKnowledgeObject).length);
    } catch (e) {
      if (generation === loadGenerationRef.current) setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

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
                value={libraryCount}
                detail="active facts, lessons, artifacts, episodes"
                onClick={() => onOpenLibrary("all")}
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
                    onClick={() => onOpenLibrary(view.type)}
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
