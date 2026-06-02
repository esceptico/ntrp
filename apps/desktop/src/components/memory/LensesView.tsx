import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, Check, ChevronRight, Loader2, Plus, RefreshCw } from "lucide-react";
import type { AppConfig } from "../../api";
import {
  createLens,
  deleteLens,
  draftLens,
  editLensCriterion,
  getLensPage,
  getLensPageStatus,
  isLensGenStatus,
  listMemoryLenses,
  writebackLens,
  type CoverageAdvisory,
  type Lens,
  type LensDetailLevel,
  type LensGenStatus,
  type LensWithCoverage,
  type PageEditOp,
  type ProjectedGroup,
  type ProjectedPage,
  type RenderedClaim,
} from "../../api/memoryItems";
import { Markdown } from "../Markdown";
import { SPRING_LAYOUT } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { Badge } from "../Badge";
import { ClaimBlock, type ClaimOp } from "./ClaimBlock";
import { LensEvidenceSearch } from "./LensEvidenceSearch";
import {
  DetailPlaceholder,
  DetailShell,
  Empty,
  GhostBtn,
  ListError,
  PrimaryBtn,
  SearchInput,
} from "./shared";
import { criterionPreview, lensColor, lensProvenanceLabel, lensProvenanceTone, lensTitle, scopeLabel } from "./lens";


