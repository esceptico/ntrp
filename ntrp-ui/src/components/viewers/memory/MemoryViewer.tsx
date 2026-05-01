import { useState } from "react";
import type { Config } from "../../../types.js";
import type { FactFilters, ObservationFilters } from "../../../api/client.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import { usePruneTab } from "../../../hooks/usePruneTab.js";
import { useMemoryEventsTab } from "../../../hooks/useMemoryEventsTab.js";
import { useMemoryAccessTab } from "../../../hooks/useMemoryAccessTab.js";
import { useLearningTab } from "../../../hooks/useLearningTab.js";
import { useMemoryData } from "../../../hooks/useMemoryData.js";
import { useMemoryKeypress } from "../../../hooks/useMemoryKeypress.js";
import { useRecallInspectTab } from "../../../hooks/useRecallInspectTab.js";
import { Dialog, Loading, Tabs, colors } from "../../ui/index.js";
import { memoryAccessSourceLabel } from "../../../lib/memoryAccess.js";
import { FactsSection } from "./FactsSection.js";
import { LearningSection } from "./LearningSection.js";
import { MemoryAccessSection } from "./MemoryAccessSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import { PruneSection } from "./PruneSection.js";
import { MemoryEventsSection } from "./MemoryEventsSection.js";
import { MemoryFooter } from "./MemoryFooter.js";
import { OverviewSection } from "./OverviewSection.js";
import { RecallInspectSection } from "./RecallInspectSection.js";

const TABS = ["overview", "recall", "context", "profile", "facts", "observations", "prune", "learning", "events"] as const;
type TabType = (typeof TABS)[number];
type SortableTab = { sortOrder: string };

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

