import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Pencil, Pin, Search, Trash2, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import {
  type Fact,
  type FactKind,
  type Observation,
  type ObservationDetail,
  deleteFactApi,
  deleteObservationApi,
  getObservationApi,
  listFactsApi,
  listObservationsApi,
  updateFactTextApi,
  updateObservationSummaryApi,
} from "../api";

const MODAL_BACKDROP_DURATION = 0.2;
const MODAL_PANEL_DURATION = 0.22;
const MODAL_EASE = [0.2, 0.8, 0.2, 1] as const;

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

type Tab = "facts" | "observations";

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [tab, setTab] = useState<Tab>("facts");

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="memory"
          className="absolute inset-0 z-50 grid place-items-center p-8 bg-[rgba(0,0,0,0.32)] backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: MODAL_BACKDROP_DURATION, ease: MODAL_EASE }}
          onClick={close}
        >
          <motion.div
            className="w-[min(960px,calc(100vw-80px))] h-[min(680px,calc(100vh-80px))] grid grid-rows-[auto_auto_minmax(0,1fr)] rounded-[14px] bg-surface shadow-[var(--shadow-pop)] overflow-hidden border border-line-soft"
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={{ duration: MODAL_PANEL_DURATION, ease: MODAL_EASE }}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between gap-3 pl-6 pr-3 pt-5">
              <h2 className="m-0 text-[18px] font-semibold tracking-[-0.014em] text-ink">Memory</h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
              >
                <X size={13} strokeWidth={1.7} />
              </button>
            </header>

            <nav className="flex items-end gap-5 mx-6 mt-3 border-b border-line-soft">
              <TabButton label="Facts" active={tab === "facts"} onClick={() => setTab("facts")} />
              <TabButton
                label="Observations"
                active={tab === "observations"}
                onClick={() => setTab("observations")}
              />
            </nav>

            <div className="overflow-hidden">
              {tab === "facts" ? <FactsPane /> : <ObservationsPane />}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}

function TabButton({
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
        "relative pb-2 -mb-px text-[13px] font-medium tracking-[-0.005em] transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {label}
      {active && (
        <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-ink" />
      )}
    </button>
  );
}

// ─── Facts ────────────────────────────────────────────────────────────

function FactsPane() {
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
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setEditing(false);
    setDraft(fact.text);
  }, [fact.id, fact.text]);

  const dirty = editing && draft.trim() !== fact.text.trim();

  async function save() {
    if (!dirty || !draft.trim()) return;
    setBusy(true);
    try {
      await updateFactTextApi(config, fact.id, draft.trim());
      await onSaved();
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this fact? This cannot be undone.")) return;
    setBusy(true);
    try {
      await deleteFactApi(config, fact.id);
      await onDeleted();
    } finally {
      setBusy(false);
    }
  }

  return (
    <DetailShell
      header={
        <DetailMeta>
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
        <MetaGrid
          rows={[
            ["Created", formatAbs(fact.created_at)],
            ["Last accessed", formatAbs(fact.last_accessed_at)],
            ["Access count", String(fact.access_count)],
            ["Source", fact.source_type],
            fact.source_ref ? ["Source ref", fact.source_ref, "mono"] : null,
            fact.expires_at ? ["Expires", formatAbs(fact.expires_at)] : null,
          ]}
        />
      }
      actions={
        editing ? (
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
        )
      }
    />
  );
}

// ─── Observations ─────────────────────────────────────────────────────