export function LensesView({
  config,
  onPeekClaim,
}: {
  config: AppConfig;
  onPeekClaim: (claimId: string) => void;
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
            <span className="block truncate text-xs text-faint">{criterionPreview(lens.criterion)}</span>
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
  const [name, setName] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [phase, setPhase] = useState<"seed" | "draft">("seed");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const markdownRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  useEffect(() => {
    const el = markdownRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 420)}px`;
  }, [markdown]);

  const makeDraft = () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr(null);
    draftLens(config, { name: name.trim() })
      .then((r) => {
        setMarkdown(r.markdown);
        setPhase("draft");
        setBusy(false);
        requestAnimationFrame(() => markdownRef.current?.focus());
      })
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  };

  const approve = () => {
    const definition = markdown.trim();
    if (!definition || busy) return;
    setBusy(true);
    setErr(null);
    createLens(config, { definition_markdown: definition })
      .then((r) => onCreated(r.lens))
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  };

  if (phase === "seed") {
    return (
      <div className="glass-surface surface-popover mb-2 flex flex-col gap-2 p-2.5">
        <input
          ref={nameRef}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") makeDraft();
            if (e.key === "Escape") onCancel();
          }}
          placeholder="Lens seed"
          spellCheck={false}
          className="input-field h-7 text-sm"
        />
        {err && <span className="text-xs text-bad">{err}</span>}
        <div className="flex items-center justify-between">
          <span className="text-2xs text-faint">Drafts an editable lens file.</span>
          <div className="flex items-center gap-1">
            <GhostBtn onClick={onCancel} disabled={busy}>
              Cancel
            </GhostBtn>
            <PrimaryBtn onClick={makeDraft} disabled={busy || !name.trim()}>
              {busy ? "Drafting…" : "Draft"}
            </PrimaryBtn>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-surface surface-popover mb-2 flex flex-col gap-2 p-2.5">
      <textarea
        ref={markdownRef}
        value={markdown}
        onChange={(e) => setMarkdown(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) approve();
        }}
        rows={12}
        spellCheck={false}
        className="input-field resize-none overflow-y-auto py-1.5 font-mono text-xs leading-relaxed"
      />
      {err && <span className="text-xs text-bad">{err}</span>}
      <div className="flex items-center justify-between">
        <span className="text-2xs text-faint">Approve writes the lens.</span>
        <div className="flex items-center gap-1">
          <GhostBtn onClick={onCancel} disabled={busy}>
            Cancel
          </GhostBtn>
          <PrimaryBtn onClick={approve} disabled={busy || !markdown.trim()}>
            {busy ? "Saving…" : "Approve"}
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
  onListChanged,
  onArchived,
}: {
  config: AppConfig;
  lens: Lens;
  coverage: CoverageAdvisory;
  onPeekClaim: (claimId: string) => void;
  onListChanged: () => void;
  onArchived: () => void;
}) {
  // Detail level is fixed to the lens's own setting — no user-facing toggle.
  const detail = lens.detail_level;
  const grouped = lens.render_mode === "grouped_by_subject";
  const [page, setPage] = useState<ProjectedPage | null>(null);
  const [gen, setGen] = useState<LensGenStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [exiting, setExiting] = useState<{ id: string; how: "supersede" | "reject" } | null>(null);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [editingCriterion, setEditingCriterion] = useState(false);
  const memberIds = useMemo(() => {
    const ids = new Set<string>();
    if (!page) return ids;
    const blocks = page.groups?.flatMap((g) => g.blocks) ?? page.blocks;
    for (const block of blocks) ids.add(block.claim_id);
    return ids;
  }, [page]);

  // Auto-dismiss the write-back result note so it doesn't linger permanently in
  // the meta bar after the user has moved on (it was only ever replaced, never cleared).
  useEffect(() => {
    if (!runNote) return;
    const t = window.setTimeout(() => setRunNote(null), 4000);
    return () => clearTimeout(t);
  }, [runNote]);

  // A generation poll in flight — cancelled on unmount/reload so a stale loop
  // never writes into a remounted page (lens switch keys remount LensPage).
  const pollRef = useRef<{ alive: boolean } | null>(null);
  // Exit-animation timer for a write-back op; tracked so a lens switch within the
  // 240ms window can't fire load()/re-arm a poll on the unmounted page.
  const exitTimerRef = useRef<number | null>(null);
  // False once this LensPage has unmounted (lens switch). applyOps awaits the
  // write-back before arming the exit timer; if the user switches lenses during
  // that await, the continuation must not arm a timer / load() on the dead page.
  const mountedRef = useRef(true);

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
                        setLoading(false);
                      } else {
                        // "ready" but the re-GET still returned a status — don't
                        // dead-end on a frozen checklist; keep polling.
                        setGen(p);
                        window.setTimeout(tick, 700);
                      }
                    })
                    .catch((e) => {
                      if (!token.alive) return;
                      // Clear gen so the error branch renders — the `gen && !page`
                      // guard would otherwise keep a frozen progress checklist up.
                      setGen(null);
                      setError(e instanceof Error ? e.message : String(e));
                      setLoading(false);
                    });
                } else if (s.status === "error") {
                  setGen(null);
                  setError(s.error || "Lens generation failed.");
                  setLoading(false);
                } else {
                  window.setTimeout(tick, 700);
                }
              })
              .catch((e) => {
                if (!token.alive) return;
                setGen(null);
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
    mountedRef.current = true;
    load({ detail });
    return () => {
      mountedRef.current = false;
      stopPoll();
    };
  }, [load, detail, stopPoll]);

  const applyOps = useCallback(
    async (ops: PageEditOp[], hint: { id: string; how: "supersede" | "reject" } | null) => {
      const opId = hint?.id ?? "lens";
      setBusyId(opId);
      try {
        const res = await writebackLens(config, lens.id, ops);
        // Lens switched during the await → this page is unmounted; don't arm a
        // timer or trigger load()/onListChanged() against the dead instance.
        if (!mountedRef.current) return;
        const parts: string[] = [];
        if (res.applied.length) parts.push(`${res.applied.length} applied`);
        if (res.rejected.length) parts.push(`${res.rejected.length} rejected`);
        setRunNote(parts.join(" · ") || "no change");
        if (hint && res.applied.length) {
          setExiting(hint);
          // let the exit animation play, then re-fetch the spine. Tracked so an
          // unmount (lens switch) within the window cancels it (see stopPoll).
          // Cancel any prior pending timer first: back-to-back commits within the
          // 240ms window would otherwise orphan it into a redundant re-fetch.
          if (exitTimerRef.current !== null) clearTimeout(exitTimerRef.current);
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
          ) : page?.groups && page.groups.length > 0 ? (
            // Directory-style lenses render as list/profile rows from generated
            // `## Name` sections. Even one row should still feel like a list item,
            // not collapse back into one large markdown note.
            <GroupedProfiles
              groups={page.groups}
              editingId={editingId}
              busyId={busyId}
              exiting={exiting}
              onOpen={setEditingId}
              onClose={() => setEditingId(null)}
              onCommit={onClaimCommit}
              onPeek={onPeekClaim}
              evidenceSearch={(subject) => (
                <LensEvidenceSearch
                  config={config}
                  lens={lens}
                  subject={subject}
                  memberIds={memberIds}
                  onEditCriterion={() => setEditingCriterion(true)}
                  onPeekClaim={onPeekClaim}
                  onRefresh={() => load({ detail, refresh: true })}
                />
              )}
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

          <LensEvidenceSearch
            config={config}
            lens={lens}
            memberIds={memberIds}
            onEditCriterion={() => setEditingCriterion(true)}
            onPeekClaim={onPeekClaim}
            onRefresh={() => load({ detail, refresh: true })}
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
                void deleteLens(config, lens.id)
                  .then(onArchived)
                  .catch((e) => {
                    // Surface a failed delete instead of swallowing it (the lens
                    // stays open) — matches the component's setError pattern.
                    if (!mountedRef.current) return;
                    setError(e instanceof Error ? e.message : String(e));
                  });
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

export function LensHeader({
  lens,
  onRefresh,
  refreshing,
}: {
  lens: Lens;
  onRefresh: () => void;
  refreshing: boolean;
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
  const [err, setErr] = useState<string | null>(null);
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
          // Compact one-line definition, not the full ## Belongs / ## Profile shape
          // markdown wall — the synthesized page below is the content, not this.
          // Click reveals the full editable criterion.
          <span className="block text-sm leading-relaxed text-muted">
            <span className="mr-1.5 text-2xs font-semibold uppercase tracking-wide text-faint">
              Collects
            </span>
            {criterionPreview(lens.criterion)}
          </span>
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
    setErr(null);
    editLensCriterion(config, lens.id, text.trim())
      .then(() => onDone(true))
      // Don't treat a failed save like a cancel — keep edit mode open and surface
      // the error so the user knows the criterion was NOT persisted, and can retry.
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
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
      {err && <div className="mt-1.5 text-xs text-bad">Couldn’t save: {err}</div>}
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

// ── Lens profile rows ────────────────────────────────────────────────────────
// A grouped lens uses claim `canonical_subject`; a flat directory-style lens uses
// synthesized `## Name` sections. Both drill into the row's backing claims here.

export function GroupedProfiles({
  groups,
  editingId,
  busyId,
  exiting,
  onOpen,
  onClose,
  onCommit,
  onPeek,
  evidenceSearch,
}: {
  groups: ProjectedGroup[];
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
  evidenceSearch?: (subject: string) => React.ReactNode;
}) {
  // Key collapse state by a stable per-group id, not the raw subject string: two
  // groups can legitimately share a subject (cached re-read), and a subject-keyed
  // Set would toggle both at once.
  const groupId = (i: number) => `${groups[i].subject}#${i}`;
  const [open, setOpen] = useState<Set<string>>(() => new Set(groups[0] ? [`${groups[0].subject}#0`] : []));
  const toggle = (id: string) =>
    setOpen((cur) => {
      const next = new Set(cur);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className="mt-3 flex flex-col gap-1">
      {groups.map((g, i) => {
        const id = groupId(i);
        const isOpen = open.has(id);
        return (
          <div key={id} className="rounded-lg">
            <button
              type="button"
              onClick={() => toggle(id)}
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
                    <ClaimSources
                      blocks={g.blocks}
                      editingId={editingId}
                      busyId={busyId}
                      exiting={exiting}
                      onOpen={onOpen}
                      onClose={onClose}
                      onCommit={onCommit}
                      onPeek={onPeek}
                    />
                    {evidenceSearch?.(g.subject)}
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

function ClaimSources({
  blocks,
  editingId,
  busyId,
  exiting,
  onOpen,
  onClose,
  onCommit,
  onPeek,
}: {
  blocks: RenderedClaim[];
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  if (blocks.length === 0) return null;
  return (
    <div className="mt-1 border-t border-line-soft/50 pt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-faint transition-colors hover:bg-surface-soft hover:text-muted"
      >
        <ChevronRight
          size={ICON.XS}
          strokeWidth={2}
          className="transition-transform"
          style={{ transform: open ? "rotate(90deg)" : undefined }}
        />
        Sources
        <Badge tone="neutral" size="sm" className="tabular-nums">
          {blocks.length}
        </Badge>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            layout
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={SPRING_LAYOUT}
            className="overflow-hidden"
          >
            <div className="mt-1 flex flex-col gap-0.5">
              {blocks.map((b) => (
                <ClaimBlock
                  key={b.claim_id}
                  block={b}
                  editing={editingId === b.claim_id}
                  busy={busyId === b.claim_id}
                  exiting={exiting && exiting.id === b.claim_id ? exiting.how : null}
                  onOpen={() => onOpen(b.claim_id)}
                  onClose={onClose}
                  onCommit={onCommit}
                  onPeek={() => onPeek(b.claim_id)}
                />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
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
      <ClaimSources
        blocks={page.blocks}
        editingId={editingId}
        busyId={busyId}
        exiting={exiting}
        onOpen={onOpen}
        onClose={onClose}
        onCommit={onCommit}
        onPeek={onPeek}
      />
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
