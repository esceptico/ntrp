import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { useStore } from "../../store";
import { type MemoryEvent, listMemoryEventsApi } from "../../api";
import { formatAbs, formatRelativePast } from "../../lib/format";
import { DetailPlaceholder, JsonBlock, ListColumn, MetaGrid, PaneShell, Pill, SearchInput } from "./shared";

export function AuditPane() {
  const config = useStore((s) => s.config);
  const [events, setEvents] = useState<MemoryEvent[] | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const result = await listMemoryEventsApi(config, 200);
    setEvents(result.events);
    setSelectedId((current) => current ?? result.events[0]?.id ?? null);
  }

  useEffect(() => {
    void refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const filtered = useMemo(() => {
    if (!events) return null;
    const q = query.trim().toLowerCase();
    if (!q) return events;
    return events.filter((event) =>
      [
        event.actor,
        event.action,
        event.target_type,
        event.source_type ?? "",
        event.source_ref ?? "",
        event.reason ?? "",
        event.policy_version,
      ].some((field) => field.toLowerCase().includes(q))
    );
  }, [events, query]);

  const selected = events?.find((event) => event.id === selectedId) ?? null;

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={<SearchInput value={query} onChange={setQuery} placeholder="Filter audit log" />}
          loading={events === null && !error}
          empty={error ?? "No memory events."}
          totalLabel={events ? `${filtered?.length ?? 0} of ${events.length}` : null}
          items={filtered ?? []}
          renderItem={(event) => (
            <AuditRow
              key={event.id}
              event={event}
              selected={event.id === selectedId}
              onSelect={() => setSelectedId(event.id)}
            />
          )}
        />
      }
      detail={selected ? <AuditDetail event={selected} /> : <DetailPlaceholder>Select an audit event</DetailPlaceholder>}
    />
  );
}

function AuditRow({
  event,
  selected,
  onSelect,
}: {
  event: MemoryEvent;
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
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13.5px] font-medium leading-snug">{event.action.replaceAll("_", " ")}</div>
          <div className="mt-1 text-[12.5px] text-faint">{event.target_type}{event.target_id ? ` #${event.target_id}` : ""}</div>
        </div>
        <Pill>{event.actor}</Pill>
      </div>
      <div className="mt-1 text-[12px] text-faint">{formatRelativePast(event.created_at)}</div>
    </button>
  );
}

function AuditDetail({ event }: { event: MemoryEvent }) {
  return (
    <div className="px-7 py-6">
      <div className="mb-5 flex items-center gap-2">
        <h3 className="m-0 text-[16px] font-semibold tracking-[-0.01em] text-ink">{event.action.replaceAll("_", " ")}</h3>
        <Pill>{event.actor}</Pill>
      </div>

      <div className="mb-6">
        <MetaGrid
          rows={[
            { label: "Created", value: formatAbs(event.created_at) },
            { label: "Target", value: `${event.target_type}${event.target_id ? ` #${event.target_id}` : ""}` },
            event.source_type ? { label: "Source", value: event.source_type } : null,
            event.source_ref ? { label: "Source ref", value: event.source_ref, mono: true } : null,
            event.reason ? { label: "Reason", value: event.reason } : null,
            { label: "Policy", value: event.policy_version },
          ]}
        />
      </div>

      <h4 className="m-0 mb-2 text-[11.5px] font-semibold uppercase tracking-[0.08em] text-faint">Details</h4>
      <JsonBlock value={event.details} />
    </div>
  );
}
