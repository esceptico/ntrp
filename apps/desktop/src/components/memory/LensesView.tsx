import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, Check, ChevronRight, GitFork, Loader2, Plus, RefreshCw, Users } from "lucide-react";
import type { AppConfig } from "../../api";
import {
  createLens,
  deleteLens,
  editLensCriterion,
  getLensPage,
  getLensPageStatus,
  isLensGenStatus,
  listMemoryLenses,
  setLensRenderMode,
  writebackLens,
  type CoverageAdvisory,
  type Lens,
  type LensDetailLevel,
  type LensGenStatus,
  type LensWithCoverage,
  type PageEditOp,
  type ProjectedGroup,
  type ProjectedPage,
} from "../../api/memoryItems";
import { Markdown } from "../Markdown";
import { SPRING_LAYOUT, SPRING_ROW_ENTRY } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { Badge } from "../Badge";
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
import { lensColor, lensProvenanceLabel, lensProvenanceTone, lensTitle, scopeLabel } from "./lens";


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
      `${lensTitle(lens)} ${lens.criterion}`.toLowerCase().includes(q),
    );
  }, [lenses, filter]);

  const selected = lenses.find((l) => l.lens.id === selectedId) ?? null;

  const onCreated = (lens: Lens) => {
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
  lens: Lens;
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
          className="mt-px size-2 shrink-0 rounded-full"
          style={{ backgroundColor: lensColor(lens) }}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">{lensTitle(lens)}</span>
          {lens.criterion && (
            <span className="block truncate text-xs text-faint">{lens.criterion}</span>
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
  onCreated: (lens: Lens) => void;
  onCancel: () => void;
}) {
  // Phase A: name only → create (criterion synthesized server-side).
  // Phase B: the generated criterion, prefilled + editable, before finishing.
  const [name, setName] = useState("");
  const [created, setCreated] = useState<Lens | null>(null);
  const [criterion, setCriterion] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const critRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  // Auto-grow the criterion box to its content so the generated text is never
  // clipped (it can be several lines) and stays fully readable/editable.
  useEffect(() => {
    const el = critRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 280)}px`;
  }, [criterion, created]);

  const create = () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr(null);
    createLens(config, { name: name.trim() })
      .then((r) => {
        setCreated(r.lens);
        setCriterion(r.lens.criterion);
        setBusy(false);
        requestAnimationFrame(() => critRef.current?.focus());
      })
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  };

  const finish = () => {
    if (!created || busy) return;
    const next = criterion.trim();
    if (next && next !== created.criterion.trim()) {
      setBusy(true);
      editLensCriterion(config, created.id, next)
        .then((r) => onCreated(r.lens))
        .catch((e) => {
          setErr(e instanceof Error ? e.message : String(e));
          setBusy(false);
        });
    } else {
      onCreated(created);
    }
  };

  if (!created) {
    return (
      <div className="glass-surface surface-popover mb-2 flex flex-col gap-2 p-2.5">
        <input
          ref={nameRef}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") create();
            if (e.key === "Escape") onCancel();
          }}
          placeholder="Lens name (e.g. People)"
          spellCheck={false}
          className="input-field h-7 text-sm"
        />
        {err && <span className="text-xs text-bad">{err}</span>}
        <div className="flex items-center justify-between">
          <span className="text-2xs text-faint">Name it — we'll draft the criterion.</span>
          <div className="flex items-center gap-1">
            <GhostBtn onClick={onCancel} disabled={busy}>
              Cancel
            </GhostBtn>
            <PrimaryBtn onClick={create} disabled={busy || !name.trim()}>
              {busy ? "Creating…" : "Create"}
            </PrimaryBtn>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-surface surface-popover mb-2 flex flex-col gap-2 p-2.5">
      <textarea
        ref={critRef}
        value={criterion}
        onChange={(e) => setCriterion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) finish();
        }}
        rows={3}
        spellCheck={false}
        className="input-field resize-none overflow-y-auto py-1.5 text-sm leading-relaxed"
      />
      {err && <span className="text-xs text-bad">{err}</span>}
      <div className="flex items-center justify-between">
        <span className="text-2xs text-faint">Generated criterion — edit if needed.</span>
        <PrimaryBtn onClick={finish} disabled={busy || !criterion.trim()}>
          {busy ? "Saving…" : "Done"}
        </PrimaryBtn>
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
  lens: Lens;
  coverage: CoverageAdvisory;
  onPeekClaim: (claimId: string) => void;
  onProvenance: () => void;
  onListChanged: () => void;
  onArchived: () => void;
}) {
  // Detail level is fixed to the lens's own setting — no user-facing toggle.
  const detail = lens.detail_level;
  const [grouped, setGrouped] = useState(lens.render_mode === "grouped_by_subject");
  const [page, setPage] = useState<ProjectedPage | null>(null);
  const [gen, setGen] = useState<LensGenStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [exiting, setExiting] = useState<{ id: string; how: "supersede" | "reject" } | null>(null);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [editingCriterion, setEditingCriterion] = useState(false);
  const [adding, setAdding] = useState(false);

  // A generation poll in flight — cancelled on unmount/reload so a stale loop
  // never writes into a remounted page (lens switch keys remount LensPage).
  const pollRef = useRef<{ alive: boolean } | null>(null);
  // Exit-animation timer for a write-back op; tracked so a lens switch within the
  // 240ms window can't fire load()/re-arm a poll on the unmounted page.
  const exitTimerRef = useRef<number | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) pollRef.current.alive = false;
    pollRef.current = null;
    if (exitTimerRef.current !== null) {
      clearTimeout(exitTimerRef.current);
      exitTimerRef.current = null;
    }
  }, []);

  const load = useCallback(
    (opts: { detail: LensDetailLevel; refresh?: boolean }) => {
      stopPoll();
      setLoading(true);
      setError(null);
      // A refresh re-runs synthesis — clear the stale page so the progress
      // checklist (not the old prose) is what the user watches.
      if (opts.refresh) setPage(null);
      getLensPage(config, lens.id, { detail: opts.detail, refresh: opts.refresh })
        .then((result) => {
          // Clean cache hit → the materialized page. Otherwise the GET returned
          // a generation status (HTTP 202): show live progress and poll
          // `/page/status` until ready, never blocking the request on synthesis.
          if (!isLensGenStatus(result)) {
            setPage(result);
            setGen(null);
            setLoading(false);
            return;
          }
          setGen(result);
          const token = { alive: true };
          pollRef.current = token;
          const tick = () => {
            if (!token.alive) return;
            getLensPageStatus(config, lens.id)
              .then((s) => {
                if (!token.alive) return;
                setGen(s);
                if (s.status === "ready") {
                  // Page materialized — re-GET hits the cache (no synthesis).
                  getLensPage(config, lens.id, { detail: opts.detail })
                    .then((p) => {
                      if (!token.alive) return;
                      if (!isLensGenStatus(p)) {
                        setPage(p);
                        setGen(null);
                      }
                      setLoading(false);
                    })
                    .catch((e) => {
                      if (!token.alive) return;
                      setError(e instanceof Error ? e.message : String(e));
                      setLoading(false);
                    });
                } else if (s.status === "error") {
                  setError(s.error || "Lens generation failed.");
                  setLoading(false);
                } else {
                  window.setTimeout(tick, 700);
                }
              })
              .catch((e) => {
                if (!token.alive) return;
                setError(e instanceof Error ? e.message : String(e));
                setLoading(false);
              });
          };
          window.setTimeout(tick, 350);
        })
        .catch((e) => {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        });
    },
    [config, lens.id, stopPoll],
  );

  useEffect(() => {
    load({ detail });
    return stopPoll;
  }, [load, detail, stopPoll]);

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
          // let the exit animation play, then re-fetch the spine. Tracked so an
          // unmount (lens switch) within the window cancels it (see stopPoll).
          exitTimerRef.current = window.setTimeout(() => {
            exitTimerRef.current = null;
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

  const toggleGroup = useCallback(() => {
    const next = grouped ? "flat" : "grouped_by_subject";
    setGrouped(!grouped); // optimistic
    setLensRenderMode(config, lens.id, next)
      .then(() => load({ detail, refresh: true }))
      .catch((e) => {
        // Roll back the optimistic flip so the UI doesn't show a mode the server
        // never persisted (it would snap back on the next load anyway).
        setGrouped(grouped);
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [grouped, config, lens.id, load, detail]);

  return (
    <DetailShell
      header={
        <LensHeader
          lens={lens}
          onProvenance={onProvenance}
          onRefresh={() => load({ detail, refresh: true })}
          refreshing={loading}
          grouped={grouped}
          onToggleGroup={toggleGroup}
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

          {gen && !page ? (
            <GenerationProgress gen={gen} grouped={grouped} />
          ) : loading && !page ? (
            <PageSkeleton />
          ) : error ? (
            <div className="mt-4">
              <ListError title="Couldn't render page" message={error} />
            </div>
          ) : page && page.blocks.length === 0 ? (
            <Empty>Nothing matches this criterion yet. New memories appear here as they're admitted.</Empty>
          ) : page?.groups && page.groups.length > 1 ? (
            // Per-person cards only when there's genuinely more than one subject.
            // A single-subject "group" (e.g. a topic lens where everything is about
            // the user) renders flat — no pointless "the user" card.
            <GroupedProfiles
              groups={page.groups}
              editingId={editingId}
              busyId={busyId}
              exiting={exiting}
              onOpen={setEditingId}
              onClose={() => setEditingId(null)}
              onCommit={onClaimCommit}
              onPeek={onPeekClaim}
            />
          ) : page ? (
            <FlatPage
              page={page}
              editingId={editingId}
              busyId={busyId}
              exiting={exiting}
              onOpen={setEditingId}
              onClose={() => setEditingId(null)}
              onCommit={onClaimCommit}
              onPeek={onPeekClaim}
            />
          ) : null}

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
              if (window.confirm(`Delete the "${lensTitle(lens)}" view? Claims are untouched.`)) {
                void deleteLens(config, lens.id).then(onArchived);
              }
            }}
          >
            Delete view
          </GhostBtn>
        </>
      }
    />
  );
}

function LensHeader({
  lens,
  onProvenance,
  onRefresh,
  refreshing,
  grouped,
  onToggleGroup,
}: {
  lens: Lens;
  onProvenance: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  grouped: boolean;
  onToggleGroup: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-xl font-semibold tracking-[-0.012em] text-ink">
          <span aria-hidden className="size-2.5 rounded-full" style={{ backgroundColor: lensColor(lens) }} />
          <span className="truncate">{lensTitle(lens)}</span>
        </h2>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral" size="sm">
            {scopeLabel(lens.scope)}
          </Badge>
          <Badge tone={lensProvenanceTone(lens.provenance)} size="sm">
            {lensProvenanceLabel(lens.provenance)}
          </Badge>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <IconButton
          onClick={onToggleGroup}
          aria-label="Group by subject"
          aria-pressed={grouped}
          size="md"
          title={grouped ? "Grouping by subject" : "Group by subject"}
          className={grouped ? "text-accent" : undefined}
        >
          <Users size={ICON.SM} strokeWidth={2} />
        </IconButton>
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
  lens: Lens;
  coverage: CoverageAdvisory;
  editing: boolean;
  onEdit: () => void;
  onDone: (changed: boolean) => void;
}) {
  const [text, setText] = useState(lens.criterion);
  const [busy, setBusy] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      setText(lens.criterion);
      requestAnimationFrame(() => taRef.current?.focus());
    }
  }, [editing, lens.criterion]);

  // Grow to fit the criterion so it never clips while reading/editing.
  useEffect(() => {
    const el = taRef.current;
    if (!editing || !el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 280)}px`;
  }, [editing, text]);

  if (!editing) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onEdit}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onEdit();
          }
        }}
        title="Click to edit this lens definition"
        className="group/crit -mx-1 block w-full cursor-pointer rounded-md px-2 py-1.5 text-left transition-colors hover:bg-surface-soft/50"
      >
        {lens.criterion ? (
          <Markdown
            content={lens.criterion}
            className="text-sm leading-relaxed text-muted [&_h2]:mb-1 [&_h2]:mt-2 [&_h2]:text-xs [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-wide [&_h2]:text-faint [&_h2:first-child]:mt-0 [&_ul]:my-0.5 [&_li]:text-sm"
          />
        ) : (
          <span className="text-sm italic text-faint">
            No criterion — click to describe what this view collects.
          </span>
        )}
      </div>
    );
  }

  const dirty = text.trim() !== lens.criterion.trim() && text.trim().length > 0;
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
        rows={3}
        spellCheck={false}
        className="w-full resize-none overflow-y-auto bg-transparent text-sm leading-relaxed text-ink outline-none"
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
        {coverage.member_count} of {coverage.scope_pool} claims match
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