function ObservationsPane() {
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
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setEditing(false);
    setDraft(detail.observation.summary);
  }, [detail.observation.id, detail.observation.summary]);

  const dirty = editing && draft.trim() !== detail.observation.summary.trim();

  async function save() {
    if (!dirty || !draft.trim()) return;
    setBusy(true);
    try {
      await updateObservationSummaryApi(config, detail.observation.id, draft.trim());
      await onSaved();
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this observation? This cannot be undone.")) return;
    setBusy(true);
    try {
      await deleteObservationApi(config, detail.observation.id);
      await onDeleted();
    } finally {
      setBusy(false);
    }
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
        editing ? (
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
        )
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

// ─── Pane / list / detail shell ───────────────────────────────────────

function PaneShell({
  list,
  detail,
}: {
  list: React.ReactNode;
  detail: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[minmax(280px,360px)_minmax(0,1fr)] h-full">
      <div className="flex flex-col min-h-0 bg-bg-main/50">{list}</div>
      <div className="min-h-0 overflow-y-auto scroll-thin">{detail}</div>
    </div>
  );
}

function ListColumn<T>({
  toolbar,
  items,
  renderItem,
  loading,
  empty,
  totalLabel,
}: {
  toolbar: React.ReactNode;
  items: T[];
  renderItem: (item: T) => React.ReactNode;
  loading: boolean;
  empty?: string;
  totalLabel: string | null;
}) {
  return (
    <>
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">{toolbar}</div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin px-2 pb-3">
        {loading ? (
          <Empty>Loading…</Empty>
        ) : items.length === 0 ? (
          <Empty>{empty ?? "No matches."}</Empty>
        ) : (
          <ul className="flex flex-col gap-px">{items.map(renderItem)}</ul>
        )}
      </div>
      {totalLabel && (
        <div className="px-4 py-2 text-[11px] text-faint tabular-nums">{totalLabel}</div>
      )}
    </>
  );
}

function DetailShell({
  header,
  body,
  meta,
  actions,
}: {
  header: React.ReactNode;
  body: React.ReactNode;
  meta: React.ReactNode;
  actions: React.ReactNode;
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-7 pt-6 pb-3">{header}</div>
      <div className="flex-1 min-h-0 px-7 overflow-y-auto scroll-thin">
        {body}
        <div className="mt-7 mb-6">{meta}</div>
      </div>
      <div className="flex items-center justify-end gap-2 px-7 py-3">{actions}</div>
    </div>
  );
}

function DetailMeta({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center flex-wrap gap-2 text-[11.5px] text-faint">{children}</div>
  );
}

function Sep() {
  return <span aria-hidden className="text-line">·</span>;
}

function MetaGrid({
  rows,
}: {
  rows: ([string, string] | [string, string, "mono"] | null)[];
}) {
  const present = rows.filter(Boolean) as ([string, string] | [string, string, "mono"])[];
  return (
    <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-y-2.5 text-[12px]">
      {present.map(([label, value, mono]) => (
        <Fragment key={label} label={label} value={value} mono={mono === "mono"} />
      ))}
    </dl>
  );
}

function Fragment({ label, value, mono }: { label: string; value: string; mono: boolean }) {
  return (
    <>
      <dt className="text-faint">{label}</dt>
      <dd
        className={clsx(
          "text-ink-soft min-w-0",
          mono ? "font-mono text-[11.5px] break-all whitespace-pre-wrap" : "",
        )}
      >
        {value}
      </dd>
    </>
  );
}

function DetailPlaceholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center h-full text-[13px] italic text-faint">{children}</div>
  );
}

// ─── Toolbar widgets ──────────────────────────────────────────────────

function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative flex-1 min-w-0">
      <Search
        size={11}
        strokeWidth={1.8}
        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className="w-full h-7 pl-7 pr-2 rounded-md bg-[rgba(0,0,0,0.04)] focus:bg-[rgba(0,0,0,0.06)] border border-transparent focus:border-line-soft text-[12px] text-ink-soft placeholder:text-faint outline-none transition-[background-color,border-color]"
      />
    </div>
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

// ─── Buttons ──────────────────────────────────────────────────────────

function PrimaryBtn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center h-7 px-3 rounded-md bg-ink text-on-ink text-[12px] font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}

function GhostBtn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[12px] text-ink-soft hover:bg-surface-soft hover:text-ink transition-colors disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function DangerBtn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[12px] text-ink-soft hover:bg-[rgba(220,38,38,0.08)] hover:text-[#b42318] transition-colors disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center min-h-[200px] text-[13px] italic text-faint">
      {children}
    </div>
  );
}

function formatRelativePast(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}

function formatAbs(value: string): string {
  const d = new Date(value);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
