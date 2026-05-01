import { useMemo, useState } from "react";
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
import { Dialog, Tabs, colors, truncateText } from "../../ui/index.js";
import { useContentWidth } from "../../../contexts/index.js";
import { memoryAccessSourceLabel } from "../../../lib/memoryAccess.js";
import { summarizeLearningCandidates } from "../../../lib/memoryLearning.js";
import { MEMORY_TABS, MEMORY_TAB_COPY, memoryTabLabels, type MemoryTabType } from "../../../lib/memoryTabs.js";
import { FactsSection } from "./FactsSection.js";
import { LearningSection } from "./LearningSection.js";
import { MemoryAccessSection } from "./MemoryAccessSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import { PruneSection } from "./PruneSection.js";
import { MemoryEventsSection } from "./MemoryEventsSection.js";
import { MemoryFooter } from "./MemoryFooter.js";
import { OverviewSection } from "./OverviewSection.js";
import { RecallInspectSection } from "./RecallInspectSection.js";

type SortableTab = { sortOrder: string };

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const contentWidth = useContentWidth();
  const [activeTab, setActiveTab] = useState<MemoryTabType>("overview");
  const [factFilters, setFactFilters] = useState<FactFilters>({ status: "active" });
  const [observationFilters, setObservationFilters] = useState<ObservationFilters>({ status: "active" });

  const {
    facts,
    factTotal,
    memoryProfilePolicy,
    observations,
    observationTotal,
    pruneDryRun,
    memoryEvents,
    learningEvents,
    learningCandidates,
    memoryAccessEvents,
    memoryAccessFacts,
    memoryAccessObservations,
    memoryInjectionPolicy,
    memoryAudit,
    loading,
    backgroundLoading,
    error,
    setFacts,
    setObservations,
    setLearningCandidates,
    setError,
    reload,
  } = useMemoryData(config, factFilters, observationFilters);

  const factsTab = useFactsTab(config, facts, contentWidth, factFilters, setFactFilters, factTotal);
  const obsTab = useObservationsTab(config, observations, contentWidth, observationFilters, setObservationFilters, observationTotal);
  const pruneTab = usePruneTab(pruneDryRun?.candidates ?? [], contentWidth);
  const learningTab = useLearningTab(learningCandidates, learningEvents, contentWidth);
  const eventsTab = useMemoryEventsTab(memoryEvents, contentWidth);
  const accessTab = useMemoryAccessTab(memoryAccessEvents, contentWidth);
  const recallTab = useRecallInspectTab(config);
  const learningSummary = useMemo(
    () => summarizeLearningCandidates(learningCandidates),
    [learningCandidates],
  );

  const { saving } = useMemoryKeypress({
    activeTab,
    setActiveTab,
    recallTab,
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

  return (
    <Dialog
      title="MEMORY"
      size="full"
      onClose={onClose}
      footer={
        <MemoryFooter
          activeTab={activeTab}
          recallTab={recallTab}
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
        const errorLineHeight = error ? 1 : 0;
        const sectionHeight = Math.max(1, height - 4 - errorLineHeight);
        const tab: SortableTab | null =
          activeTab === "overview" || activeTab === "recall"
            ? null
            : activeTab === "context"
              ? accessTab
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
          ? `${factTotal} facts · ${observationTotal} patterns · ${learningSummary.needsAction} learning`
          : activeTab === "recall"
          ? recallTab.result
            ? `${recallTab.result.observations.length} patterns · ${recallTab.result.facts.length} facts`
            : "no query yet"
          : activeTab === "context"
          ? [
              `source: ${accessTab.sourceFilter === "all" ? "all" : memoryAccessSourceLabel(accessTab.sourceFilter)}`,
              `policy flags: ${memoryInjectionPolicy?.summary.candidates ?? 0}`,
              `loaded: ${memoryAccessEvents.length}`,
            ].join(" · ")
          : activeTab === "facts"
          ? [
              `kind: ${factsTab.filters.kind ?? "all"}`,
              `life: ${factsTab.filters.lifetime ?? "all"}`,
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
                  `lane: ${learningTab.laneFilter}`,
                  `status: ${learningTab.statusFilter}`,
                  `type: ${learningTab.changeTypeFilter ?? "all"}`,
                  `review: ${learningSummary.proposed}`,
                  `apply: ${learningSummary.readyToApply}`,
                  `active: ${learningSummary.active}`,
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
        const loadDisplay = loading ? "loading memory" : backgroundLoading ? "loading checks" : error ? "load warning" : "";
        const statusDisplay = [loadDisplay, filterDisplay, sortDisplay].filter(Boolean).join(" · ");
        const copy = MEMORY_TAB_COPY[activeTab];
        const copyWidth = Math.max(1, Math.min(width, Math.max(24, Math.floor(width * 0.58))));
        const copyDescriptionWidth = Math.max(8, copyWidth - copy.title.length - 3);
        const statusWidth = Math.max(0, width - copyWidth - 4);

        return (
          <>
            <box flexDirection="row" marginBottom={1} marginTop={1}>
              <Tabs
                tabs={MEMORY_TABS}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                labels={memoryTabLabels(width)}
              />
            </box>

            <box flexDirection="row" marginBottom={1}>
              <box width={copyWidth}>
                <text>
                  <span fg={colors.text.secondary}>{copy.title}</span>
                  <span fg={colors.text.disabled}> {"\u2502"} {truncateText(copy.description, copyDescriptionWidth)}</span>
                </text>
              </box>
              <box flexGrow={1} />
              {statusDisplay && statusWidth > 12 && (
                <text><span fg={colors.text.disabled}>{truncateText(statusDisplay, statusWidth)}</span></text>
              )}
            </box>

            {error && (
              <box marginBottom={1}>
                <text><span fg={colors.status.error}>{truncateText(error, width)}</span></text>
              </box>
            )}

            {activeTab === "overview" && (
              <OverviewSection
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
                facts={[...facts, ...memoryAccessFacts]}
                observations={[...observations, ...memoryAccessObservations]}
                height={sectionHeight}
                width={width}
              />
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