// ── Grouped-by-subject profiles ──────────────────────────────────────────────
// A grouped lens (e.g. "persons") renders one collapsible profile per subject,
// straight off the claim `canonical_subject` attribute. Expanding drills into the
// subject's underlying claims through the same ClaimBlock / peek wiring.

function GroupedProfiles({
  groups,
  editingId,
  busyId,
  exiting,
  onOpen,
  onClose,
  onCommit,
  onPeek,
}: {
  groups: ProjectedGroup[];
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(groups[0] ? [groups[0].subject] : []));
  const toggle = (subject: string) =>
    setOpen((cur) => {
      const next = new Set(cur);
      next.has(subject) ? next.delete(subject) : next.add(subject);
      return next;
    });

  return (
    <div className="mt-3 flex flex-col gap-1">
      {groups.map((g) => {
        const isOpen = open.has(g.subject);
        return (
          <div key={g.subject} className="rounded-lg">
            <button
              type="button"
              onClick={() => toggle(g.subject)}
              aria-expanded={isOpen}
              className="app-row group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left"
            >
              <ChevronRight
                size={ICON.SM}
                strokeWidth={2}
                className="shrink-0 text-faint transition-transform"
                style={{ transform: isOpen ? "rotate(90deg)" : undefined }}
              />
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{g.subject}</span>
              <Badge tone="neutral" size="sm" className="tabular-nums">
                {g.blocks.length}
              </Badge>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  layout
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={SPRING_LAYOUT}
                  className="overflow-hidden pl-6"
                >
                  <div className="flex flex-col gap-2 py-0.5">
                    {g.synthesized && stripAnchors(g.markdown).trim() && (
                      <Markdown
                        content={stripAnchors(g.markdown).trim()}
                        className="text-sm leading-relaxed"
                      />
                    )}
                    {g.blocks.length > 0 && (
                      <div className="mt-1 border-t border-line-soft/50 pt-1.5">
                        <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-faint">
                          {g.blocks.length === 1 ? "Source claim" : "Source claims"}
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <AnimatePresence initial={false}>
                            {g.blocks.map((b) => (
                              <ClaimBlock
                                key={b.claim_id}
                                block={b}
                                editing={editingId === b.claim_id}
                                busy={busyId === b.claim_id}
                                exiting={exiting?.id === b.claim_id ? exiting.how : null}
                                onOpen={() => onOpen(b.claim_id)}
                                onClose={onClose}
                                onCommit={onCommit}
                                onPeek={() => onPeek(b.claim_id)}
                              />
                            ))}
                          </AnimatePresence>
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

// The synthesized page carries deterministic `<!--claim:ID-->` anchors so the
// substrate can map prose back to claims on write-back. They're HTML comments —
// rehype-sanitize already drops them — but strip first so a partial/edge render
// never leaks the marker. The prose itself is the human reading surface (spec §5).
const CLAIM_ANCHOR = /<!--\s*claim:[^>]*-->/g;
function stripAnchors(md: string): string {
  return md.replace(CLAIM_ANCHOR, "");
}

// A flat (non-grouped) lens page. The synthesized markdown is the primary
// reading surface (Fork A: the page IS the editable projection); the claim
// blocks sit beneath as the evidence/drill-down + edit affordance. On a genuine
// synthesis failure (`synthesized === false`) there is no prose to show, so the
// blocks stand alone.
function FlatPage({
  page,
  editingId,
  busyId,
  exiting,
  onOpen,
  onClose,
  onCommit,
  onPeek,
}: {
  page: ProjectedPage;
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
}) {
  const prose = page.synthesized ? stripAnchors(page.markdown).trim() : "";
  return (
    <div className="mt-3 flex flex-col gap-3">
      {prose && <Markdown content={prose} className="text-sm leading-relaxed" />}
      <div className={prose ? "border-t border-line-soft/50 pt-2" : ""}>
        {prose && (
          <div className="mb-1 text-2xs font-medium uppercase tracking-wide text-faint">
            {page.blocks.length === 1 ? "Source claim" : "Source claims"}
          </div>
        )}
        <div className="flex flex-col gap-0.5">
          <AnimatePresence initial={false}>
            {page.blocks.map((b) => (
              <ClaimBlock
                key={b.claim_id}
                block={b}
                editing={editingId === b.claim_id}
                busy={busyId === b.claim_id}
                exiting={exiting?.id === b.claim_id ? exiting.how : null}
                onOpen={() => onOpen(b.claim_id)}
                onClose={onClose}
                onCommit={onCommit}
                onPeek={() => onPeek(b.claim_id)}
              />
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

// Live generation progress (ask: "i can't see what's happening when i create a
// lens"). The async page GET returns a status (HTTP 202) and the projector
// reports stage/subject/"i/n" through the poll target — surfaced here as an
// ordered checklist instead of a frozen spinner that times out.
const GEN_STEPS: { stage: "scoring" | "synthesizing"; label: string }[] = [
  { stage: "scoring", label: "Finding matching claims" },
  { stage: "synthesizing", label: "Writing the summary" },
];
const STAGE_ORDER: Record<string, number> = { creating: 0, scoring: 1, synthesizing: 2, ready: 3 };

function GenerationProgress({ gen, grouped }: { gen: LensGenStatus; grouped: boolean }) {
  const cur = STAGE_ORDER[gen.status] ?? 0;
  return (
    <div className="mt-4 flex flex-col gap-2.5">
      {/* Static title — the spinner lives on the active step only, so there are
          never two spinners competing ("Generating view" + "Scoring members"). */}
      <div className="flex items-center gap-2 text-sm font-medium text-ink">
        {gen.status === "error" && (
          <AlertCircle size={ICON.XS} strokeWidth={2.4} className="shrink-0 text-bad" />
        )}
        {gen.status === "error" ? "Couldn't build this view" : "Building this view…"}
      </div>
      <ul className="flex flex-col gap-1.5">
        {GEN_STEPS.map((step) => {
          const stepOrd = STAGE_ORDER[step.stage];
          const done = cur > stepOrd;
          const active = cur === stepOrd;
          const detail =
            active && step.stage === "synthesizing"
              ? [grouped && gen.subject, gen.progress].filter(Boolean).join(" · ")
              : "";
          return (
            <li key={step.stage} className="flex items-center gap-2 text-sm">
              <span className="flex size-4 shrink-0 items-center justify-center">
                {done ? (
                  <Check size={ICON.XS} strokeWidth={2.4} className="text-accent" />
                ) : active ? (
                  <Loader2 size={ICON.XS} strokeWidth={2.4} className="animate-spin text-accent" />
                ) : (
                  <span className="size-1.5 rounded-full bg-line" aria-hidden />
                )}
              </span>
              <span className={done || active ? "text-ink" : "text-faint"}>{step.label}</span>
              {detail && <span className="text-xs tabular-nums text-faint">{detail}</span>}
            </li>
          );
        })}
      </ul>
      {gen.status === "error" && gen.error && (
        <span className="text-xs text-bad">{gen.error}</span>
      )}
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
