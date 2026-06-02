import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ExternalLink, Loader2, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import type { AppConfig } from "../../api";
import { searchMemory, writebackLens, type Lens, type MemoryItem } from "../../api/memoryItems";
import { ICON } from "../../lib/icons";
import { MOTION, SPRING_LAYOUT, SPRING_POPOVER } from "../../lib/tokens/motion";
import { Badge } from "../Badge";
import { GhostBtn, SearchInput } from "./shared";

const DEBOUNCE = 220;
const LIMIT = 15;

interface LensEvidenceSearchProps {
  config: AppConfig;
  lens: Lens;
  memberIds: Set<string>;
  onEditCriterion: () => void;
  onPeekClaim: (claimId: string) => void;
  onRefresh: () => void;
  /** A group header bumps `nonce` to open the panel seeded with a subject term. */
  seed?: { term: string; nonce: number };
}

export function LensEvidenceSearch({
  config,
  lens,
  memberIds,
  onEditCriterion,
  onPeekClaim,
  onRefresh,
  seed,
}: LensEvidenceSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [includingId, setIncludingId] = useState<string | null>(null);
  const [includedIds, setIncludedIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // A group header opens the single search seeded with its subject term.
  useEffect(() => {
    if (!seed || seed.nonce === 0) return;
    setOpen(true);
    setQuery(seed.term);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce]);

  // Refocus on (re)seed — autoFocus only fires on first mount, so a reseed while
  // the panel is already open needs an explicit focus (effects run post-commit, so
  // the input is already mounted; focusing it also scrolls it into view).
  useEffect(() => {
    if (!open || !seed || seed.nonce === 0) return;
    inputRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, seed?.nonce]);

  // Live, debounced, whole-pool search (mirrors ClaimsView). Stale responses are
  // dropped via the `alive` flag; an empty query clears results without a request.
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (!q) {
      setItems([]);
      setSearched(false);
      setBusy(false);
      setError(null);
      return;
    }
    setBusy(true);
    setError(null);
    let alive = true;
    const handle = setTimeout(() => {
      searchMemory(config, { q, mode: "fts", limit: LIMIT })
        .then((r) => {
          if (!alive) return;
          setItems(r.mode === "fts" ? r.items : r.items.map(({ item }) => item));
          setSearched(true);
        })
        .catch((e) => {
          if (alive) setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (alive) setBusy(false);
        });
    }, DEBOUNCE);
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [query, config, open]);

  const results = useMemo(
    () =>
      items.map((item) => ({
        item,
        inView: memberIds.has(item.id) || includedIds.has(item.id),
        included: includedIds.has(item.id),
      })),
    [items, memberIds, includedIds],
  );

  const include = (item: MemoryItem) => {
    if (memberIds.has(item.id) || includedIds.has(item.id) || includingId) return;
    setIncludingId(item.id);
    setError(null);
    writebackLens(config, lens.id, [{ kind: "include", claim_id: item.id }])
      .then(() => {
        setIncludedIds((cur) => new Set(cur).add(item.id));
        onRefresh();
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setIncludingId(null);
      });
  };

  const close = () => {
    setOpen(false);
    setError(null);
  };

  const trimmed = query.trim();

  return (
    <div className="mt-2">
      {!open && (
        <GhostBtn onClick={() => setOpen(true)} title="Find entries">
          <Search size={ICON.XS} strokeWidth={2.2} />
          <span>Find entries</span>
        </GhostBtn>
      )}
      <AnimatePresence>
        {open && (
          <motion.div
            key="panel"
            initial={{ opacity: 0, scale: 0.98, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -4 }}
            transition={SPRING_POPOVER}
            style={{ transformOrigin: "top" }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.stopPropagation();
                close();
              }
            }}
            className="glass-surface surface-popover p-2.5"
          >
            <div className="flex items-center gap-2">
              <SearchInput
                value={query}
                onChange={setQuery}
                placeholder="Search your memory"
                ariaLabel="Search memory for evidence"
                autoFocus
                busy={busy}
                inputRef={inputRef}
              />
              <button
                type="button"
                onClick={close}
                aria-label="Close search"
                className="grid size-7 shrink-0 place-items-center rounded-md text-faint transition-colors hover:bg-surface-soft hover:text-ink"
              >
                <X size={ICON.XS} strokeWidth={2.2} />
              </button>
            </div>

            {error && <div className="mt-2 text-xs text-bad">{error}</div>}

            {!trimmed && (
              <div className="px-2 py-5 text-center text-sm text-faint">
                Search your memory to add evidence to this view.
              </div>
            )}

            {trimmed && busy && results.length === 0 && (
              <div className="mt-2 flex flex-col gap-1.5" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <div key={i} className="skeleton h-9 rounded-md" />
                ))}
              </div>
            )}

            {trimmed && searched && !busy && !error && results.length === 0 && (
              <div className="px-2 py-5 text-center">
                <div className="text-sm text-faint">No matching claims.</div>
                <div className="mt-1 text-xs text-faint">
                  Try a broader term, or adjust what belongs in this view.
                </div>
                <div className="mt-2 flex justify-center">
                  <GhostBtn onClick={onEditCriterion}>
                    <SlidersHorizontal size={ICON.XS} strokeWidth={2.2} /> Edit criterion
                  </GhostBtn>
                </div>
              </div>
            )}

            {results.length > 0 && (
              <div className="mt-2 flex flex-col gap-0.5">
                <AnimatePresence mode="popLayout" initial={false}>
                  {results.map(({ item, inView, included }) => (
                    <motion.div
                      key={item.id}
                      layout
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.98 }}
                      transition={{
                        layout: SPRING_LAYOUT,
                        opacity: { duration: MOTION.row },
                        y: { duration: MOTION.fast },
                      }}
                      className="group/ev rounded-md px-2 py-1.5 transition-colors hover:bg-surface-soft/60"
                    >
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm text-ink-soft">{item.content}</div>
                          <div className="mt-0.5 truncate text-xs text-faint">{item.canonical_subject}</div>
                        </div>
                        {inView && (
                          <Badge tone="ok" size="sm" className="mt-0.5">
                            {included ? "Included" : "In view"}
                          </Badge>
                        )}
                        <div className="mt-0.5 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover/ev:opacity-100 focus-within:opacity-100">
                          <RowIcon onClick={() => onPeekClaim(item.id)} title="Open claim">
                            <ExternalLink size={ICON.XS} strokeWidth={2.2} />
                          </RowIcon>
                          {!inView && (
                            <RowIcon
                              onClick={() => include(item)}
                              disabled={includingId !== null}
                              title="Include in this view"
                            >
                              {includingId === item.id ? (
                                <Loader2 size={ICON.XS} strokeWidth={2.2} className="animate-spin" />
                              ) : (
                                <Plus size={ICON.XS} strokeWidth={2.2} />
                              )}
                            </RowIcon>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RowIcon({
  children,
  onClick,
  disabled,
  title,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="grid size-[22px] place-items-center rounded text-faint transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  );
}
