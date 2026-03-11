import { useState } from "react";
import type { Config } from "../../../types.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import { useDreamsTab } from "../../../hooks/useDreamsTab.js";
import { useMemoryData } from "../../../hooks/useMemoryData.js";
import { useMemoryKeypress } from "../../../hooks/useMemoryKeypress.js";
import { Dialog, Loading, Tabs, colors } from "../../ui/index.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import { DreamsSection } from "./DreamsSection.js";
import { MemoryFooter } from "./MemoryFooter.js";

const TABS = ["facts", "observations", "dreams"] as const;
type TabType = (typeof TABS)[number];

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<TabType>("facts");

  const { facts, observations, dreams, loading, error, setFacts, setObservations, setDreams, setError, reload } =
    useMemoryData(config);

  const factsTab = useFactsTab(config, facts, 80);
  const obsTab = useObservationsTab(config, observations, 80);
  const dreamsTab = useDreamsTab(config, dreams, 80);

  const { saving } = useMemoryKeypress({
    activeTab,
    setActiveTab,
    factsTab,
    obsTab,
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
      footer={<MemoryFooter activeTab={activeTab} factsTab={factsTab} obsTab={obsTab} dreamsTab={dreamsTab} />}
    >
      {({ width, height }) => {
        const sectionHeight = height - 2;
        const tab = activeTab === "facts" ? factsTab : activeTab === "observations" ? obsTab : dreamsTab;
        const sourceDisplay = activeTab === "facts" ? `src: ${factsTab.sourceFilter}` : "";
        const sortDisplay = `sort: ${tab.sortOrder}`;

        return (
          <>
            <box flexDirection="row" marginBottom={1} marginTop={1}>
              <Tabs
                tabs={TABS}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                labels={{ facts: "Facts", observations: "Observations", dreams: "Dreams" }}
              />
              <box flexGrow={1} />
              {sourceDisplay && (
                <box marginRight={3}>
                  <text><span fg={colors.text.disabled}>{sourceDisplay}</span></text>
                </box>
              )}
              <text><span fg={colors.text.disabled}>{sortDisplay}</span></text>
            </box>

            {activeTab === "facts" && (
              <FactsSection
                facts={factsTab.filteredFacts}
                selectedIndex={factsTab.selectedIndex}
                factDetails={factsTab.factDetails}
                detailsLoading={factsTab.detailsLoading}
                searchQuery={factsTab.searchQuery}
                searchMode={factsTab.searchMode}
                focusPane={factsTab.focusPane}
                height={sectionHeight}
                width={width}
                detailSection={factsTab.detailSection}
                textExpanded={factsTab.textExpanded}
                textScrollOffset={factsTab.textScrollOffset}
                entitiesIndex={factsTab.entitiesIndex}
                linkedIndex={factsTab.linkedIndex}
                editMode={factsTab.editMode}
                editText={factsTab.editText}
                cursorPos={factsTab.cursorPos}
                setEditText={factsTab.setEditText}
                setCursorPos={factsTab.setCursorPos}
                confirmDelete={factsTab.confirmDelete}
                saving={saving}
                onItemClick={factsTab.setSelectedIndex}
              />
            )}

            {activeTab === "observations" && (
              <ObservationsSection
                observations={obsTab.filteredObservations}
                selectedIndex={obsTab.selectedIndex}
                obsDetails={obsTab.obsDetails}
                detailsLoading={obsTab.detailsLoading}
                searchQuery={obsTab.searchQuery}
                searchMode={obsTab.searchMode}
                focusPane={obsTab.focusPane}
                height={sectionHeight}
                width={width}
                detailSection={obsTab.detailSection}
                textExpanded={obsTab.textExpanded}
                textScrollOffset={obsTab.textScrollOffset}
                factsIndex={obsTab.factsIndex}
                editMode={obsTab.editMode}
                editText={obsTab.editText}
                cursorPos={obsTab.cursorPos}
                setEditText={obsTab.setEditText}
                setCursorPos={obsTab.setCursorPos}
                confirmDelete={obsTab.confirmDelete}
                saving={saving}
                onItemClick={obsTab.setSelectedIndex}
              />
            )}

            {activeTab === "dreams" && (
              <DreamsSection
                dreams={dreamsTab.filteredDreams}
                selectedIndex={dreamsTab.selectedIndex}
                dreamDetails={dreamsTab.dreamDetails}
                detailsLoading={dreamsTab.detailsLoading}
                searchQuery={dreamsTab.searchQuery}
                searchMode={dreamsTab.searchMode}
                focusPane={dreamsTab.focusPane}
                height={sectionHeight}
                width={width}
                detailSection={dreamsTab.detailSection}
                textExpanded={dreamsTab.textExpanded}
                textScrollOffset={dreamsTab.textScrollOffset}
                factsIndex={dreamsTab.factsIndex}
                confirmDelete={dreamsTab.confirmDelete}
                onItemClick={dreamsTab.setSelectedIndex}
              />
            )}

          </>
        );
      }}
    </Dialog>
  );
}
