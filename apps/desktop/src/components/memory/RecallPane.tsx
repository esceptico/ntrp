import { useState } from "react";
import type { ReactNode } from "react";
import { Search } from "lucide-react";
import { useStore } from "../../store";
import { type Fact, type MemoryRecallInspectResult, type Observation, inspectMemoryRecallApi } from "../../api";
import { formatRelativePast } from "../../lib/format";
import { factSourceSummary } from "../../lib/memoryProvenance";
import { memoryRecallReasonLabel } from "../../lib/memoryRecallReasons";
import {
  factStatusLabel,
  factStatusTone,
  observationEvidenceLabel,
  observationEvidenceTone,
} from "../../lib/memoryTrust";
import { ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";
import { ICON } from "../../lib/icons";

export function RecallPane({
  onOpenFact,
  onOpenPattern,
}: {
  onOpenFact?: (fact: Fact) => void;
  onOpenPattern?: (pattern: Observation) => void;
}) {
  const config = useStore((s) => s.config);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<MemoryRecallInspectResult | null>(null);
  const [showPromptContext, setShowPromptContext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await inspectMemoryRecallApi(config, trimmed));
      setShowPromptContext(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
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
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void run();
              }}
              spellCheck={false}
              placeholder="Ask what memory would retrieve for a query"
              className="h-9 w-full rounded-[8px] border border-line-soft bg-bg-main pl-9 pr-3 text-base text-ink outline-none transition-colors focus:border-line-strong"
            />
          </div>
          <GhostBtn onClick={() => void run()} disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Run search"}
          </GhostBtn>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-faint">
          {error ? <ErrorPill message={error} /> : <span>Preview the exact memory context before it reaches a prompt.</span>}
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto scroll-thin px-7 py-5">
        <ScrollBlurTop />
        {!result ? (
          <div className="grid h-full place-items-center text-base italic text-faint">Run a query to inspect recall</div>
        ) : (
          <div className="grid gap-5">
            <section className="min-w-0">
              <div className="mb-3 flex min-h-7 flex-wrap items-center justify-between gap-2">
                <h3 className="m-0 text-base font-semibold text-ink">Recall results</h3>
                <div className="flex items-center gap-1.5">
                  <Pill>{result.observations.length} patterns</Pill>
                  <Pill>{result.facts.length} facts</Pill>
                  <GhostBtn onClick={() => setShowPromptContext((value) => !value)}>
                    {showPromptContext ? "Hide prompt context" : "Show prompt context"}
                  </GhostBtn>
                </div>
              </div>
              {showPromptContext && (
                <pre className="m-0 max-h-[220px] overflow-y-auto whitespace-pre-wrap rounded-[8px] border border-line-soft bg-code-bg px-4 py-3 text-sm leading-relaxed text-ink-soft scroll-thin">
                  {result.formatted_recall || "No memory matches"}
                </pre>
              )}
            </section>

            <div className="min-w-0">
              <SourceList
                title="Patterns"
                items={result.observations}
                render={(obs) => (
                  <PatternSource
                    key={obs.id}
                    observation={obs}
                    sources={result.bundled_sources[String(obs.id)] ?? []}
                    reasons={result.observation_reasons[String(obs.id)] ?? []}
                    onOpen={() => onOpenPattern?.(obs)}
                    onOpenFact={onOpenFact}
                  />
                )}
              />
              <div className="mt-5">
                <SourceList
                  title="Facts"
                  items={result.facts}
                  render={(fact) => (
                    <FactSource
                      key={fact.id}
                      fact={fact}
                      reasons={result.fact_reasons[String(fact.id)] ?? []}
                      onOpen={() => onOpenFact?.(fact)}
                    />
                  )}
                />
              </div>
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

function FactSource({ fact, reasons, onOpen }: { fact: Fact; reasons: string[]; onOpen?: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="block w-full rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-left transition-colors hover:border-line-strong hover:bg-surface-soft/40"
      >
        <span className="mb-1 flex flex-wrap items-center gap-1.5">
          <Pill>{fact.kind}</Pill>
          <Pill tone={factStatusTone(fact.status)}>{factStatusLabel(fact.status)}</Pill>
          <span className="text-xs text-faint">
            {factSourceSummary(fact)} · {fact.access_count}× · {formatRelativePast(fact.last_accessed_at)}
          </span>
        </span>
        <RecallReasons reasons={reasons} />
        <span className="block text-sm leading-snug text-ink-soft line-clamp-4">{fact.text}</span>
      </button>
    </li>
  );
}

function PatternSource({
  observation,
  sources,
  reasons,
  onOpen,
  onOpenFact,
}: {
  observation: Observation;
  sources: Fact[];
  reasons: string[];
  onOpen?: () => void;
  onOpenFact?: (fact: Fact) => void;
}) {
  return (
    <li className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2">
      <button
        type="button"
        onClick={onOpen}
        className="-mx-1 -mt-1 block w-[calc(100%+0.5rem)] rounded-[6px] px-1 py-1 text-left transition-colors hover:bg-surface-soft/40"
      >
        <span className="mb-1 flex flex-wrap items-center gap-1.5">
          <Pill tone={observationEvidenceTone(observation.evidence_level)}>
            {observationEvidenceLabel(observation.evidence_level)}
          </Pill>
          <span className="text-xs text-faint">
            {observation.evidence_count} sources · {observation.access_count}× · {formatRelativePast(observation.last_accessed_at)}
          </span>
        </span>
        <RecallReasons reasons={reasons} />
        <span className="block text-sm leading-snug text-ink-soft line-clamp-4">{observation.summary}</span>
      </button>
      {sources.length > 0 && (
        <ul className="mt-2 flex list-none flex-col gap-1 border-t border-line-soft pt-2">
          {sources.slice(0, 2).map((fact) => (
            <li key={fact.id} className="min-w-0">
              <button
                type="button"
                onClick={() => onOpenFact?.(fact)}
                className="block w-full text-left text-xs leading-snug text-faint hover:text-ink-soft"
              >
                <span className="uppercase tracking-[0.06em]">{fact.kind}</span>
                <span aria-hidden> · </span>
                <span>{factSourceSummary(fact)}</span>
                <span aria-hidden> · </span>
                <span className="line-clamp-2">{fact.text}</span>
              </button>
            </li>
          ))}
          {sources.length > 2 && (
            <li>
              <button
                type="button"
                onClick={onOpen}
                className="text-left text-xs text-faint hover:text-ink-soft"
              >
                {sources.length - 2} more sources in pattern detail
              </button>
            </li>
          )}
        </ul>
      )}
    </li>
  );
}

function RecallReasons({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <span className="mb-1 block text-xs leading-snug text-faint">
      Why: {reasons.map(memoryRecallReasonLabel).join(", ")}
    </span>
  );
}
