import { useEffect, useState } from "react";
import type { KnowledgeObject, KnowledgeSourceTraceResult } from "../../api";
import {
  getKnowledgeObjectSourcesApi,
  listKnowledgeObjectsApi,
  publishKnowledgeArtifactApi,
  updateKnowledgeObjectApi,
} from "../../api";
import { useStore } from "../../store";
import { formatRelativePast } from "../../lib/format";
import { KNOWLEDGE_REVIEW_TYPES, reviewKind, shouldReviewKnowledgeObject } from "../../lib/knowledgeViews";
import { ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";

export function KnowledgeReviewPane() {
  const config = useStore((s) => s.config);
  const [items, setItems] = useState<KnowledgeObject[] | null>(null);
  const [sources, setSources] = useState<Record<number, KnowledgeSourceTraceResult>>({});
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    setError(null);
    try {
      const results = await Promise.all(
        KNOWLEDGE_REVIEW_TYPES.map((type) => listKnowledgeObjectsApi(config, { object_type: type, status: "draft" })),
      );
      setItems(results.flatMap((result) => result.objects).filter(shouldReviewKnowledgeObject));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function updateStatus(item: KnowledgeObject, status: "approved" | "rejected") {
    setBusyId(item.id);
    setError(null);
    try {
      await updateKnowledgeObjectApi(config, item.id, { status });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function publishArtifact(item: KnowledgeObject) {
    setBusyId(item.id);
    setError(null);
    try {
      await publishKnowledgeArtifactApi(config, {
        artifact_id: item.id,
        sink: "local-review",
        sink_ref: `knowledge:${item.id}`,
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function toggleSources(item: KnowledgeObject) {
    if (sources[item.id]) {
      setSources((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      return;
    }
    setBusyId(item.id);
    setError(null);
    try {
      const result = await getKnowledgeObjectSourcesApi(config, item.id);
      setSources((current) => ({ ...current, [item.id]: result }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
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
            <h3 className="m-0 text-base font-semibold text-ink">Review</h3>
            <p className="m-0 mt-1 text-sm text-faint">Draft procedures, actions, and artifacts that can change behavior</p>
          </div>
          <GhostBtn onClick={() => void load()}>Refresh</GhostBtn>
        </div>
        {error && <div className="mt-2"><ErrorPill message={error} /></div>}
      </div>

      <div className="min-h-0 overflow-y-auto scroll-thin px-7 py-5">
        <ScrollBlurTop />
        {items === null ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Loading</div>
        ) : items.length === 0 ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Nothing needs review</div>
        ) : (
          <ul className="m-0 grid list-none gap-3 p-0">
            {items.map((item) => (
              <li key={item.id} className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <Pill>{reviewKind(item)}</Pill>
                  <Pill>{item.proactiveness_level}</Pill>
                  {item.scope && <Pill>{item.scope}</Pill>}
                  <span className="text-xs text-faint">updated {formatRelativePast(item.updated_at)}</span>
                </div>
                <h4 className="m-0 text-sm font-semibold text-ink-soft">{item.title}</h4>
                <p className="m-0 mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-soft">{item.text}</p>
                {sources[item.id] && (
                  <div className="mt-3 rounded-md border border-line-soft bg-bg-main px-2 py-2">
                    <p className="m-0 mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-faint">Sources</p>
                    <ul className="m-0 grid list-none gap-2 p-0">
                      {sources[item.id].sources.map((source) => (
                        <li key={source.source_id} className="text-xs leading-snug text-ink-soft">
                          <span className="font-mono text-faint">{source.source_id}</span>
                          {source.object && <span> · {source.object.object_type}: {source.object.title}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.object_type === "artifact" ? (
                    <GhostBtn disabled={busyId === item.id} onClick={() => void publishArtifact(item)}>Publish</GhostBtn>
                  ) : (
                    <GhostBtn disabled={busyId === item.id} onClick={() => void updateStatus(item, "approved")}>Approve</GhostBtn>
                  )}
                  <GhostBtn disabled={busyId === item.id} onClick={() => void updateStatus(item, "rejected")}>Dismiss</GhostBtn>
                  <GhostBtn disabled={busyId === item.id} onClick={() => void toggleSources(item)}>Sources</GhostBtn>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
