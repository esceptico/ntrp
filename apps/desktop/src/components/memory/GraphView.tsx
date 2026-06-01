import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import type { AppConfig } from "../../api";
import { getMemoryGraph, listMemoryLenses, type MemoryItem } from "../../api/memoryItems";
import { SPRING_MODAL } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { Badge } from "../Badge";
import { MemoryGraph, type CenterRequest, type GraphPayload } from "./MemoryGraph";
import { DetailPlaceholder, Empty, ListError } from "./shared";
import { lensTitle, provenanceLabel, provenanceTone, relativeTime, scopeLabel } from "./lens";

/** Provenance underside. Seeds the BFS from a focused item (peel-in from a
 *  lens header or a claim); with no focus it picks the first lens so the
 *  graph is never empty on the global tab. */
export function GraphView({ config, focusId }: { config: AppConfig; focusId: string | null }) {
  const [rootId, setRootId] = useState<string | null>(focusId);
  const [graph, setGraph] = useState<GraphPayload>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MemoryItem | null>(null);
  const [center, setCenter] = useState<CenterRequest | null>(null);

  // Resolve a seed: explicit focus, else the first lens in scope.
  useEffect(() => {
    if (focusId) {
      setRootId(focusId);
      return;
    }
    if (rootId) return;
    listMemoryLenses(config)
      .then((r) => setRootId(r.lenses[0]?.lens.id ?? null))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [focusId, config, rootId]);

  const load = useCallback(
    (id: string) => {
      setLoading(true);
      getMemoryGraph(config, id, { direction: "both", depth: 3 })
        .then((g) => {
          setGraph({ nodes: g.nodes, edges: g.edges });
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    },
    [config],
  );

  useEffect(() => {
    if (rootId) load(rootId);
    else setLoading(false);
  }, [rootId, load]);

  const onSelect = useCallback((item: MemoryItem) => {
    setSelected(item);
  }, []);

  if (error) {
    return (
      <div className="p-7">
        <ListError title="Couldn't load the graph" message={error} />
      </div>
    );
  }

  if (!loading && !rootId) {
    return <Empty>No memory to map yet. Create a lens to see its provenance.</Empty>;
  }

  return (
    <div className="relative h-full overflow-hidden">
      {loading && graph.nodes.length === 0 ? (
        <DetailPlaceholder>Settling the graph…</DetailPlaceholder>
      ) : (
        <MemoryGraph graph={graph} rootId={rootId} selectedId={selected?.id ?? null} onSelect={onSelect} centerRequest={center} />
      )}

      {/* Peel-in inspector — sibling-anchored glass card, slides from the right. */}
      <AnimatePresence>
        {selected && (
          <motion.div
            key={selected.id}
            initial={{ opacity: 0, x: 28 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 28 }}
            transition={SPRING_MODAL}
            className="glass-surface surface-popover absolute right-3 top-3 bottom-3 z-10 flex w-[300px] flex-col p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <Badge tone={selected.kind === "lens" ? "accent" : "neutral"} size="sm">
                {selected.kind}
              </Badge>
              <IconButton onClick={() => setSelected(null)} aria-label="Close" size="sm">
                <X size={ICON.SM} strokeWidth={2} />
              </IconButton>
            </div>
            <p className="mt-3 text-sm leading-[1.5] text-ink">
              {selected.kind === "lens" ? lensTitle(selected) : selected.content}
            </p>
            {selected.kind === "lens" && selected.lens_criterion && (
              <p className="mt-1.5 text-xs italic text-faint">{selected.lens_criterion}</p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <Badge tone={provenanceTone(selected.provenance)} size="sm">
                {provenanceLabel(selected.provenance)}
              </Badge>
              <Badge tone="neutral" size="sm">
                {scopeLabel(selected.scope)}
              </Badge>
              {selected.corroboration > 0 && (
                <span className="text-2xs text-faint tabular-nums">×{selected.corroboration}</span>
              )}
            </div>
            <div className="mt-auto pt-3 text-2xs text-faint">
              created {relativeTime(selected.created_at)}
            </div>
            <button
              type="button"
              onClick={() => {
                setRootId(selected.id);
                setCenter({ id: selected.id, nonce: Date.now() });
              }}
              className="mt-2 inline-flex h-7 items-center justify-center rounded-md bg-surface-soft text-sm text-ink-soft transition-colors hover:bg-surface-sunken hover:text-ink"
            >
              Center here
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