function tabLabels(width: number): Record<TabType, string> {
  if (width < 95) {
    return {
      overview: "Home",
      recall: "Query",
      context: "Used",
      profile: "Prof",
      facts: "Facts",
      observations: "Pat",
      prune: "Clean",
      learning: "Learn",
      events: "Log",
    };
  }
  return {
    overview: "Overview",
    recall: "Recall",
    context: "Used",
    profile: "Profile",
    facts: "Facts",
    observations: "Patterns",
    prune: "Cleanup",
    learning: "Learning",
    events: "Log",
  };
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [profileFilters, setProfileFilters] = useState<FactFilters>({ status: "active" });
  const [factFilters, setFactFilters] = useState<FactFilters>({ status: "active" });
  const [observationFilters, setObservationFilters] = useState<ObservationFilters>({ status: "active" });

  const {
    facts,
    factTotal,
    profileFacts,
    memoryProfilePolicy,
    observations,
    observationTotal,
    pruneDryRun,
    memoryEvents,
    learningEvents,
    learningCandidates,
    memoryAccessEvents,
    memoryInjectionPolicy,
    memoryAudit,
    loading,
    error,
    setFacts,
    setObservations,
    setLearningCandidates,
    setError,
    reload,
  } = useMemoryData(config, factFilters, observationFilters);

  const profileTab = useFactsTab(config, profileFacts, 80, profileFilters, setProfileFilters, profileFacts.length);
  const factsTab = useFactsTab(config, facts, 80, factFilters, setFactFilters, factTotal);
  const obsTab = useObservationsTab(config, observations, 80, observationFilters, setObservationFilters, observationTotal);
  const pruneTab = usePruneTab(pruneDryRun?.candidates ?? [], 80);
  const learningTab = useLearningTab(learningCandidates, learningEvents, 80);
  const eventsTab = useMemoryEventsTab(memoryEvents, 80);
  const accessTab = useMemoryAccessTab(memoryAccessEvents, 80);
  const recallTab = useRecallInspectTab(config);

  const { saving } = useMemoryKeypress({
    activeTab,
    setActiveTab,
    recallTab,
    profileTab,
    factsTab,
    obsTab,
    pruneTab,
    learningTab,
    pruneDryRun,
    accessTab,
    eventsTab,
    config,
    setFacts,
    setObservations,
    setLearningCandidates,
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
          recallTab={recallTab}
          profileTab={profileTab}
          factsTab={factsTab}
          obsTab={obsTab}
          pruneTab={pruneTab}
          learningTab={learningTab}
          accessTab={accessTab}
          eventsTab={eventsTab}
        />
      }
    >
      {({ width, height }) => {
        const sectionHeight = height - 2;
        const tab: SortableTab | null =
          activeTab === "overview" || activeTab === "recall"
            ? null
            : activeTab === "context"
              ? accessTab
              : activeTab === "profile"
                ? profileTab
                : activeTab === "facts"
                  ? factsTab
                  : activeTab === "observations"
                    ? obsTab
                    : activeTab === "prune"
                      ? pruneTab
                      : activeTab === "learning"
                        ? learningTab
                        : eventsTab;
        const filterDisplay = activeTab === "overview"
          ? "Recall · Used · Profile · Facts · Patterns · Cleanup · Learning · Log"
          : activeTab === "recall"
          ? recallTab.result
            ? `${recallTab.result.observations.length} patterns · ${recallTab.result.facts.length} facts`
            : "no query yet"
          : activeTab === "context"
          ? [
              `source: ${accessTab.sourceFilter === "all" ? "all" : memoryAccessSourceLabel(accessTab.sourceFilter)}`,
              `flags: ${memoryInjectionPolicy?.summary.candidates ?? 0}`,
              `loaded: ${memoryAccessEvents.length}`,
            ].join(" · ")
          : activeTab === "profile"
          ? [
              `profile facts: ${profileFacts.length}`,
              `review: ${(memoryProfilePolicy?.summary.candidates ?? 0) + (memoryProfilePolicy?.summary.issues ?? 0)}`,
            ].join(" · ")
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
            : activeTab === "learning"
              ? [
                  `status: ${learningTab.statusFilter}`,
                  `type: ${learningTab.changeTypeFilter ?? "all"}`,
                  `candidates: ${learningCandidates.length}`,
                  `events: ${learningEvents.length}`,
                ].join(" · ")
            : activeTab === "events"
              ? [
                  `target: ${eventsTab.targetFilter}`,
                  `actor: ${eventsTab.actorFilter}`,
                  `action: ${eventsTab.actionFilter ?? "all"}`,
                  `events: ${memoryEvents.length}`,
                ].join(" · ")
            : "";
        const sortDisplay = tab ? `sort: ${tab.sortOrder}` : "";

        return (
          <>
            <box flexDirection="row" marginBottom={1} marginTop={1}>
              <Tabs
                tabs={TABS}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                labels={tabLabels(width)}
              />
              <box flexGrow={1} />
              {filterDisplay && (
                <box marginRight={3}>
                  <text><span fg={colors.text.disabled}>{filterDisplay}</span></text>
                </box>
              )}
              {sortDisplay && <text><span fg={colors.text.disabled}>{sortDisplay}</span></text>}
            </box>

            {activeTab === "overview" && (
              <OverviewSection
                profileFacts={profileFacts}
                memoryProfilePolicy={memoryProfilePolicy}
                factTotal={factTotal}
                observationTotal={observationTotal}
                pruneDryRun={pruneDryRun}
                memoryEvents={memoryEvents}
                learningCandidates={learningCandidates}
                memoryAccessEvents={memoryAccessEvents}
                memoryInjectionPolicy={memoryInjectionPolicy}
                memoryAudit={memoryAudit}
                height={sectionHeight}
                width={width}
              />
            )}

            {activeTab === "recall" && (
              <RecallInspectSection tab={recallTab} height={sectionHeight} width={width} />
            )}

            {activeTab === "context" && (
              <MemoryAccessSection
                tab={accessTab}
                totalCount={memoryAccessEvents.length}
                policyPreview={memoryInjectionPolicy}
                height={sectionHeight}
                width={width}
              />
            )}

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

            {activeTab === "learning" && (
              <LearningSection
                tab={learningTab}
                totalCount={learningCandidates.length}
                height={sectionHeight}
                width={width}
              />
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
