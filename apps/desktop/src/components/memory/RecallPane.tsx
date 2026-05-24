import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { Search, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import { type ActivationBundle, type ActivationCandidate, inspectKnowledgeActivationApi } from "../../api";
import { ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";
import { ICON } from "../../lib/icons";

export function RecallPane() {
  const config = useStore((s) => s.config);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<ActivationBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runGenerationRef = useRef(0);

  function clearQuery() {
    runGenerationRef.current += 1;
    setQuery("");
    setResult(null);
    setError(null);
    setLoading(false);
  }

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    if (!nextQuery.trim()) {
      runGenerationRef.current += 1;
      setResult(null);
      setError(null);
      setLoading(false);
    }
  }

  async function run() {
    const trimmed = query.trim();
    if (!trimmed) return;
    const generation = ++runGenerationRef.current;
    setLoading(true);
    setError(null);
    try {
      const nextResult = await inspectKnowledgeActivationApi(config, trimmed);
      if (generation === runGenerationRef.current) setResult(nextResult);
    } catch (e) {
      if (generation === runGenerationRef.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === runGenerationRef.current) setLoading(false);
    }
  }

  return (
    <div className="grid h-full grid-rows-[auto_minmax(0,1fr)]">
      <div className="border-b border-line-soft px-7 py-4">
        <div className="flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search size={ICON.MD} strokeWidth={2} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => updateQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void run();
              }}
              spellCheck={false}
              placeholder="Ask what knowledge would activate for a query"
              aria-label="Activation inspector query"
              title="Press Enter to inspect activation"
              className="h-9 w-full rounded-[8px] border border-line-soft bg-bg-main pl-9 pr-8 text-base text-ink outline-none transition-colors focus:border-line-strong"
            />
            {query && (
              <button
                type="button"
                onClick={clearQuery}
                aria-label="Clear activation query"
                className="absolute right-2.5 top-1/2 grid size-5 -translate-y-1/2 place-items-center rounded text-faint hover:bg-surface-soft hover:text-ink"
              >
                <X size={ICON.XS} strokeWidth={2} />
              </button>
            )}
          </div>
          <GhostBtn onClick={() => void run()} disabled={loading || !query.trim()}>
            {loading ? "Inspecting..." : "Inspect activation"}
          </GhostBtn>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-faint">
          {error ? <ErrorPill message={error} /> : <span>Preview the activated knowledge bundle before it reaches the agent.</span>}
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto scroll-thin px-7 py-5">
        <ScrollBlurTop />
        {!result ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Run a query to inspect activation</div>
        ) : (
          <div className="grid gap-5">
            <section className="min-w-0">
              <div className="mb-3 flex min-h-7 flex-wrap items-center justify-between gap-2">
                <h3 className="m-0 text-base font-semibold text-ink">Activation bundle</h3>
                <div className="flex items-center gap-1.5">
                  <Pill>{result.candidates.length} active</Pill>
                  <Pill>{result.omitted.length} omitted</Pill>
                  <Pill>{result.used_chars}/{result.budget_chars} chars</Pill>
                </div>
              </div>
            </section>

            <div className="min-w-0">
              <SourceList
                title="Active candidates"
                items={result.candidates}
                render={(candidate) => <ActivationItem key={`${candidate.object_type}:${candidate.object_id}`} candidate={candidate} />}
              />
              {result.omitted.length > 0 && (
                <div className="mt-5">
                  <SourceList
                    title="Omitted"
                    items={result.omitted}
                    render={(candidate) => <ActivationItem key={`${candidate.object_type}:${candidate.object_id}`} candidate={candidate} muted />}
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SourceList<T>({
  title,
  items,
  render,
}: {
  title: string;
  items: T[];
  render: (item: T) => ReactNode;
}) {
  return (
    <section>
      <h3 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">{title}</h3>
      {items.length === 0 ? (
        <div className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-sm italic text-faint">No matches</div>
      ) : (
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0">{items.map(render)}</ul>
      )}
    </section>
  );
}

function ActivationItem({ candidate, muted = false }: { candidate: ActivationCandidate; muted?: boolean }) {
  return (
    <li>
      <div className="block w-full rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-left">
        <span className="mb-1 flex flex-wrap items-center gap-1.5">
          <Pill>{candidate.object_type}</Pill>
          <Pill>{candidate.activation}</Pill>
          <Pill>{candidate.proactiveness_level}</Pill>
          <span className="text-xs text-faint">score {candidate.score.toFixed(2)}</span>
        </span>
        <span className="mb-1 block text-sm font-medium text-ink-soft">{candidate.title}</span>
        <ActivationReasons reasons={candidate.reasons} />
        <span className={clsx("block text-sm leading-snug line-clamp-4", muted ? "text-faint" : "text-ink-soft")}>{candidate.text}</span>
        {candidate.signals.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {candidate.signals.slice(0, 4).map((signal) => (
              <Pill key={`${signal.name}:${signal.reason}`}>{signal.name}: {String(signal.value)}</Pill>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

function ActivationReasons({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <span className="mb-1 block text-xs leading-snug text-faint">
      Why: {reasons.join(", ")}
    </span>
  );
}
