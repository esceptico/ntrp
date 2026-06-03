import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import type { AppConfig } from "../../api";
import { getMemoryGraph, getWholeGraph, type MemoryItem } from "../../api/memoryItems";
import { SPRING_MODAL } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { Badge } from "../Badge";
import { MemoryGraph, type CenterRequest, type GraphPayload } from "./MemoryGraph";
import { DetailPlaceholder, Empty, ListError } from "./shared";
import { provenanceLabel, provenanceTone, relativeTime, scopeLabel } from "./lens";

/** The claim graph. By default the whole in-scope graph (all claims + claim↔claim
 *  edges); click-to-focus re-roots a bounded BFS on a claim. Lenses are never
 *  nodes (the locked model: memory is claims only). */
export function GraphView({
  config,
  scope,
  focusId,
}: {
  config: AppConfig;
  scope: { kind: "user" | "project" | "session"; key: string | null } | null;
  focusId: string | null;
}) {
  const [rootId, setRootId] = useState<string | null>(focusId);
  const [graph, setGraph] = useState<GraphPayload>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MemoryItem | null>(null);
  const [center, setCenter] = useState<CenterRequest | null>(null);

  useEffect(() => {
    setRootId(focusId);
  }, [focusId]);

  const load = useCallback(
    (id: string | null, alive: () => boolean) => {
      setLoading(true);
      // No root → whole-graph (default). A root → click-to-focus BFS.
      const req = id
        ? getMemoryGraph(config, id, { direction: "both", depth: 3 })
        : getWholeGraph(config, { scope_kind: scope?.kind, scope_key: scope?.key ?? undefined });
      req
        .then((g) => {
          // Drop a stale response: rootId may have changed (and a newer request
          // resolved) before this one returned — applying it would overwrite the
          // current graph with the wrong one.
          if (!alive()) return;
          setGraph({ nodes: g.nodes, edges: g.edges });
          setError(null);
        })
        .catch((e) => {
          if (alive()) setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (alive()) setLoading(false);
        });
    },
    [config, scope?.kind, scope?.key],
  );

  useEffect(() => {
    let alive = true;
    load(rootId, () => alive);
    return () => {
      alive = false;
    };
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

  if (!loading && graph.nodes.length === 0) {
    return <Empty>No claims yet.</Empty>;
  }

  return (
    <div className="relative h-full overflow-hidden">
      {loading && graph.nodes.length === 0 ? (
        <DetailPlaceholder>Settling the graph…</DetailPlaceholder>
      ) : (
        <MemoryGraph graph={graph} rootId={rootId} selectedId={selected?.id ?? null} onSelect={onSelect} centerRequest={center} />
      )}

      {/* Peel-in inspector — sibling-anchored panel, slides from the right. */}
      <AnimatePresence>
        {selected && (
          <motion.div
            key={selected.id}
            initial={{ opacity: 0, x: 28 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 28 }}
            transition={SPRING_MODAL}
            className="surface-panel surface-popover absolute right-3 top-3 bottom-3 z-10 flex w-[300px] flex-col p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <Badge tone="neutral" size="sm">
                {selected.canonical_subject}
              </Badge>
              <IconButton onClick={() => setSelected(null)} aria-label="Close" size="sm">
                <X size={ICON.SM} strokeWidth={2} />
              </IconButton>
            </div>
            <p className="mt-3 text-sm leading-[1.5] text-ink">{selected.content}</p>
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
