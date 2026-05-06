import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Pencil, Pin, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type Fact,
  type FactKind,
  deleteFactApi,
  listFactsApi,
  updateFactTextApi,
} from "../../api";
import { useMountedRef, useMutationState } from "../../lib/hooks";
import { formatAbs, formatRelativePast } from "../../lib/format";
import { factStatusLabel, factStatusTone } from "../../lib/memoryTrust";
import {
  DangerBtn,
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ErrorPill,
  GhostBtn,
  ListColumn,
  MetaGrid,
  PaneShell,
  Pill,
  PrimaryBtn,
  SearchInput,
  Sep,
} from "./shared";

const FACT_KINDS: FactKind[] = [
  "identity",
  "preference",
  "relationship",
  "decision",
  "project",
  "event",
  "artifact",
  "procedure",
  "constraint",
  "note",
];

export function FactsPane({ targetFact }: { targetFact?: Fact | null }) {
  const config = useStore((s) => s.config);
  const [facts, setFacts] = useState<Fact[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<FactKind | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  async function refresh() {
    const r = await listFactsApi(config, { limit: 200, kind: kind ?? undefined, status: "active" });
    setFacts(r.facts);
    setTotal(r.total);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  useEffect(() => {
    if (!targetFact) return;
    setFacts((prev) => {
      const existing = prev ?? [];
      return [targetFact, ...existing.filter((fact) => fact.id !== targetFact.id)];
    });
    setSelectedId(targetFact.id);
    setQuery("");
    setKind(null);
  }, [targetFact]);

  const filtered = useMemo(() => {
    if (!facts) return null;
    const q = query.trim().toLowerCase();
    if (!q) return facts;
    return facts.filter((f) => f.text.toLowerCase().includes(q));
  }, [facts, query]);

  const selected = facts?.find((f) => f.id === selectedId) ?? null;

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={
            <>
              <SearchInput value={query} onChange={setQuery} placeholder="Filter facts" />
              <KindFilter value={kind} onChange={setKind} />
            </>
          }
          empty={facts && facts.length === 0 ? "Nothing here yet." : undefined}
          loading={facts === null}
          totalLabel={facts ? `${filtered?.length ?? 0} of ${total}` : null}
          items={filtered ?? []}
          renderItem={(f) => (
            <FactRow
              key={f.id}
              fact={f}
              selected={f.id === selectedId}
              onSelect={() => setSelectedId(f.id)}
            />
          )}
        />
      }
      detail={
        selected ? (
          <FactDetail
            key={selected.id}
            fact={selected}
            onSaved={refresh}
            onDeleted={async () => {
              setSelectedId(null);
              await refresh();
            }}
          />
        ) : (
          <DetailPlaceholder>Select a fact to view details</DetailPlaceholder>
        )
      }
    />
  );
}

function FactRow({
  fact,
  selected,
  onSelect,
}: {
  fact: Fact;
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
      <div className="flex items-start gap-2">
        {fact.pinned_at && (
          <Pin size={11} strokeWidth={1.8} className="mt-[3px] shrink-0 text-accent-strong" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] leading-snug line-clamp-2">{fact.text}</div>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-faint">
            <span className="uppercase tracking-[0.06em]">{fact.kind}</span>
            <span aria-hidden>·</span>
            <span>{factStatusLabel(fact.status)}</span>
            <span aria-hidden>·</span>
            <span className="tabular-nums">{formatRelativePast(fact.last_accessed_at)}</span>
            {fact.access_count > 0 && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums">{fact.access_count}×</span>
              </>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

function FactDetail({
  fact,
  onSaved,
  onDeleted,
}: {
  fact: Fact;
  onSaved: () => Promise<void>;
  onDeleted: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact.text);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  useEffect(() => {
    setEditing(false);
    setDraft(fact.text);
  }, [fact.id, fact.text]);

  const dirty = editing && draft.trim() !== fact.text.trim();

  async function save() {
    if (!dirty || !draft.trim()) return;
    await run(async () => {
      await updateFactTextApi(config, fact.id, draft.trim());
      await onSaved();
      if (mounted.current) setEditing(false);
    });
  }

  async function remove() {
    if (!confirm("Delete this fact? This cannot be undone.")) return;
    await run(async () => {
      await deleteFactApi(config, fact.id);
      await onDeleted();
    });
  }

  return (
    <DetailShell
      header={
        <DetailMeta>
          <Pill tone={factStatusTone(fact.status)}>{factStatusLabel(fact.status)}</Pill>
          <span className="uppercase tracking-[0.06em]">{fact.kind}</span>
          <Sep />
          <span>salience {fact.salience.toFixed(2)}</span>
          <Sep />
          <span>confidence {fact.confidence.toFixed(2)}</span>
          {fact.lifetime !== "durable" && (
            <>
              <Sep />
              <span className="uppercase tracking-[0.06em]">{fact.lifetime}</span>
            </>
          )}
          {fact.pinned_at && (
            <>
              <Sep />
              <span className="inline-flex items-center gap-1 text-accent-strong">
                <Pin size={10} strokeWidth={2} /> pinned
              </span>
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
            {fact.text}
          </p>
        )
      }
      meta={
        <>
          <MetaGrid
            rows={[
              { label: "Created", value: formatAbs(fact.created_at) },
              fact.happened_at ? { label: "Happened", value: formatAbs(fact.happened_at) } : null,
              { label: "Last accessed", value: formatAbs(fact.last_accessed_at) },
              { label: "Access count", value: String(fact.access_count) },
              { label: "Source", value: fact.source_type },
              fact.source_ref ? { label: "Source ref", value: fact.source_ref, mono: true } : null,
              fact.expires_at ? { label: "Expires", value: formatAbs(fact.expires_at) } : null,
              fact.superseded_by_fact_id
                ? { label: "Superseded by", value: `fact #${fact.superseded_by_fact_id}` }
                : null,
            ]}
          />
        </>
      }
      actions={
        <>
          {error && <ErrorPill message={error} />}
          {editing ? (
            <>
              <GhostBtn
                onClick={() => {
                  setEditing(false);
                  setDraft(fact.text);
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

function KindFilter({
  value,
  onChange,
}: {
  value: FactKind | null;
  onChange: (v: FactKind | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "inline-flex items-center gap-1 h-7 pl-2.5 pr-1.5 rounded-md text-[11.5px] font-medium tracking-[-0.005em] transition-colors",
          value
            ? "bg-ink text-on-ink"
            : "text-ink-soft bg-[rgba(0,0,0,0.04)] hover:bg-[rgba(0,0,0,0.06)]",
        )}
      >
        <span className="capitalize">{value ?? "All kinds"}</span>
        <ChevronDown size={11} strokeWidth={1.8} className="opacity-70" />
      </button>
      {open && (
        <div className="absolute top-full mt-1 right-0 z-10 w-[160px] py-1 rounded-[10px] border border-line-soft bg-surface shadow-[var(--shadow-pop)]">
          <KindOption
            label="All kinds"
            active={value === null}
            onClick={() => {
              onChange(null);
              setOpen(false);
            }}
          />
          <div className="my-1 mx-2 h-px bg-line-soft" />
          {FACT_KINDS.map((k) => (
            <KindOption
              key={k}
              label={k}
              active={value === k}
              onClick={() => {
                onChange(k);
                setOpen(false);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function KindOption({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "w-full flex items-center px-2.5 py-1.5 text-left text-[12px] capitalize transition-colors",
        active ? "text-ink font-medium" : "text-ink-soft hover:bg-surface-soft/60 hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}
