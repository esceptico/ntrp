import { useEffect, useRef, useState } from "react";
import type { AppConfig } from "../../api";
import { useStore } from "../../store";
import { TabPanels, useTabDirection } from "../ui/TabPanels";
import { DetailPlaceholder } from "./shared";
import { LensesView } from "./LensesView";
import { ClaimsView } from "./ClaimsView";
import { GraphView } from "./GraphView";

export type MemoryDestination = "lenses" | "claims" | "graph";
export const MEMORY_TABS: { id: MemoryDestination; label: string }[] = [
  { id: "claims", label: "Memory" },
  { id: "graph", label: "Graph" },
  { id: "lenses", label: "Lenses" },
];
const ORDER = MEMORY_TABS.map((t) => t.id);

/** Hosts the three woven destinations. The memory itself (records + their
 *  derivations) is the default surface; the graph is its DAG; lenses are the
 *  side feature. Peel state threads between them: a claim peeked from a lens
 *  opens Memory focused on that claim; a provenance request seeds the Graph. */
export function MemoryPane({
  tab,
  onTab,
}: {
  tab: MemoryDestination;
  onTab: (t: MemoryDestination) => void;
}) {
  const config = useConfig();
  const [claimFocus, setClaimFocus] = useState<string | null>(null);
  const [graphFocus, setGraphFocus] = useState<string | null>(null);
  const direction = useTabDirection(ORDER, tab);

  // Memory is ONE flat connected store — no projects/scopes. Every view sees the
  // whole pool (scope = null).

  // A peel-in (claim/provenance) carries focus to the destination; a manual tab
  // switch must NOT — else the stale focus re-applies when the unmounted view
  // remounts. Mark peel navigations so the tab-change effect leaves their focus,
  // and clear focus on any other tab change.
  const peeledRef = useRef(false);
  useEffect(() => {
    if (peeledRef.current) {
      peeledRef.current = false;
      return;
    }
    setClaimFocus(null);
    setGraphFocus(null);
  }, [tab]);

  if (!config) {
    return <DetailPlaceholder>Memory is unavailable until the app config loads.</DetailPlaceholder>;
  }

  const peekClaim = (claimId: string) => {
    setClaimFocus(claimId);
    if (tab !== "claims") peeledRef.current = true;
    onTab("claims");
  };
  const showProvenance = (itemId: string) => {
    setGraphFocus(itemId);
    if (tab !== "graph") peeledRef.current = true;
    onTab("graph");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TabPanels value={tab} direction={direction} className="h-full min-h-0">
        {tab === "lenses" && (
          <LensesView config={config} scope={null} onPeekClaim={peekClaim} />
        )}
        {tab === "claims" && (
          <ClaimsView config={config} scope={null} focusId={claimFocus} onProvenance={showProvenance} />
        )}
        {tab === "graph" && <GraphView config={config} scope={null} focusId={graphFocus} />}
      </TabPanels>
    </div>
  );
}

function useConfig(): AppConfig | null {
  return useStore((s) => s.config);
}
