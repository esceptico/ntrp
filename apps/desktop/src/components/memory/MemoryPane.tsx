import { useState } from "react";
import type { AppConfig } from "../../api";
import { useStore } from "../../store";
import { TabPanels, useTabDirection } from "../ui/TabPanels";
import { DetailPlaceholder } from "./shared";
import { LensesView } from "./LensesView";
import { ClaimsView } from "./ClaimsView";
import { GraphView } from "./GraphView";

export type MemoryDestination = "lenses" | "claims" | "graph";
export const MEMORY_TABS: { id: MemoryDestination; label: string }[] = [
  { id: "claims", label: "Claims" },
  { id: "lenses", label: "Lenses" },
  { id: "graph", label: "Graph" },
];
const ORDER = MEMORY_TABS.map((t) => t.id);

/** Hosts the three woven destinations. Peel state threads between them: a
 *  claim peeked from a lens opens Claims focused on that claim; a provenance
 *  request opens Graph seeded on that item. */
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

  if (!config) {
    return <DetailPlaceholder>Memory is unavailable until the app config loads.</DetailPlaceholder>;
  }

  const peekClaim = (claimId: string) => {
    setClaimFocus(claimId);
    onTab("claims");
  };
  const showProvenance = (itemId: string) => {
    setGraphFocus(itemId);
    onTab("graph");
  };

  return (
    <TabPanels value={tab} direction={direction} className="h-full min-h-0">
      {tab === "lenses" && (
        <LensesView config={config} onPeekClaim={peekClaim} onProvenance={showProvenance} />
      )}
      {tab === "claims" && (
        <ClaimsView config={config} focusId={claimFocus} onProvenance={showProvenance} />
      )}
      {tab === "graph" && <GraphView config={config} focusId={graphFocus} />}
    </TabPanels>
  );
}

function useConfig(): AppConfig | null {
  return useStore((s) => s.config);
}
