import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { GitFork, Plus, RefreshCw } from "lucide-react";
import type { AppConfig } from "../../api";
import {
  createLens,
  deleteLens,
  editLensCriterion,
  getLensPage,
  listMemoryLenses,
  writebackLens,
  type CoverageAdvisory,
  type LensDetailLevel,
  type LensWithCoverage,
  type MemoryItem,
  type PageEditOp,
  type ProjectedPage,
} from "../../api/memoryItems";
import { SPRING_LAYOUT, SPRING_ROW_ENTRY } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { Badge } from "../Badge";
import { Tab, Tabs } from "../ui/Tabs";
import { ClaimBlock, type ClaimOp } from "./ClaimBlock";
import {
  DetailPlaceholder,
  DetailShell,
  Empty,
  GhostBtn,
  ListError,
  PrimaryBtn,
  SearchInput,
} from "./shared";
import { lensColor, lensTitle, provenanceLabel, provenanceTone, scopeLabel } from "./lens";

const DETAILS: LensDetailLevel[] = ["gist", "structured", "dossier"];
const DETAIL_LABEL: Record<LensDetailLevel, string> = {
  gist: "Gist",
  structured: "List",
  dossier: "Dossier",
};

export function LensesView({
  config,
  onPeekClaim,
  onProvenance,
}: {
  config: AppConfig;
  onPeekClaim: (claimId: string) => void;
  onProvenance: (lensId: string) => void;
}) {
  const [lenses, setLenses] = useState<LensWithCoverage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);

  const reloadList = useCallback(() => {
    setLoading(true);
    listMemoryLenses(config)
      .then((r) => {
        setLenses(r.lenses);
        setError(null);
        setSelectedId((cur) => cur ?? r.lenses[0]?.lens.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [config]);

  useEffect(() => {
    reloadList();
  }, [reloadList]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return lenses;
    return lenses.filter(({ lens }) =>
      `${lensTitle(lens)} ${lens.lens_criterion ?? ""}`.toLowerCase().includes(q),
    );
  }, [lenses, filter]);

  const selected = lenses.find((l) => l.lens.id === selectedId) ?? null;

  const onCreated = (lens: MemoryItem) => {
    setComposing(false);
    setSelectedId(lens.id);
    reloadList();
  };

  return (
    <div className="grid h-full grid-cols-[minmax(280px,340px)_minmax(0,1fr)]">
      {/* Rail — anchored sidebar: no specular rim, sibling to the slab. */}
      <div className="surface-rail m-2 mr-1 flex min-h-0 flex-col">
        <div className="flex items-center gap-2 px-2.5 pt-2.5 pb-2">
          <SearchInput value={filter} onChange={setFilter} placeholder="Filter lenses…" />
          <IconButton onClick={() => setComposing((v) => !v)} aria-label="New lens" size="md">
            <Plus size={ICON.MD} strokeWidth={2} />
          </IconButton>
        </div>

        <AnimatePresence initial={false}>
          {composing && (
            <motion.div
              layout
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={SPRING_LAYOUT}
              className="overflow-hidden px-2.5"
            >
              <Composer config={config} onCreated={onCreated} onCancel={() => setComposing(false)} />
            </motion.div>
          )}
        </AnimatePresence>

        <div className="min-h-0 flex-1 overflow-y-auto scroll-thin px-1.5 pb-2">
          {loading ? (
            <Empty>Loading…</Empty>
          ) : error ? (
            <div className="px-1 py-3">
              <ListError title="Couldn't load lenses" message={error} />
            </div>
          ) : filtered.length === 0 ? (
            <Empty>{lenses.length === 0 ? "Name a view of your memory." : "No matches."}</Empty>
          ) : (
            <ul className="flex flex-col gap-px">
              {filtered.map(({ lens, coverage }) => (
                <LensRow
                  key={lens.id}
                  lens={lens}
                  coverage={coverage}
                  active={lens.id === selectedId}
                  onSelect={() => setSelectedId(lens.id)}
                />
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Page */}
      <div className="min-h-0 overflow-hidden">
        {selected ? (
          <LensPage
            key={selected.lens.id}
            config={config}
            lens={selected.lens}
            coverage={selected.coverage}
            onPeekClaim={onPeekClaim}
            onProvenance={() => onProvenance(selected.lens.id)}
            onListChanged={reloadList}
            onArchived={() => {
              setSelectedId(null);
              reloadList();
            }}
          />
        ) : (
          <DetailPlaceholder>Select a lens, or name a new view of your memory.</DetailPlaceholder>
        )}
      </div>
    </div>
  );
}

function LensRow({
  lens,
  coverage,
  active,
  onSelect,
}: {
  lens: MemoryItem;
  coverage: CoverageAdvisory;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-selected={active}
        className="app-row group flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left"
      >
        <span
          aria-hidden
          className="mt-px size-2 shrink-0 rounded-[3px]"
          style={{ backgroundColor: lensColor(lens) }}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">{lensTitle(lens)}</span>
          {lens.lens_criterion && (
            <span className="block truncate text-xs text-faint">{lens.lens_criterion}</span>
          )}
        </span>
        <Badge tone={coverage.generic ? "warn" : "neutral"} size="sm" className="tabular-nums">
          {coverage.member_count}
        </Badge>
      </button>
    </li>
  );
}

function Composer({
  config,
  onCreated,
  onCancel,
}: {
  config: AppConfig;
  onCreated: (lens: MemoryItem) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [criterion, setCriterion] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const submit = () => {
    if (!name.trim() || !criterion.trim() || busy) return;
    setBusy(true);
    setErr(null);
    createLens(config, { name: name.trim(), criterion: criterion.trim() })
      .then((r) => onCreated(r.lens))
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  };

  return (
    <div className="glass-surface surface-popover mb-2 flex flex-col gap-2 p-2.5">
      <input
        ref={nameRef}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Lens name (e.g. People)"
        spellCheck={false}
        className="input-field h-7 text-sm"
      />
      <textarea
        value={criterion}
        onChange={(e) => setCriterion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
        }}
        placeholder="Describe what this view collects…"
        rows={2}
        spellCheck={false}
        className="input-field resize-none py-1.5 text-sm leading-snug"
      />
      {err && <span className="text-xs text-bad">{err}</span>}
      <div className="flex items-center justify-between">
        <span className="text-2xs text-faint">Backfills once on create.</span>
        <div className="flex items-center gap-1">
          <GhostBtn onClick={onCancel} disabled={busy}>
            Cancel
          </GhostBtn>
          <PrimaryBtn onClick={submit} disabled={busy || !name.trim() || !criterion.trim()}>
            {busy ? "Creating…" : "Create"}
          </PrimaryBtn>
        </div>
      </div>
    </div>
  );
}

// ── Lens page (detail) ──────────────────────────────────────────────────────

function LensPage({
  config,
  lens,
  coverage,
  onPeekClaim,
  onProvenance,
  onListChanged,
  onArchived,
}: {
  config: AppConfig;
  lens: MemoryItem;
  coverage: CoverageAdvisory;
  onPeekClaim: (claimId: string) => void;
  onProvenance: () => void;
  onListChanged: () => void;
  onArchived: () => void;
}) {
  const [detail, setDetail] = useState<LensDetailLevel>(lens.lens_detail_level ?? "structured");
  const [page, setPage] = useState<ProjectedPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [exiting, setExiting] = useState<{ id: string; how: "supersede" | "reject" } | null>(null);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [editingCriterion, setEditingCriterion] = useState(false);
  const [adding, setAdding] = useState(false);

  const load = useCallback(
    (opts: { detail: LensDetailLevel; refresh?: boolean }) => {
      setLoading(true);
      getLensPage(config, lens.id, { detail: opts.detail, refresh: opts.refresh })
        .then((p) => {
          setPage(p);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    },
    [config, lens.id],
  );

  useEffect(() => {
    load({ detail });
  }, [load, detail]);

  const applyOps = useCallback(
    async (ops: PageEditOp[], hint: { id: string; how: "supersede" | "reject" } | null) => {
      const opId = hint?.id ?? "lens";
      setBusyId(opId);
      try {
        const res = await writebackLens(config, lens.id, ops);
        const parts: string[] = [];
        if (res.applied.length) parts.push(`${res.applied.length} applied`);
        if (res.rejected.length) parts.push(`${res.rejected.length} rejected`);
        setRunNote(parts.join(" · ") || "no change");
        if (hint && res.applied.length) {
          setExiting(hint);
          // let the exit animation play, then re-fetch the spine
          setTimeout(() => {
            setExiting(null);
            load({ detail, refresh: res.rederive_triggered });
            onListChanged();
          }, 240);
        } else {
          load({ detail, refresh: res.rederive_triggered });
          onListChanged();
        }
      } catch (e) {
        setRunNote(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
        setEditingId(null);
        setAdding(false);
      }
    },
    [config, lens.id, load, detail, onListChanged],
  );

  const onClaimCommit = (op: ClaimOp) => {
    const how = op.kind === "reject" ? "reject" : op.kind === "edit" ? "supersede" : null;
    void applyOps([op], how ? { id: op.claim_id, how } : null);
  };

  return (
    <DetailShell
      header={
        <LensHeader
          lens={lens}
          detail={detail}
          onDetail={setDetail}
          onProvenance={onProvenance}
          onRefresh={() => load({ detail, refresh: true })}
          refreshing={loading}
        />
      }
      body={
        <div className="pb-2">
          <CriterionRow
            config={config}
            lens={lens}
            coverage={coverage}
            editing={editingCriterion}
            onEdit={() => setEditingCriterion(true)}
            onDone={(changed) => {
              setEditingCriterion(false);
              if (changed) {
                onListChanged();
                load({ detail, refresh: true });
              }
            }}
          />

          {loading && !page ? (
            <PageSkeleton />
          ) : error ? (
            <div className="mt-4">
              <ListError title="Couldn't render page" message={error} />
            </div>
          ) : page && page.blocks.length === 0 ? (
            <Empty>Nothing matches this criterion yet. New memories appear here as they're admitted.</Empty>
          ) : (
            <div className="mt-3 flex flex-col gap-0.5">
              <AnimatePresence initial={false}>
                {page?.blocks.map((b) => (
                  <ClaimBlock
                    key={b.claim_id}
                    block={b}
                    editing={editingId === b.claim_id}
                    busy={busyId === b.claim_id}
                    exiting={exiting?.id === b.claim_id ? exiting.how : null}
                    onOpen={() => setEditingId(b.claim_id)}
                    onClose={() => setEditingId(null)}
                    onCommit={onClaimCommit}
                    onPeek={() => onPeekClaim(b.claim_id)}
                  />
                ))}
              </AnimatePresence>
            </div>
          )}

          <AddClaim
            open={adding}
            busy={busyId === "lens"}
            onOpen={() => setAdding(true)}
            onCancel={() => setAdding(false)}
            onAdd={(text) => void applyOps([{ kind: "add", new_text: text }], null)}
          />
        </div>
      }
      meta={
        <div className="flex items-center justify-between gap-3 text-xs text-faint">
          <CoverageStrip coverage={coverage} />
          <AnimatePresence>
            {runNote && (
              <motion.span
                key={runNote}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="tabular-nums text-muted"
              >
                {runNote}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      }
      actions={
        <>
          <span className="mr-auto text-xs text-faint">
            {page?.synthesized === false && "raw list (synthesis unavailable)"}
          </span>
          <GhostBtn onClick={() => setEditingCriterion(true)}>Edit criterion</GhostBtn>
          <GhostBtn
            onClick={() => {
              if (window.confirm(`Archive the "${lensTitle(lens)}" view? Claims are untouched.`)) {
                void deleteLens(config, lens.id).then(onArchived);
              }
            }}
          >
            Archive view
          </GhostBtn>
        </>
      }
    />
  );
}

function LensHeader({
  lens,
  detail,
  onDetail,
  onProvenance,
  onRefresh,
  refreshing,
}: {
  lens: MemoryItem;
  detail: LensDetailLevel;
  onDetail: (d: LensDetailLevel) => void;
  onProvenance: () => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-xl font-semibold tracking-[-0.012em] text-ink">
          <span aria-hidden className="size-2.5 rounded-[3px]" style={{ backgroundColor: lensColor(lens) }} />
          <span className="truncate">{lensTitle(lens)}</span>
        </h2>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral" size="sm">
            {lens.lens_kind ?? "topic"}
          </Badge>
          <Badge tone="neutral" size="sm">
            {scopeLabel(lens.scope)}
          </Badge>
          <Badge tone={provenanceTone(lens.provenance)} size="sm">
            {provenanceLabel(lens.provenance)}
          </Badge>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Tabs value={detail} onChange={(v) => onDetail(v as LensDetailLevel)} variant="pill" className="gap-0.5 rounded-lg bg-surface-soft p-0.5">
          {DETAILS.map((d) => (
            <Tab key={d} value={d} className="rounded-md px-2.5 py-1 text-xs font-medium text-muted data-[active=true]:text-ink">
              {DETAIL_LABEL[d]}
            </Tab>
          ))}
        </Tabs>
        <IconButton onClick={onProvenance} aria-label="Provenance graph" size="md" title="Provenance graph">
          <GitFork size={ICON.SM} strokeWidth={2} />
        </IconButton>
        <IconButton onClick={onRefresh} aria-label="Re-synthesize" size="md" title="Re-synthesize (LLM)">
          <RefreshCw size={ICON.SM} strokeWidth={2} className={refreshing ? "animate-spin" : undefined} />
        </IconButton>
      </div>
    </div>
  );
}

function CriterionRow({
  config,
  lens,
  coverage,
  editing,
  onEdit,
  onDone,
}: {
  config: AppConfig;
  lens: MemoryItem;
  coverage: CoverageAdvisory;
  editing: boolean;
  onEdit: () => void;
  onDone: (changed: boolean) => void;
}) {
  const [text, setText] = useState(lens.lens_criterion ?? "");
  const [busy, setBusy] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      setText(lens.lens_criterion ?? "");
      requestAnimationFrame(() => taRef.current?.focus());
    }
  }, [editing, lens.lens_criterion]);

  if (!editing) {
    return (
      <button
        type="button"
        onClick={onEdit}
        className="group/crit -mx-1 block w-full rounded-md px-1 py-1 text-left text-sm italic text-faint transition-colors hover:bg-surface-soft/50 hover:text-muted"
      >
        {lens.lens_criterion || "No criterion — click to describe what this view collects."}
      </button>
    );
  }

  const dirty = text.trim() !== (lens.lens_criterion ?? "").trim() && text.trim().length > 0;
  const save = () => {
    if (!dirty || busy) return;
    setBusy(true);
    editLensCriterion(config, lens.id, text.trim())
      .then(() => onDone(true))
      .catch(() => onDone(false))
      .finally(() => setBusy(false));
  };

  return (
    <div className="glass-surface surface-popover my-1 p-2.5">
      <textarea
        ref={taRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
          if (e.key === "Escape") onDone(false);
        }}
        rows={2}
        spellCheck={false}
        className="w-full resize-none bg-transparent text-sm leading-snug text-ink outline-none"
      />
      <div className="mt-1.5">
        <CoverageMeter coverage={coverage} />
      </div>
      <div className="mt-2 flex items-center justify-end gap-1">
        <GhostBtn onClick={() => onDone(false)} disabled={busy}>
          Cancel
        </GhostBtn>
        <PrimaryBtn onClick={save} disabled={busy || !dirty}>
          {busy ? "Re-cutting…" : "Save criterion"}
        </PrimaryBtn>
      </div>
    </div>
  );
}

function AddClaim({
  open,
  busy,
  onOpen,
  onCancel,
  onAdd,
}: {
  open: boolean;
  busy: boolean;
  onOpen: () => void;
  onCancel: () => void;
  onAdd: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) requestAnimationFrame(() => taRef.current?.focus());
    else setText("");
  }, [open]);

  if (!open) {
    return (
      <div className="mt-2 pl-4">
        <GhostBtn onClick={onOpen}>
          <Plus size={ICON.XS} strokeWidth={2.2} /> Add to this lens
        </GhostBtn>
      </div>
    );
  }

  const submit = () => {
    if (!text.trim() || busy) return;
    onAdd(text.trim());
    setText("");
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={SPRING_ROW_ENTRY}
      className="glass-surface surface-popover mt-2 p-2.5"
    >
      <textarea
        ref={taRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          if (e.key === "Escape") onCancel();
        }}
        placeholder="Add a claim to this view…"
        rows={2}
        spellCheck={false}
        className="w-full resize-none bg-transparent text-sm leading-[1.55] text-ink outline-none placeholder:text-faint"
      />
      <div className="mt-2 flex items-center justify-end gap-1">
        <GhostBtn onClick={onCancel} disabled={busy}>
          Cancel
        </GhostBtn>
        <PrimaryBtn onClick={submit} disabled={busy || !text.trim()}>
          {busy ? "Adding…" : "Add"}
        </PrimaryBtn>
      </div>
    </motion.div>
  );
}

function CoverageStrip({ coverage }: { coverage: CoverageAdvisory }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <CoverageMeter coverage={coverage} compact />
      <span className="shrink-0 tabular-nums">
        {coverage.member_count}/{coverage.scope_pool} in scope
      </span>
      {coverage.generic && (
        <span className="truncate text-warn" title={coverage.suggestion}>
          — {coverage.suggestion || "matching most of your memory — narrow?"}
        </span>
      )}
    </div>
  );
}

function CoverageMeter({ coverage, compact }: { coverage: CoverageAdvisory; compact?: boolean }) {
  const pct = Math.min(100, Math.round(coverage.ratio * 100));
  return (
    <div className={compact ? "h-1 w-16 overflow-hidden rounded-full bg-surface-sunken" : "h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken"}>
      <motion.div
        layout
        initial={false}
        animate={{ width: `${pct}%` }}
        transition={SPRING_LAYOUT}
        className={coverage.generic ? "h-full rounded-full bg-warn" : "h-full rounded-full bg-accent"}
      />
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="mt-4 flex flex-col gap-2">
      {[92, 78, 85, 64, 88].map((w, i) => (
        <div key={i} className="skeleton h-4 rounded" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}
