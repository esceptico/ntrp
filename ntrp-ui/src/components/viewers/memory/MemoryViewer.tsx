import { useState } from "react";
import type { Config } from "../../../types.js";
import type { FactFilters, ObservationFilters } from "../../../api/client.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import { usePruneTab } from "../../../hooks/usePruneTab.js";
import { useMemoryEventsTab } from "../../../hooks/useMemoryEventsTab.js";
import { useMemoryData } from "../../../hooks/useMemoryData.js";
import { useMemoryKeypress } from "../../../hooks/useMemoryKeypress.js";
import { Dialog, Loading, Tabs, colors } from "../../ui/index.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import { PruneSection } from "./PruneSection.js";
import { MemoryEventsSection } from "./MemoryEventsSection.js";
import { MemoryFooter } from "./MemoryFooter.js";

const TABS = ["profile", "facts", "observations", "prune", "events"] as const;
type TabType = (typeof TABS)[number];

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<TabType>("profile");
  const [profileFilters, setProfileFilters] = useState<FactFilters>({ status: "active" });
  const [factFilters, setFactFilters] = useState<FactFilters>({ status: "active" });
  const [observationFilters, setObservationFilters] = useState<ObservationFilters>({ status: "active" });

  const { facts, factTotal, profileFacts, observations, observationTotal, pruneDryRun, memoryEvents, loading, error, setFacts, setObservations, setError, reload } =
    useMemoryData(config, factFilters, observationFilters);

  const profileTab = useFactsTab(config, profileFacts, 80, profileFilters, setProfileFilters, profileFacts.length);
  const factsTab = useFactsTab(config, facts, 80, factFilters, setFactFilters, factTotal);
  const obsTab = useObservationsTab(config, observations, 80, observationFilters, setObservationFilters, observationTotal);
  const pruneTab = usePruneTab(pruneDryRun?.candidates ?? [], 80);
  const eventsTab = useMemoryEventsTab(memoryEvents, 80);

  const { saving } = useMemoryKeypress({
    activeTab,
    setActiveTab,
    profileTab,
    factsTab,
    obsTab,
    pruneTab,
    pruneDryRun,
    eventsTab,
    config,
    setFacts,
    setObservations,
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
      footer={
        <MemoryFooter
          activeTab={activeTab}
          profileTab={profileTab}
          factsTab={factsTab}
          obsTab={obsTab}
          pruneTab={pruneTab}
          eventsTab={eventsTab}
        />
      }
    >
      {({ width, height }) => {
        const sectionHeight = height - 2;
        const tab = activeTab === "profile" ? profileTab : activeTab === "facts" ? factsTab : activeTab === "observations" ? obsTab : activeTab === "prune" ? pruneTab : eventsTab;
        const filterDisplay = activeTab === "profile"
          ? `profile facts: ${profileFacts.length}`
          : activeTab === "facts"
          ? [
              `kind: ${factsTab.filters.kind ?? "all"}`,
              `status: ${factsTab.filters.status ?? "active"}`,
              `source: ${factsTab.filters.sourceType ?? "all"}`,
              `usage: ${factsTab.filters.accessed ?? "all"}`,
            ].join(" · ")
          : activeTab === "observations"
            ? [
                `status: ${obsTab.filters.status ?? "active"}`,
                `usage: ${obsTab.filters.accessed ?? "all"}`,
                `support: ${obsTab.filters.minSources ? `${obsTab.filters.minSources}+` : "all"}`,
                `total: ${obsTab.observationTotal}`,
              ].join(" · ")
            : activeTab === "prune" && pruneDryRun
              ? [
                  `older: ${pruneDryRun.criteria.older_than_days}d`,
                  `max support: ${pruneDryRun.criteria.max_sources}`,
                  `candidates: ${pruneDryRun.summary.total}`,
                ].join(" · ")
            : activeTab === "events"
              ? [
                  `target: ${eventsTab.targetFilter}`,
                  `actor: ${eventsTab.actorFilter}`,
                  `action: ${eventsTab.actionFilter ?? "all"}`,
                  `events: ${memoryEvents.length}`,
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
                labels={{ profile: "Profile", facts: "Facts", observations: "Patterns", prune: "Cleanup", events: "Log" }}
              />
              <box flexGrow={1} />
              {filterDisplay && (
                <box marginRight={3}>
                  <text><span fg={colors.text.disabled}>{filterDisplay}</span></text>
                </box>
              )}
              <text><span fg={colors.text.disabled}>{sortDisplay}</span></text>
            </box>

            {activeTab === "profile" && (
              <FactsSection tab={profileTab} height={sectionHeight} width={width} saving={saving} emptyMessage="No profile facts yet" />
            )}

            {activeTab === "facts" && (
              <FactsSection tab={factsTab} height={sectionHeight} width={width} saving={saving} />
            )}

            {activeTab === "observations" && (
              <ObservationsSection tab={obsTab} height={sectionHeight} width={width} saving={saving} />
            )}

            {activeTab === "prune" && (
              <PruneSection tab={pruneTab} dryRun={pruneDryRun} height={sectionHeight} width={width} />
            )}

            {activeTab === "events" && (
              <MemoryEventsSection tab={eventsTab} totalCount={memoryEvents.length} height={sectionHeight} width={width} />
            )}
          </>
        );
      }}
    </Dialog>
  );
}
