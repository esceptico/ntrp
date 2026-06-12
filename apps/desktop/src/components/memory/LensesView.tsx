import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, Plus, RefreshCw, Search, Tag } from "lucide-react";
import type { AppConfig } from "../../api";
import {
  createLens,
  deleteLens,
  editLensCriterion,
  getLensPage,
  isLensGenStatus,
  listMemoryLenses,
  promoteLens,
  writebackLens,
  type CoverageAdvisory,
  type Lens,
  type LensDetailLevel,
  type LensWithCoverage,
  type PageEditOp,
  type ProjectedGroup,
  type ProjectedPage,
  type RenderedClaim,
} from "../../api/memoryItems";
import { Markdown } from "../Markdown";
import { EASE_OUT, MOTION, RISE_IN, RISE_SETTLED, SPRING_LAYOUT } from "../../lib/tokens/motion";
import { BlurSwap } from "../BlurSwap";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { Badge } from "../Badge";
import { ClaimBlock, type ClaimOp } from "./ClaimBlock";
import { LensEvidenceSearch } from "./LensEvidenceSearch";
import {
  DangerBtn,
  DetailPlaceholder,
  DetailShell,
  Empty,
  GhostBtn,
  ListError,
  PrimaryBtn,
  SearchInput,
} from "./shared";
import { criterionPreview, lensColor, lensTitle } from "./lens";

// Disclosure reveals: the layout snaps at mount/unmount, only the content
// rises into focus — never a height tween over these unbounded subtrees.
const REVEAL_IN = { ...RISE_IN, y: -4, filter: "blur(2px)" };
const REVEAL_ENTER = { duration: MOTION.row, ease: EASE_OUT };
const REVEAL_EXIT = {
  opacity: 0,
  filter: "blur(2px)",
  transition: { duration: MOTION.fast, ease: EASE_OUT },
};

export function LensesView({
  config,
  scope,
  onPeekClaim,
}: {
  config: AppConfig;
  scope: { kind: "user" | "project" | "session"; key: string | null } | null;
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
    listMemoryLenses(config, { scope_kind: scope?.kind, scope_key: scope?.key ?? undefined })
      .then((r) => {
        setLenses(r.lenses);
        setError(null);
        setSelectedId((cur) => cur ?? r.lenses[0]?.lens.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [config, scope?.kind, scope?.key]);

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
              initial={REVEAL_IN}
              animate={RISE_SETTLED}
              exit={REVEAL_EXIT}
              transition={REVEAL_ENTER}
              className="px-2.5"
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
            <span className="block truncate text-xs text-muted">{criterionPreview(lens.criterion)}</span>
          )}
        </span>
        <Badge tone={coverage.generic ? "warn" : "neutral"} size="sm" className="tabular-nums">
          {coverage.member_count}
        </Badge>
      </button>
    </li>
  );
}

