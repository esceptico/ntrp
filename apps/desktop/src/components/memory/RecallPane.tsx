import { useState } from "react";
import type { ReactNode } from "react";
import { Search } from "lucide-react";
import { useStore } from "../../store";
import { type Fact, type MemoryRecallInspectResult, type Observation, inspectMemoryRecallApi } from "../../api";
import { formatRelativePast } from "../../lib/format";
import { ErrorPill, GhostBtn, Pill } from "./shared";

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const trimmed = query.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await inspectMemoryRecallApi(config, trimmed));
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
            <Search size={13} strokeWidth={1.8} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void run();
              }}
              spellCheck={false}
              placeholder="Ask what memory would retrieve for a query"
              className="h-9 w-full rounded-[8px] border border-line-soft bg-bg-main pl-9 pr-3 text-[13px] text-ink outline-none transition-colors focus:border-line-strong"
            />
          </div>
          <GhostBtn onClick={() => void run()} disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Run search"}
          </GhostBtn>
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11.5px] text-faint">
          {error ? <ErrorPill message={error} /> : <span>Preview the exact memory context before it reaches a prompt.</span>}
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto scroll-thin px-7 py-5">
        {!result ? (
          <div className="grid h-full place-items-center text-[13px] italic text-faint">Run a query to inspect recall</div>
        ) : (
          <div className="grid grid-cols-[minmax(0,1fr)_340px] gap-6">
            <section>
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="m-0 text-[13px] font-semibold text-ink">Formatted context</h3>
                <div className="flex items-center gap-1.5">
                  <Pill>{result.observations.length} patterns</Pill>
                  <Pill>{result.facts.length} facts</Pill>
                </div>
              </div>
              <pre className="m-0 min-h-[240px] whitespace-pre-wrap rounded-[8px] border border-line-soft bg-code-bg px-4 py-3 text-[12.5px] leading-relaxed text-ink-soft">
                {result.formatted_recall || "No memory matches"}
              </pre>
            </section>

            <aside className="min-w-0">
              <SourceList
                title="Patterns"
                items={result.observations}
                render={(obs) => <PatternSource key={obs.id} observation={obs} onOpen={() => onOpenPattern?.(obs)} />}
              />
              <div className="mt-5">
                <SourceList
                  title="Facts"
                  items={result.facts}
                  render={(fact) => <FactSource key={fact.id} fact={fact} onOpen={() => onOpenFact?.(fact)} />}
                />
              </div>
            </aside>
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
      <h3 className="m-0 mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">{title}</h3>
      {items.length === 0 ? (
        <div className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-[12px] italic text-faint">No matches</div>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">{items.map(render)}</ul>
      )}
    </section>
  );
}

function FactSource({ fact, onOpen }: { fact: Fact; onOpen?: () => void }) {
  return (
    <li className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2">
      <div className="mb-1 flex items-center gap-1.5">
        <Pill>{fact.kind}</Pill>
        <span className="text-[11px] text-faint">{fact.access_count}× · {formatRelativePast(fact.last_accessed_at)}</span>
      </div>
      <button type="button" onClick={onOpen} className="text-left text-[12.5px] leading-snug text-ink-soft hover:text-ink">
        {fact.text}
      </button>
    </li>
  );
}

function PatternSource({ observation, onOpen }: { observation: Observation; onOpen?: () => void }) {
  return (
    <li className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2">
      <div className="mb-1 text-[11px] text-faint">
        {observation.evidence_count} sources · {observation.access_count}× · {formatRelativePast(observation.last_accessed_at)}
      </div>
      <button type="button" onClick={onOpen} className="text-left text-[12.5px] leading-snug text-ink-soft hover:text-ink">
        {observation.summary}
      </button>
    </li>
  );
}
