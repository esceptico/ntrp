import { useEffect, useMemo, useRef, useState } from "react";
import { Archive, ArchiveRestore, ChevronDown, ExternalLink, GitCompareArrows, Pencil, Pin } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type Fact,
  type FactDetail as ApiFactDetail,
  type FactKind,
  type FactStatus,
  type LinkedFact,
  getFactApi,
  listFactsApi,
  supersedeFactApi,
  updateFactMetadataApi,
  updateFactTextApi,
} from "../../api";
import { useMountedRef, useMutationState } from "../../lib/hooks";
import { formatAbs, formatRelativePast } from "../../lib/format";
import {
  factChatSourceFocus,
  factSourceDetail,
  factSourceLabel,
  factSourceStatus,
  type FactChatSourceFocus,
} from "../../lib/memoryProvenance";
import { type MemoryTarget, upsertById } from "../../lib/memoryTargets";
import { factStatusFilterLabel, factStatusLabel, factStatusTone } from "../../lib/memoryTrust";
import {
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

const FACT_STATUSES: FactStatus[] = ["active", "all", "archived", "superseded", "expired", "temporary", "pinned"];

function statusFilterForFact(fact: Fact): FactStatus {
  if (fact.status === "archived" || fact.status === "superseded" || fact.status === "expired") return fact.status;
  return "active";
}

export function FactsPane({
  targetFact,
  onOpenSource,
}: {
  targetFact?: MemoryTarget<Fact | number> | null;
  onOpenSource?: (focus: FactChatSourceFocus) => void;
}) {
  const config = useStore((s) => s.config);
  const [facts, setFacts] = useState<Fact[] | null>(null);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<FactKind | null>(null);
  const [status, setStatus] = useState<FactStatus>("active");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [targetHighlightId, setTargetHighlightId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ApiFactDetail | null>(null);

  async function refresh(nextStatus = status) {
    const r = await listFactsApi(config, { limit: 200, kind: kind ?? undefined, status: nextStatus });
    setFacts(r.facts);
    setTotal(r.total);
  }

  async function openFactById(factId: number) {
    const next = await getFactApi(config, factId);
    setFacts((prev) => upsertById(prev, next.fact));
    setDetail(next);
    setSelectedId(next.fact.id);
    setTargetHighlightId(next.fact.id);
    setQuery("");
    setKind(null);
    setStatus(statusFilterForFact(next.fact));
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, status]);

  useEffect(() => {
    if (!targetFact) return;
    const targetItem = targetFact.item;
    if (typeof targetItem === "number") {
      void openFactById(targetItem);
      return;
    }
    const fact = targetItem;
    setFacts((prev) => upsertById(prev, fact));
    setSelectedId(fact.id);
    setTargetHighlightId(fact.id);
    setQuery("");
    setKind(null);
    setStatus(statusFilterForFact(fact));
  }, [targetFact?.nonce]);

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    void getFactApi(config, selectedId).then((next) => {
      if (!cancelled) setDetail(next);
    });
    return () => {
      cancelled = true;
    };
  }, [config, selectedId]);

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
              <StatusFilter value={status} onChange={setStatus} />
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
              highlighted={f.id === targetHighlightId}
              onSelect={() => {
                setSelectedId(f.id);
                setTargetHighlightId(null);
              }}
            />
          )}
        />
      }
      detail={
        selected ? (
          <FactDetail
            key={selected.id}
            fact={detail?.fact.id === selected.id ? detail.fact : selected}
            linkedFacts={detail?.fact.id === selected.id ? detail.linked_facts : []}
            onSaved={refresh}
            onOpenFact={(factId) => void openFactById(factId)}
            onOpenSource={onOpenSource}
            onSuperseded={async (oldFact, newFact) => {
              setStatus("active");
              setQuery("");
              setFacts((prev) => {
                const existing = prev ?? [];
                return [
                  newFact,
                  ...existing.filter((fact) => fact.id !== oldFact.id && fact.id !== newFact.id),
                ];
              });
              setSelectedId(newFact.id);
            }}
            onArchived={async (archived) => {
              const nextStatus = archived ? "archived" : "active";
              setStatus(nextStatus);
              await refresh(nextStatus);
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
  highlighted,
  onSelect,
}: {
  fact: Fact;
  selected: boolean;
  highlighted: boolean;
  onSelect: () => void;
}) {
  const sourceStatus = factSourceStatus(fact);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "w-full text-left px-4 py-2.5 transition-[background-color,color,box-shadow] rounded-md",
        selected ? "bg-surface-soft text-ink" : "hover:bg-surface-soft/50 text-ink-soft",
        highlighted && "bg-accent-soft/50 shadow-[inset_0_0_0_1px_var(--color-accent-strong)]",
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
            <span>{factSourceLabel(fact)}</span>
            {sourceStatus.tone === "warn" && (
              <>
                <span aria-hidden>·</span>
                <Pill tone="warn">source</Pill>
              </>
            )}
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
  linkedFacts,
  onSaved,
  onOpenFact,
  onOpenSource,
  onSuperseded,
  onArchived,
}: {
  fact: Fact;
  linkedFacts: LinkedFact[];
  onSaved: () => Promise<void>;
  onOpenFact: (factId: number) => void;
  onOpenSource?: (focus: FactChatSourceFocus) => void;
  onSuperseded: (oldFact: Fact, newFact: Fact) => Promise<void>;
  onArchived: (archived: boolean) => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const [mode, setMode] = useState<"edit" | "correct" | null>(null);
  const [draft, setDraft] = useState(fact.text);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  useEffect(() => {
    setMode(null);
    setDraft(fact.text);
  }, [fact.id, fact.text]);

  const dirty = mode !== null && draft.trim() !== fact.text.trim();
  const sourceRef = factSourceDetail(fact);
  const sourceFocus = factChatSourceFocus(fact);
  const sourceStatus = factSourceStatus(fact);

  async function save() {
    if (!dirty || !draft.trim()) return;
    await run(async () => {
      await updateFactTextApi(config, fact.id, draft.trim());
      await onSaved();
      if (mounted.current) setMode(null);
    });
  }

  async function supersede() {
    if (!dirty || !draft.trim()) return;
    await run(async () => {
      const result = await supersedeFactApi(config, fact.id, draft.trim());
      await onSuperseded(result.old_fact, result.new_fact);
      if (mounted.current) setMode(null);
    });
  }

  async function setArchived(archived: boolean) {
    await run(async () => {
      await updateFactMetadataApi(config, fact.id, { archived });
      await onArchived(archived);
    });
  }

  return (
    <DetailShell
      header={
        <DetailMeta>
          <Pill tone={factStatusTone(fact.status)}>{factStatusLabel(fact.status)}</Pill>
          <Pill tone={sourceStatus.tone}>{sourceStatus.label}</Pill>
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
        mode !== null ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                void (mode === "correct" ? supersede() : save());
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
        <div className="flex flex-col gap-6">
          <MetaGrid
            rows={[
              { label: "Created", value: formatAbs(fact.created_at) },
              fact.happened_at ? { label: "Happened", value: formatAbs(fact.happened_at) } : null,
              fact.valid_from ? { label: "Valid from", value: formatAbs(fact.valid_from) } : null,
              fact.valid_until ? { label: "Valid until", value: formatAbs(fact.valid_until) } : null,
              { label: "Last accessed", value: formatAbs(fact.last_accessed_at) },
              { label: "Access count", value: String(fact.access_count) },
              { label: "Source", value: factSourceLabel(fact) },
              sourceRef ? { label: "Reference", value: sourceRef, mono: true } : null,
              fact.expires_at ? { label: "Expires", value: formatAbs(fact.expires_at) } : null,
            ]}
          />
          <FactLinks links={linkedFacts} onOpenFact={onOpenFact} />
        </div>
      }
      actions={
        <>
          {error && <ErrorPill message={error} />}
          {mode !== null ? (
            <>
              <GhostBtn
                onClick={() => {
                  setMode(null);
                  setDraft(fact.text);
                }}
                disabled={busy}
              >
                Cancel
              </GhostBtn>
              <PrimaryBtn
                onClick={() => void (mode === "correct" ? supersede() : save())}
                disabled={!dirty || busy || !draft.trim()}
              >
                {busy ? "Saving…" : mode === "correct" ? "Create replacement" : "Save changes"}
              </PrimaryBtn>
            </>
          ) : (
            <>
              {sourceFocus && (
                <GhostBtn onClick={() => onOpenSource?.(sourceFocus)} disabled={busy}>
                  <ExternalLink size={12} strokeWidth={1.8} /> Open source
                </GhostBtn>
              )}
              {fact.status === "archived" ? (
                <GhostBtn onClick={() => void setArchived(false)} disabled={busy}>
                  <ArchiveRestore size={12} strokeWidth={1.8} /> Restore
                </GhostBtn>
              ) : (
                <GhostBtn onClick={() => void setArchived(true)} disabled={busy}>
                  <Archive size={12} strokeWidth={1.8} /> Archive
                </GhostBtn>
              )}
              <GhostBtn onClick={() => setMode("correct")} disabled={busy || fact.status === "superseded"}>
                <GitCompareArrows size={12} strokeWidth={1.8} /> Replace claim
              </GhostBtn>
              <GhostBtn onClick={() => setMode("edit")} disabled={busy}>
                <Pencil size={12} strokeWidth={1.8} /> Fix typo
              </GhostBtn>
            </>
          )}
        </>
      }
    />
  );
}

function FactLinks({ links, onOpenFact }: { links: LinkedFact[]; onOpenFact: (factId: number) => void }) {
  if (links.length === 0) return null;
  return (
    <section>
      <h3 className="m-0 mb-3 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">
        Fact links
      </h3>
      <ul className="flex flex-col gap-2">
        {links.map((link) => (
          <li key={`${link.link_type}-${link.id}`} className="flex items-start gap-3">
            <span className="mt-[2px] text-[10px] uppercase tracking-[0.06em] text-faint shrink-0 w-[96px]">
              {link.link_type === "superseded_by" ? "replaced by" : "replaces"}
            </span>
            <button
              type="button"
              onClick={() => onOpenFact(link.id)}
              className="min-w-0 text-left text-[12.5px] leading-snug text-ink-soft hover:text-ink"
            >
              {link.text}
            </button>
          </li>
        ))}
      </ul>
    </section>
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

function StatusFilter({
  value,
  onChange,
}: {
  value: FactStatus;
  onChange: (v: FactStatus) => void;
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
          value !== "active"
            ? "bg-ink text-on-ink"
            : "text-ink-soft bg-[rgba(0,0,0,0.04)] hover:bg-[rgba(0,0,0,0.06)]",
        )}
      >
        <span>{factStatusFilterLabel(value)}</span>
        <ChevronDown size={11} strokeWidth={1.8} className="opacity-70" />
      </button>
      {open && (
        <div className="absolute top-full mt-1 right-0 z-10 w-[150px] py-1 rounded-[10px] border border-line-soft bg-surface shadow-[var(--shadow-pop)]">
          {FACT_STATUSES.map((s) => (
            <KindOption
              key={s}
              label={factStatusFilterLabel(s)}
              active={value === s}
              onClick={() => {
                onChange(s);
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