// A lens is a saved query: name + plain-language criterion. Create is an
// INSERT only — membership derives the first time the view is opened.
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
  const [criterion, setCriterion] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const criterionRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  useEffect(() => {
    const el = criterionRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 280)}px`;
  }, [criterion]);

  const create = () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr(null);
    createLens(config, { name: name.trim(), criterion: criterion.trim() || undefined })
      .then((r) => onCreated(r.lens))
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  };

  return (
    <div className="surface-panel surface-popover mb-2 flex flex-col gap-2 p-2.5">
      <input
        ref={nameRef}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") criterionRef.current?.focus();
          if (e.key === "Escape") onCancel();
        }}
        placeholder="View name"
        spellCheck={false}
        className="input-field h-7 text-sm"
      />
      <textarea
        ref={criterionRef}
        value={criterion}
        onChange={(e) => setCriterion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) create();
          if (e.key === "Escape") onCancel();
        }}
        rows={2}
        placeholder="What belongs here, in plain language"
        spellCheck={false}
        className="input-field resize-none overflow-y-auto py-1.5 text-sm leading-relaxed"
      />
      {err && <span className="text-xs text-bad">{err}</span>}
      <div className="flex items-center justify-between">
        <span className="text-2xs text-faint">Saved instantly — evaluated when opened.</span>
        <div className="flex items-center gap-1">
          <GhostBtn onClick={onCancel} disabled={busy}>
            Cancel
          </GhostBtn>
          <PrimaryBtn onClick={create} disabled={busy || !name.trim()}>
            {busy ? "Saving…" : "Create"}
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
  const [page, setPage] = useState<ProjectedPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [exiting, setExiting] = useState<{ id: string; how: "supersede" | "reject" } | null>(null);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [editingCriterion, setEditingCriterion] = useState(false);
  // A single page-level evidence search; group headers bump `nonce` to open it
  // seeded with their subject (one live search, not one popover per group).
  const [evidenceSeed, setEvidenceSeed] = useState({ term: "", nonce: 0 });
  const findEvidenceFor = useCallback(
    (subject: string) => setEvidenceSeed((s) => ({ term: subject, nonce: s.nonce + 1 })),
    [],
  );
  // The actions strip cycles between rest, delete-confirm, and the inline
  // promote-to-label form (one BlurSwap, never stacked panels).
  const [actionMode, setActionMode] = useState<"rest" | "delete" | "promote">("rest");
  const [promoting, setPromoting] = useState(false);
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

  // Post-exit continuation for a write-back op: the removed claim row's exit
  // animation drives the re-fetch (ClaimSources fires onClaimExitDone).
  // Cleared on every load() so a reload within the exit window can't fire a
  // redundant fetch — and overwritten wholesale by back-to-back commits.
  const exitContinuationRef = useRef<(() => void) | null>(null);
  // False once this LensPage has unmounted (lens switch). applyOps awaits the
  // write-back before arming the exit continuation; if the user switches lenses
  // during that await, the continuation must not arm / load() on the dead page.
  const mountedRef = useRef(true);

  const onClaimExitDone = useCallback(() => {
    const continueAfterExit = exitContinuationRef.current;
    exitContinuationRef.current = null;
    continueAfterExit?.();
  }, []);

  const load = useCallback(
    (opts: { detail: LensDetailLevel; refresh?: boolean }) => {
      exitContinuationRef.current = null;
      setLoading(true);
      setError(null);
      // A refresh re-evaluates membership and re-synthesizes — clear the stale
      // page so the skeleton (not the old prose) is what the user watches.
      if (opts.refresh) setPage(null);
      getLensPage(config, lens.id, { detail: opts.detail, refresh: opts.refresh })
        .then((result) => {
          // Lens v2 evaluates on demand inside this GET — it always returns the
          // materialized page (the async 202 status shape is gone).
          if (isLensGenStatus(result)) return;
          setPage(result);
          // Fresh data in — release the exit hold (the removed claim is gone
          // from the page itself now, the filter must not linger).
          setExiting(null);
          setLoading(false);
        })
        .catch((e) => {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        });
    },
    [config, lens.id],
  );

  useEffect(() => {
    mountedRef.current = true;
    load({ detail });
    return () => {
      mountedRef.current = false;
      exitContinuationRef.current = null;
    };
  }, [load, detail]);

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
          // Removing the block from ClaimSources plays its exit; the popLayout
          // AnimatePresence then fires onClaimExitDone, which runs this.
          setExiting(hint);
          exitContinuationRef.current = () => {
            load({ detail, refresh: res.rederive_triggered });
            onListChanged();
          };
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

  // Graduate the lens into a label: the server evaluates fresh and tags every
  // member; thereafter the curator tags new records (the label is in vocabulary).
  const doPromote = (label: string) => {
    setPromoting(true);
    promoteLens(config, lens.id, label)
      .then((r) => {
        if (!mountedRef.current) return;
        setActionMode("rest");
        setRunNote(`promoted — ${r.promoted} record${r.promoted === 1 ? "" : "s"} labeled ${r.label}`);
        onListChanged();
      })
      .catch((e) => {
        if (mountedRef.current) setRunNote(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (mountedRef.current) setPromoting(false);
      });
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

          {loading && !page ? (
            <PageSkeleton />
          ) : error ? (
            <div className="mt-4">
              <ListError title="Couldn't render page" message={error} />
            </div>
          ) : page && page.blocks.length === 0 ? (
            <Empty>Nothing matches this criterion yet. Re-evaluate once new memories land.</Empty>
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
              onFindEvidence={findEvidenceFor}
              onExitDone={onClaimExitDone}
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
              onExitDone={onClaimExitDone}
            />
          ) : null}

          <div className="mt-4 border-t border-line-soft/40 pt-1">
            <LensEvidenceSearch
              config={config}
              lens={lens}
              memberIds={memberIds}
              seed={evidenceSeed}
              onEditCriterion={() => setEditingCriterion(true)}
              onPeekClaim={onPeekClaim}
              onRefresh={() => load({ detail, refresh: true })}
            />
          </div>
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
                exit={{ opacity: 0, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
                transition={{ duration: MOTION.row, ease: EASE_OUT }}
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
          <BlurSwap swapKey={actionMode} blur={3}>
            {actionMode === "delete" ? (
              // In-app confirm instead of the off-brand native window.confirm.
              <div className="flex items-center gap-2">
                <span className="text-xs text-faint">Delete this view? Records are untouched.</span>
                <GhostBtn onClick={() => setActionMode("rest")}>Cancel</GhostBtn>
                <DangerBtn
                  onClick={() => {
                    setActionMode("rest");
                    void deleteLens(config, lens.id)
                      .then(onArchived)
                      .catch((e) => {
                        // Surface a failed delete instead of swallowing it (the lens
                        // stays open) — matches the component's setError pattern.
                        if (!mountedRef.current) return;
                        setError(e instanceof Error ? e.message : String(e));
                      });
                  }}
                >
                  Delete view
                </DangerBtn>
              </div>
            ) : actionMode === "promote" ? (
              <PromoteForm
                initial={lens.name}
                busy={promoting}
                onCancel={() => setActionMode("rest")}
                onSubmit={doPromote}
              />
            ) : (
              <div className="flex items-center gap-2">
                {!lens.promoted_to && (
                  <GhostBtn
                    onClick={() => setActionMode("promote")}
                    title="Graduate this view into a label — every member gets tagged"
                  >
                    Promote to label
                  </GhostBtn>
                )}
                <GhostBtn onClick={() => setEditingCriterion(true)}>Edit criterion</GhostBtn>
                <GhostBtn onClick={() => setActionMode("delete")}>Delete view</GhostBtn>
              </div>
            )}
          </BlurSwap>
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
        {lens.promoted_to && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge
              tone="accent"
              size="sm"
              leading={<Tag size={ICON.XS} strokeWidth={2} />}
              title="Promoted — members carry this label; the curator tags new records"
            >
              {lens.promoted_to}
            </Badge>
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <IconButton onClick={onRefresh} aria-label="Re-evaluate" size="md" title="Re-evaluate this view (LLM)">
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
            <span className="mr-1.5 text-2xs font-semibold uppercase tracking-wide text-muted">
              Collects
            </span>
            {criterionPreview(lens.criterion)}
          </span>
        ) : (
          <span className="text-sm italic text-muted">
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
    <div className="surface-panel surface-popover my-1 p-2.5">
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
  return (
    <div className={compact ? "h-1 w-16 overflow-hidden rounded-full bg-surface-sunken" : "h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken"}>
      <motion.div
        initial={false}
        animate={{ scaleX: Math.min(1, coverage.ratio) }}
        transition={SPRING_LAYOUT}
        style={{ originX: 0 }}
        className={coverage.generic ? "h-full w-full rounded-full bg-warn" : "h-full w-full rounded-full bg-accent"}
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
  onFindEvidence,
  onExitDone,
}: {
  groups: ProjectedGroup[];
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
  onFindEvidence?: (subject: string) => void;
  onExitDone: () => void;
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
              <motion.span
                className="inline-flex shrink-0 text-faint"
                animate={{ rotate: isOpen ? 90 : 0 }}
                transition={SPRING_LAYOUT}
              >
                <ChevronRight size={ICON.SM} strokeWidth={2} />
              </motion.span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{g.subject}</span>
              <Badge tone="neutral" size="sm" className="tabular-nums">
                {g.blocks.length}
              </Badge>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={REVEAL_IN}
                  animate={RISE_SETTLED}
                  exit={REVEAL_EXIT}
                  transition={REVEAL_ENTER}
                  className="pl-6"
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
                      onExitDone={onExitDone}
                    />
                    {onFindEvidence && (
                      <button
                        type="button"
                        onClick={() => onFindEvidence(g.subject)}
                        className="inline-flex items-center gap-1.5 self-start rounded-md px-1.5 py-1 text-xs font-medium text-faint transition-colors hover:bg-surface-soft hover:text-muted"
                      >
                        <Search size={ICON.XS} strokeWidth={2} />
                        Find evidence for {g.subject}
                      </button>
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

function ClaimSources({
  blocks,
  editingId,
  busyId,
  exiting,
  onOpen,
  onClose,
  onCommit,
  onPeek,
  onExitDone,
}: {
  blocks: RenderedClaim[];
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
  /** Fires when a removed claim row finishes its exit animation. */
  onExitDone: () => void;
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
        <motion.span
          className="inline-flex"
          animate={{ rotate: open ? 90 : 0 }}
          transition={SPRING_LAYOUT}
        >
          <ChevronRight size={ICON.XS} strokeWidth={2} />
        </motion.span>
        Sources
        <Badge tone="neutral" size="sm" className="tabular-nums">
          {blocks.length}
        </Badge>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={REVEAL_IN}
            animate={RISE_SETTLED}
            exit={REVEAL_EXIT}
            transition={REVEAL_ENTER}
            // relative: the wrapper's animated filter makes it the containing
            // block for popLayout's absolutely-positioned exit rows — position
            // it so offset measurements resolve against the same box.
            className="relative mt-1 flex flex-col gap-0.5"
          >
            {/* A committed write-back removes its block here; `custom` carries the
                op direction to the already-removed row's exit variant. */}
            <AnimatePresence
              mode="popLayout"
              initial={false}
              custom={exiting?.how ?? null}
              onExitComplete={onExitDone}
            >
              {blocks
                .filter((b) => b.claim_id !== exiting?.id)
                .map((b) => (
                  <ClaimBlock
                    key={b.claim_id}
                    block={b}
                    editing={editingId === b.claim_id}
                    busy={busyId === b.claim_id}
                    onOpen={() => onOpen(b.claim_id)}
                    onClose={onClose}
                    onCommit={onCommit}
                    onPeek={() => onPeek(b.claim_id)}
                  />
                ))}
            </AnimatePresence>
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
  onExitDone,
}: {
  page: ProjectedPage;
  editingId: string | null;
  busyId: string | null;
  exiting: { id: string; how: "supersede" | "reject" } | null;
  onOpen: (id: string) => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  onPeek: (claimId: string) => void;
  onExitDone: () => void;
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
        onExitDone={onExitDone}
      />
    </div>
  );
}

// Evaluation happens inside the page GET (recall → one membership call →
// synthesis), so a first open can take a while — caption the skeleton so it
// reads as work, not a hang.
function PageSkeleton() {
  return (
    <div className="mt-4 flex flex-col gap-2">
      <div className="mb-1 text-sm italic text-muted">Evaluating this view against memory…</div>
      {[92, 78, 85, 64, 88].map((w, i) => (
        <div key={i} className="skeleton h-4 rounded" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

// Inline promote-to-label form living in the actions strip: name the label
// (prefilled with the lens name), confirm, and the view graduates.
function PromoteForm({
  initial,
  busy,
  onCancel,
  onSubmit,
}: {
  initial: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (label: string) => void;
}) {
  const [label, setLabel] = useState(initial);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const valid = label.trim().length > 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-faint">Tag every member with</span>
      <input
        ref={inputRef}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && valid && !busy) onSubmit(label.trim());
          if (e.key === "Escape") onCancel();
        }}
        placeholder="Label"
        spellCheck={false}
        className="input-field h-7 w-44 text-sm"
      />
      <GhostBtn onClick={onCancel} disabled={busy}>
        Cancel
      </GhostBtn>
      <PrimaryBtn onClick={() => onSubmit(label.trim())} disabled={busy || !valid}>
        {busy ? "Promoting…" : "Promote"}
      </PrimaryBtn>
    </div>
  );
}
