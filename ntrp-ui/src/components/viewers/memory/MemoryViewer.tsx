import { useState } from "react";
import type { Config } from "../../../types.js";
import type { FactFilters, ObservationFilters } from "../../../api/client.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import { useDreamsTab } from "../../../hooks/useDreamsTab.js";
import { usePruneTab } from "../../../hooks/usePruneTab.js";
import { useMemoryData } from "../../../hooks/useMemoryData.js";
import { useMemoryKeypress } from "../../../hooks/useMemoryKeypress.js";
import { Dialog, Loading, Tabs, colors } from "../../ui/index.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import { PruneSection } from "./PruneSection.js";
import { DreamsSection } from "./DreamsSection.js";
import { MemoryFooter } from "./MemoryFooter.js";

const TABS = ["facts", "observations", "prune", "dreams"] as const;
type TabType = (typeof TABS)[number];

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<TabType>("facts");
  const [factFilters, setFactFilters] = useState<FactFilters>({ status: "active" });
  const [observationFilters, setObservationFilters] = useState<ObservationFilters>({ status: "active" });

  const { facts, factTotal, observations, observationTotal, dreams, pruneDryRun, loading, error, setFacts, setObservations, setDreams, setError, reload } =
    useMemoryData(config, factFilters, observationFilters);

  const factsTab = useFactsTab(config, facts, 80, factFilters, setFactFilters, factTotal);
  const obsTab = useObservationsTab(config, observations, 80, observationFilters, setObservationFilters, observationTotal);
  const pruneTab = usePruneTab(pruneDryRun?.candidates ?? [], 80);
  const dreamsTab = useDreamsTab(config, dreams, 80);

  const { saving } = useMemoryKeypress({
    activeTab,
    setActiveTab,
    factsTab,
    obsTab,
    pruneTab,
    pruneDryRun,
    dreamsTab,
    config,
    setFacts,
    setObservations,
    setDreams,
    setError,
    reload,
    onClose,
  });

  if (loading) {
    return (
      <Dialog title="MEMORY" size="full" onClose={onClose}>
        {() => <Loading message="Loading memory..." />}
      </Dialog>
    );
  }

  if (error) {
    return (
      <Dialog title="MEMORY" size="full" onClose={onClose}>
        {() => <text><span fg={colors.text.muted}>{error}</span></text>}
      </Dialog>
    );
  }

  return (
    <Dialog
      title="MEMORY"
      size="full"
      onClose={onClose}
      footer={<MemoryFooter activeTab={activeTab} factsTab={factsTab} obsTab={obsTab} pruneTab={pruneTab} dreamsTab={dreamsTab} />}
    >
      {({ width, height }) => {
        const sectionHeight = height - 2;
        const tab = activeTab === "facts" ? factsTab : activeTab === "observations" ? obsTab : activeTab === "prune" ? pruneTab : dreamsTab;
        const filterDisplay = activeTab === "facts"
          ? [
              `kind: ${factsTab.filters.kind ?? "all"}`,
              `status: ${factsTab.filters.status ?? "active"}`,
              `src: ${factsTab.filters.sourceType ?? "all"}`,
              `seen: ${factsTab.filters.accessed ?? "all"}`,
            ].join(" · ")
          : activeTab === "observations"
            ? [
                `status: ${obsTab.filters.status ?? "active"}`,
                `seen: ${obsTab.filters.accessed ?? "all"}`,
                `support: ${obsTab.filters.minSources ? `${obsTab.filters.minSources}+` : "all"}`,
                `total: ${obsTab.observationTotal}`,
              ].join(" · ")
            : activeTab === "prune" && pruneDryRun
              ? [
                  `older: ${pruneDryRun.criteria.older_than_days}d`,
                  `support <= ${pruneDryRun.criteria.max_sources}`,
                  `candidates: ${pruneDryRun.summary.total}`,
                ].join(" · ")
            : "";
        const sortDisplay = `sort: ${tab.sortOrder}`;

        return (
          <>
            <box flexDirection="row" marginBottom={1} marginTop={1}>
              <Tabs
                tabs={TABS}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                labels={{ facts: "Facts", observations: "Patterns", prune: "Prune", dreams: "Dreams" }}
              />
              <box flexGrow={1} />
              {filterDisplay && (
                <box marginRight={3}>
                  <text><span fg={colors.text.disabled}>{filterDisplay}</span></text>
                </box>
              )}
              <text><span fg={colors.text.disabled}>{sortDisplay}</span></text>
            </box>

            {activeTab === "facts" && (
              <FactsSection tab={factsTab} height={sectionHeight} width={width} saving={saving} />
            )}

            {activeTab === "observations" && (
              <ObservationsSection tab={obsTab} height={sectionHeight} width={width} saving={saving} />
            )}

            {activeTab === "prune" && (
              <PruneSection tab={pruneTab} dryRun={pruneDryRun} height={sectionHeight} width={width} />
            )}

            {activeTab === "dreams" && (
              <DreamsSection tab={dreamsTab} height={sectionHeight} width={width} />
            )}

          </>
        );
      }}
    </Dialog>
  );
}
