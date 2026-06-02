import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import type { AppConfig } from "../../api";
import {
  searchMemory,
  type Lens,
  type MemoryItem,
} from "../../api/memoryItems";
import { ICON } from "../../lib/icons";
import { Badge } from "../Badge";
import { GhostBtn, PrimaryBtn } from "./shared";

interface LensEvidenceSearchProps {
  config: AppConfig;
  lens: Lens;
  subject?: string;
  memberIds: Set<string>;
  onEditCriterion: () => void;
  onPeekClaim: (claimId: string) => void;
  onRefresh: () => void;
}

export function LensEvidenceSearch({
  config,
  lens,
  subject,
  memberIds,
  onEditCriterion,
  onPeekClaim,
  onRefresh,
}: LensEvidenceSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(initialQuery(subject, lens.name));
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryRef = useRef(query);
  const requestSeq = useRef(0);
  const mounted = useRef(true);
  const label = subject ? "Find evidence" : "Find entries";

  useEffect(() => {
    queryRef.current = query;
  }, [query]);

  useEffect(() => {
    return () => {
      mounted.current = false;
    };
  }, []);

  const candidates = useMemo(() => {
    if (subject) return items.map((item) => ({ item, count: 1, inView: memberIds.has(item.id) }));
    const bySubject = new Map<string, { item: MemoryItem; count: number; inView: boolean }>();
    for (const item of items) {
      const current = bySubject.get(item.canonical_subject);
      if (current) {
        current.count += 1;
        current.inView &&= memberIds.has(item.id);
      } else {
        bySubject.set(item.canonical_subject, { item, count: 1, inView: memberIds.has(item.id) });
      }
    }
    return [...bySubject.values()];
  }, [items, memberIds, subject]);

  const run = () => {
    const q = query.trim();
    if (!q || busy) return;
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    setBusy(true);
    setError(null);
    searchMemory(config, {
      q,
      mode: "fts",
      limit: 12,
      scope_kind: lens.scope.kind,
      scope_key: lens.scope.key ?? undefined,
    })
      .then((result) => {
        if (!mounted.current || seq !== requestSeq.current || queryRef.current.trim() !== q) return;
        setItems(result.mode === "fts" ? result.items : result.items.map(({ item }) => item));
        setSearched(true);
      })
      .catch((e) => {
        if (!mounted.current || seq !== requestSeq.current || queryRef.current.trim() !== q) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (mounted.current && seq === requestSeq.current) setBusy(false);
      });
  };

  if (!open) {
    return (
      <div className="mt-2">
        <GhostBtn onClick={() => setOpen(true)} title={subject ? `Find evidence for ${subject}` : "Find entries"}>
          <Search size={ICON.XS} strokeWidth={2.2} />
          <span>{label}</span>
          {subject && <span className="max-w-[180px] truncate text-xs text-faint">{subject}</span>}
        </GhostBtn>
      </div>
    );
  }

  return (
    <div className="glass-surface surface-popover mt-2 p-2.5">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search
            size={ICON.XS}
            strokeWidth={2.2}
            className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") run();
              if (e.key === "Escape") setOpen(false);
            }}
            placeholder={subject ? "Search this profile" : "Search memory"}
            spellCheck={false}
            className="input-field h-7 pl-7 text-sm"
            style={{ paddingLeft: "2rem" }}
          />
        </div>
        <PrimaryBtn onClick={run} disabled={busy || !query.trim()}>
          {busy ? "Searching..." : "Search"}
        </PrimaryBtn>
      </div>

      {error && <div className="mt-2 text-xs text-bad">{error}</div>}

      {searched && candidates.length === 0 && !error && (
        <div className="py-4 text-center text-sm italic text-faint">No claims found.</div>
      )}

      {candidates.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          {candidates.map(({ item, count, inView }) => {
            return (
              <div
                key={item.id}
                className="rounded-md px-2 py-1.5 text-left transition-colors hover:bg-surface-soft/60"
              >
                <div className="flex items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-medium text-ink">
                        {subject ? item.content : item.canonical_subject}
                      </span>
                      {count > 1 && (
                        <Badge tone="neutral" size="sm" className="tabular-nums">
                          {count}
                        </Badge>
                      )}
                    </div>
                    {!subject && (
                      <div className="mt-0.5 truncate text-xs text-faint">{item.content}</div>
                    )}
                  </div>
                  <Badge tone={inView ? "ok" : "warn"} size="sm">
                    {inView ? "In view" : "Review criterion"}
                  </Badge>
                </div>
                <div className="mt-1 flex items-center justify-end gap-1">
                  <GhostBtn onClick={() => onPeekClaim(item.id)}>
                    <ExternalLink size={ICON.XS} strokeWidth={2.2} /> Open
                  </GhostBtn>
                  {!inView && (
                    <GhostBtn onClick={onEditCriterion}>
                      <SlidersHorizontal size={ICON.XS} strokeWidth={2.2} /> Edit criterion
                    </GhostBtn>
                  )}
                  <GhostBtn onClick={onRefresh}>
                    <RefreshCw size={ICON.XS} strokeWidth={2.2} /> Refresh
                  </GhostBtn>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-2 flex justify-end">
        <GhostBtn onClick={() => setOpen(false)}>Close</GhostBtn>
      </div>
    </div>
  );
}

function initialQuery(subject: string | undefined, lensName: string) {
  if (!subject) return lensName;
  const normalized = subject.trim().toLowerCase();
  return normalized === "the user" || normalized === "user" ? "" : subject;
}
