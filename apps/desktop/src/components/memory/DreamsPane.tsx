import { useEffect, useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type Dream,
  type DreamDetail,
  deleteDreamApi,
  getDreamApi,
  listDreamsApi,
} from "../../api";
import { useMountedRef, useMutationState } from "../../lib/hooks";
import { formatAbs, formatRelativePast } from "../../lib/format";
import {
  DangerBtn,
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ErrorPill,
  ListColumn,
  PaneShell,
  SearchInput,
  Sep,
} from "./shared";

export function DreamsPane() {
  const config = useStore((s) => s.config);
  const [items, setItems] = useState<Dream[] | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DreamDetail | null>(null);

  async function refresh() {
    const r = await listDreamsApi(config);
    setItems(r.dreams);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    void getDreamApi(config, selectedId).then((d) => {
      if (!cancelled) setDetail(d);
    });
    return () => {
      cancelled = true;
    };
  }, [config, selectedId]);

  const filtered = useMemo(() => {
    if (!items) return null;
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (d) => d.bridge.toLowerCase().includes(q) || d.insight.toLowerCase().includes(q),
    );
  }, [items, query]);

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={<SearchInput value={query} onChange={setQuery} placeholder="Filter dreams" />}
          empty={items && items.length === 0 ? "No dreams yet." : undefined}
          loading={items === null}
          totalLabel={items ? `${filtered?.length ?? 0} of ${items.length}` : null}
          items={filtered ?? []}
          renderItem={(d) => (
            <DreamRow
              key={d.id}
              dream={d}
              selected={d.id === selectedId}
              onSelect={() => setSelectedId(d.id)}
            />
          )}
        />
      }
      detail={
        selectedId === null ? (
          <DetailPlaceholder>Select a dream to view details</DetailPlaceholder>
        ) : detail ? (
          <DreamView
            key={detail.dream.id}
            detail={detail}
            onDeleted={async () => {
              setSelectedId(null);
              await refresh();
            }}
          />
        ) : (
          <DetailPlaceholder>Loading…</DetailPlaceholder>
        )
      }
    />
  );
}

function DreamRow({
  dream,
  selected,
  onSelect,
}: {
  dream: Dream;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "w-full text-left px-4 py-2.5 transition-colors rounded-md",
        selected ? "bg-surface-soft text-ink" : "hover:bg-surface-soft/50 text-ink-soft",
      )}
    >
      <div className="text-[12.5px] font-medium leading-snug line-clamp-1">{dream.bridge}</div>
      <div className="mt-1 text-[11.5px] text-faint leading-snug line-clamp-2">{dream.insight}</div>
      <div className="mt-1 text-[11px] text-faint tabular-nums">
        {formatRelativePast(dream.created_at)}
      </div>
    </button>
  );
}

function DreamView({
  detail,
  onDeleted,
}: {
  detail: DreamDetail;
  onDeleted: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  async function remove() {
    if (!confirm("Delete this dream? This cannot be undone.")) return;
    await run(async () => {
      await deleteDreamApi(config, detail.dream.id);
      await onDeleted();
    });
  }

  return (
    <DetailShell
      header={
        <DetailMeta>
          <span>created {formatAbs(detail.dream.created_at)}</span>
          <Sep />
          <span>{detail.source_facts.length} source facts</span>
        </DetailMeta>
      }
      body={
        <>
          <h3 className="m-0 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">
            Bridge
          </h3>
          <p className="m-0 mb-5 text-[14px] font-medium leading-relaxed text-ink whitespace-pre-wrap">
            {detail.dream.bridge}
          </p>
          <h3 className="m-0 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">
            Insight
          </h3>
          <p className="m-0 text-[14px] leading-relaxed text-ink whitespace-pre-wrap">
            {detail.dream.insight}
          </p>
        </>
      }
      meta={
        detail.source_facts.length > 0 && (
          <section>
            <h3 className="m-0 mb-3 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">
              Source facts
            </h3>
            <ul className="flex flex-col gap-2 m-0 p-0 list-none">
              {detail.source_facts.map((f) => (
                <li
                  key={f.id}
                  className="text-[12.5px] leading-snug text-ink-soft"
                >
                  {f.text}
                </li>
              ))}
            </ul>
          </section>
        )
      }
      actions={
        <>
          {error && <ErrorPill message={error} />}
          <DangerBtn onClick={() => void remove()} disabled={busy}>
            <Trash2 size={12} strokeWidth={1.8} /> Delete
          </DangerBtn>
        </>
      }
    />
  );
}
