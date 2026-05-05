import { useEffect, useMemo, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type ProfileEntry,
  type ProfileEntryDetail,
  deleteProfileEntryApi,
  getProfileEntryApi,
  listProfileApi,
  updateProfileEntryApi,
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

export function ProfilePane() {
  const config = useStore((s) => s.config);
  const [items, setItems] = useState<ProfileEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ProfileEntryDetail | null>(null);

  async function refresh() {
    const r = await listProfileApi(config);
    setItems(r.entries);
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
    void getProfileEntryApi(config, selectedId).then((d) => {
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
    return items.filter((e) => e.summary.toLowerCase().includes(q) || e.kind.toLowerCase().includes(q));
  }, [items, query]);

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={<SearchInput value={query} onChange={setQuery} placeholder="Filter profile" />}
          empty={items && items.length === 0 ? "No profile entries yet." : undefined}
          loading={items === null}
          totalLabel={items ? `${filtered?.length ?? 0} of ${items.length}` : null}
          items={filtered ?? []}
          renderItem={(e) => (
            <ProfileRow
              key={e.id}
              entry={e}
              selected={e.id === selectedId}
              onSelect={() => setSelectedId(e.id)}
            />
          )}
        />
      }
      detail={
        selectedId === null ? (
          <DetailPlaceholder>Select an entry to view details</DetailPlaceholder>
        ) : detail ? (
          <ProfileView
            key={detail.entry.id}
            detail={detail}
            onSaved={async () => {
              await refresh();
              const fresh = await getProfileEntryApi(config, detail.entry.id);
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

function ProfileRow({
  entry,
  selected,
  onSelect,
}: {
  entry: ProfileEntry;
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
      <div className="text-[12.5px] leading-snug line-clamp-2">{entry.summary}</div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-faint">
        <span className="uppercase tracking-[0.06em]">{entry.kind}</span>
        <span aria-hidden>·</span>
        <span className="tabular-nums">{formatRelativePast(entry.updated_at)}</span>
      </div>
    </button>
  );
}

function ProfileView({
  detail,
  onSaved,
  onDeleted,
}: {
  detail: ProfileEntryDetail;
  onSaved: () => Promise<void>;
  onDeleted: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(detail.entry.summary);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  useEffect(() => {
    setEditing(false);
    setDraft(detail.entry.summary);
  }, [detail.entry.id, detail.entry.summary]);

  const dirty = editing && draft.trim() !== detail.entry.summary.trim();

  async function save() {
    if (!dirty || !draft.trim()) return;
    await run(async () => {
      await updateProfileEntryApi(config, detail.entry.id, { summary: draft.trim() });
      await onSaved();
      if (mounted.current) setEditing(false);
    });
  }

  async function remove() {
    if (!confirm("Delete this profile entry? This cannot be undone.")) return;
    await run(async () => {
      await deleteProfileEntryApi(config, detail.entry.id);
      await onDeleted();
    });
  }

  return (
    <DetailShell
      header={
        <DetailMeta>
          <span className="uppercase tracking-[0.06em]">{detail.entry.kind}</span>
          <Sep />
          <span>confidence {detail.entry.confidence.toFixed(2)}</span>
          <Sep />
          <span>updated {formatAbs(detail.entry.updated_at)}</span>
          {detail.entry.created_by && (
            <>
              <Sep />
              <span>by {detail.entry.created_by}</span>
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
          <p className="m-0 text-[14px] leading-relaxed text-ink whitespace-pre-wrap">
            {detail.entry.summary}
          </p>
        )
      }
      meta={<ProfileSources detail={detail} />}
      actions={
        <>
          {error && <ErrorPill message={error} />}
          {editing ? (
            <>
              <GhostBtn
                onClick={() => {
                  setEditing(false);
                  setDraft(detail.entry.summary);
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

function ProfileSources({ detail }: { detail: ProfileEntryDetail }) {
  const total = detail.source_facts.length + detail.source_observations.length;
  if (total === 0) return null;
  return (
    <section>
      <h3 className="m-0 mb-3 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">
        Sources ({total})
      </h3>
      <ul className="flex flex-col gap-2 m-0 p-0 list-none">
        {detail.source_facts.map((f) => (
          <li key={`f-${f.id}`} className="flex items-start gap-3">
            <span className="mt-[2px] text-[10px] uppercase tracking-[0.06em] text-faint shrink-0 w-[80px]">
              {f.kind}
            </span>
            <span className="text-[12.5px] leading-snug text-ink-soft">{f.text}</span>
          </li>
        ))}
        {detail.source_observations.map((o) => (
          <li key={`o-${o.id}`} className="flex items-start gap-3">
            <span className="mt-[2px] text-[10px] uppercase tracking-[0.06em] text-faint shrink-0 w-[80px]">
              observation
            </span>
            <span className="text-[12.5px] leading-snug text-ink-soft">{o.summary}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
