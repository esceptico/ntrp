import { useEffect, useMemo, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type Fact,
  type Observation,
  type ObservationDetail,
  deleteObservationApi,
  getObservationApi,
  listObservationsApi,
  updateObservationSummaryApi,
} from "../../api";
import { useMountedRef, useMutationState } from "../../lib/hooks";
import { formatAbs, formatRelativePast } from "../../lib/format";
import {
  DangerBtn,
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ErrorPill,
  GhostBtn,
  ListColumn,
  PaneShell,
  PrimaryBtn,
  SearchInput,
  Sep,
} from "./shared";

export function ObservationsPane() {
  const config = useStore((s) => s.config);
  const [items, setItems] = useState<Observation[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ObservationDetail | null>(null);

  async function refresh() {
    const r = await listObservationsApi(config, { limit: 200, status: "active" });
    setItems(r.observations);
    setTotal(r.total);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Whenever a row is selected, fetch full detail with supporting facts.
  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    void getObservationApi(config, selectedId).then((d) => {
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
    return items.filter((o) => o.summary.toLowerCase().includes(q));
  }, [items, query]);

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={<SearchInput value={query} onChange={setQuery} placeholder="Filter observations" />}
          empty={items && items.length === 0 ? "Nothing here yet." : undefined}
          loading={items === null}
          totalLabel={items ? `${filtered?.length ?? 0} of ${total}` : null}
          items={filtered ?? []}
          renderItem={(o) => (
            <ObservationRow
              key={o.id}
              obs={o}
              selected={o.id === selectedId}
              onSelect={() => setSelectedId(o.id)}
            />
          )}
        />
      }
      detail={
        selectedId === null ? (
          <DetailPlaceholder>Select an observation to view details</DetailPlaceholder>
        ) : detail ? (
          <ObservationView
            key={detail.observation.id}
            detail={detail}
            onSaved={async () => {
              await refresh();
              const fresh = await getObservationApi(config, detail.observation.id);
              setDetail(fresh);
            }}
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

function ObservationRow({
  obs,
  selected,
  onSelect,
}: {
  obs: Observation;
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
      <div className="text-[12.5px] leading-snug line-clamp-2">{obs.summary}</div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-faint">
        <span className="tabular-nums">
          {obs.evidence_count} {obs.evidence_count === 1 ? "source" : "sources"}
        </span>
        <span aria-hidden>·</span>
        <span className="tabular-nums">{formatRelativePast(obs.last_accessed_at)}</span>
      </div>
    </button>
  );
}

function ObservationView({
  detail,
  onSaved,
  onDeleted,
}: {
  detail: ObservationDetail;
  onSaved: () => Promise<void>;
  onDeleted: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(detail.observation.summary);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  useEffect(() => {
    setEditing(false);
    setDraft(detail.observation.summary);
  }, [detail.observation.id, detail.observation.summary]);

  const dirty = editing && draft.trim() !== detail.observation.summary.trim();

  async function save() {
    if (!dirty || !draft.trim()) return;
    await run(async () => {
      await updateObservationSummaryApi(config, detail.observation.id, draft.trim());
      await onSaved();
      if (mounted.current) setEditing(false);
    });
  }

  async function remove() {
    if (!confirm("Delete this observation? This cannot be undone.")) return;
    await run(async () => {
      await deleteObservationApi(config, detail.observation.id);
      await onDeleted();
    });
  }

  return (
    <DetailShell
      header={
        <DetailMeta>
          <span>
            {detail.observation.evidence_count}{" "}
            {detail.observation.evidence_count === 1 ? "source" : "sources"}
          </span>
          <Sep />
          <span>accessed {detail.observation.access_count}×</span>
          <Sep />
          <span>created {formatAbs(detail.observation.created_at)}</span>
          {detail.observation.created_by && (
            <>
              <Sep />
              <span>by {detail.observation.created_by}</span>
            </>
          )}
        </DetailMeta>
      }
      body={
        editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                void save();
              }
            }}
            spellCheck={false}
            autoFocus
            className="w-full min-h-[160px] resize-none bg-transparent text-[14px] leading-relaxed text-ink outline-none"
          />
        ) : (
          <p className="text-[14px] leading-relaxed text-ink whitespace-pre-wrap m-0">
            {detail.observation.summary}
          </p>
        )
      }
      meta={<SupportingFacts facts={detail.supporting_facts} missing={detail.missing_source_fact_ids} />}
      actions={
        <>
          {error && <ErrorPill message={error} />}
          {editing ? (
            <>
              <GhostBtn
                onClick={() => {
                  setEditing(false);
                  setDraft(detail.observation.summary);
                }}
                disabled={busy}
              >
                Cancel
              </GhostBtn>
              <PrimaryBtn onClick={() => void save()} disabled={!dirty || busy || !draft.trim()}>
                {busy ? "Saving…" : "Save changes"}
              </PrimaryBtn>
            </>
          ) : (
            <>
              <DangerBtn onClick={() => void remove()} disabled={busy}>
                <Trash2 size={12} strokeWidth={1.8} /> Delete
              </DangerBtn>
              <GhostBtn onClick={() => setEditing(true)} disabled={busy}>
                <Pencil size={12} strokeWidth={1.8} /> Edit
              </GhostBtn>
            </>
          )}
        </>
      }
    />
  );
}

function SupportingFacts({ facts, missing }: { facts: Fact[]; missing: number[] }) {
  if (facts.length === 0 && missing.length === 0) return null;
  return (
    <section>
      <h3 className="m-0 mb-3 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">
        Supporting facts ({facts.length + missing.length})
      </h3>
      <ul className="flex flex-col gap-2">
        {facts.map((f) => (
          <li key={f.id} className="flex items-start gap-3">
            <span className="mt-[2px] text-[10px] uppercase tracking-[0.06em] text-faint shrink-0 w-[80px]">
              {f.kind}
            </span>
            <span className="text-[12.5px] leading-snug text-ink-soft">{f.text}</span>
          </li>
        ))}
        {missing.map((id) => (
          <li key={`missing-${id}`} className="flex items-start gap-3 italic">
            <span className="mt-[2px] text-[10px] uppercase tracking-[0.06em] text-faint shrink-0 w-[80px]">
              missing
            </span>
            <span className="text-[12.5px] text-faint">fact #{id} no longer available</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
