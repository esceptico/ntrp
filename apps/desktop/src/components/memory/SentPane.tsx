import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type Fact,
  type MemoryAccessEvent,
  type Observation,
  listMemoryAccessEventsApi,
} from "../../api";
import { formatAbs, formatRelativePast } from "../../lib/format";
import { DetailPlaceholder, JsonBlock, ListColumn, PaneShell, Pill, SearchInput } from "./shared";

export function SentPane({
  onOpenFact,
  onOpenPattern,
}: {
  onOpenFact?: (fact: Fact) => void;
  onOpenPattern?: (pattern: Observation) => void;
}) {
  const config = useStore((s) => s.config);
  const [events, setEvents] = useState<MemoryAccessEvent[] | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  async function refresh() {
    const access = await listMemoryAccessEventsApi(config);
    setEvents(access.events);
    setFacts(access.facts ?? []);
    setObservations(access.observations ?? []);
    setSelectedId((current) => current ?? access.events[0]?.id ?? null);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const filtered = useMemo(() => {
    if (!events) return null;
    const q = query.trim().toLowerCase();
    if (!q) return events;
    return events.filter((event) =>
      event.source.toLowerCase().includes(q) ||
      (event.query ?? "").toLowerCase().includes(q) ||
      event.policy_version.toLowerCase().includes(q)
    );
  }, [events, query]);

  const selected = events?.find((event) => event.id === selectedId) ?? null;
  const factById = useMemo(() => new Map(facts.map((fact) => [fact.id, fact])), [facts]);
  const observationById = useMemo(() => new Map(observations.map((obs) => [obs.id, obs])), [observations]);

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={<SearchInput value={query} onChange={setQuery} placeholder="Filter sent memory" />}
          loading={events === null}
          empty="No sent-memory records yet."
          totalLabel={events ? `${filtered?.length ?? 0} of ${events.length}` : null}
          items={filtered ?? []}
          renderItem={(event) => (
            <SentRow
              key={event.id}
              event={event}
              selected={event.id === selectedId}
              onSelect={() => setSelectedId(event.id)}
            />
          )}
        />
      }
      detail={
        selected ? (
          <SentDetail
            event={selected}
            factById={factById}
            observationById={observationById}
            onOpenFact={onOpenFact}
            onOpenPattern={onOpenPattern}
          />
        ) : (
          <DetailPlaceholder>Select a sent-memory record</DetailPlaceholder>
        )
      }
    />
  );
}

function SentRow({
  event,
  selected,
  onSelect,
}: {
  event: MemoryAccessEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  const injectedCount = event.injected_fact_ids.length + event.injected_observation_ids.length;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "w-full rounded-md px-4 py-2.5 text-left transition-colors",
        selected ? "bg-surface-soft text-ink" : "text-ink-soft hover:bg-surface-soft/50",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[12.5px] font-medium leading-snug">{sourceLabel(event.source)}</div>
          <div className="mt-1 line-clamp-2 text-[11.5px] leading-snug text-faint">{event.query || "no query"}</div>
        </div>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-faint">
        <span>{injectedCount} injected</span>
        <span aria-hidden>·</span>
        <span>{event.formatted_chars.toLocaleString()} chars</span>
        <span aria-hidden>·</span>
        <span>{formatRelativePast(event.created_at)}</span>
      </div>
    </button>
  );
}

function SentDetail({
  event,
  factById,
  observationById,
  onOpenFact,
  onOpenPattern,
}: {
  event: MemoryAccessEvent;
  factById: Map<number, Fact>;
  observationById: Map<number, Observation>;
  onOpenFact?: (fact: Fact) => void;
  onOpenPattern?: (pattern: Observation) => void;
}) {
  return (
    <div className="px-7 py-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="m-0 text-[15px] font-semibold tracking-[-0.01em] text-ink">{sourceLabel(event.source)}</h3>
          </div>
          <p className="m-0 mt-1 text-[12px] text-faint">{formatAbs(event.created_at)} · {event.policy_version}</p>
        </div>
        <Pill>{event.formatted_chars.toLocaleString()} chars</Pill>
      </div>

      {event.query && (
        <section className="mb-5">
          <h4 className="m-0 mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">Query</h4>
          <p className="m-0 rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-[12.5px] leading-relaxed text-ink-soft">
            {event.query}
          </p>
        </section>
      )}

      <MemoryIdSection
        title="Injected patterns"
        ids={event.injected_observation_ids}
        render={(id) => observationById.get(id)?.summary ?? `Pattern #${id}`}
        onOpen={(id) => {
          const pattern = observationById.get(id);
          if (pattern) onOpenPattern?.(pattern);
        }}
      />
      <MemoryIdSection
        title="Injected facts"
        ids={event.injected_fact_ids}
        render={(id) => factById.get(id)?.text ?? `Fact #${id}`}
        onOpen={(id) => {
          const fact = factById.get(id);
          if (fact) onOpenFact?.(fact);
        }}
      />
      <MemoryIdSection
        title="Omitted facts"
        ids={event.omitted_fact_ids}
        render={(id) => factById.get(id)?.text ?? `Fact #${id}`}
        onOpen={(id) => {
          const fact = factById.get(id);
          if (fact) onOpenFact?.(fact);
        }}
      />

      <section className="mt-5">
        <h4 className="m-0 mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">Details</h4>
        <JsonBlock value={event.details} />
      </section>
    </div>
  );
}

function MemoryIdSection({
  title,
  ids,
  render,
  onOpen,
}: {
  title: string;
  ids: number[];
  render: (id: number) => string;
  onOpen?: (id: number) => void;
}) {
  if (ids.length === 0) return null;
  return (
    <section className="mt-5">
      <h4 className="m-0 mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">{title} ({ids.length})</h4>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {ids.map((id) => (
          <li key={id} className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-2 text-[12.5px] leading-snug text-ink-soft">
            {onOpen ? (
              <button type="button" onClick={() => onOpen(id)} className="text-left hover:text-ink">
                {render(id)}
              </button>
            ) : (
              render(id)
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function sourceLabel(source: string): string {
  return source.replaceAll("_", " ");
}
