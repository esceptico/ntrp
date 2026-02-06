import { useState, useEffect, useRef, useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import {
  getFacts,
  getObservations,
  type Fact,
  type Observation,
} from "../../../api/client.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Divider, Footer, Loading, Tabs, colors } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";
import { StatsView } from "./StatsView.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";

type TabType = "facts" | "observations" | "stats";
const TABS: TabType[] = ["facts", "observations", "stats"];

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);
  const viewHeight = VISIBLE_LINES;

  const [activeTab, setActiveTab] = useState<TabType>("facts");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);

  const loadedRef = useRef(false);

  const factsTab = useFactsTab(config, facts, contentWidth);
  const obsTab = useObservationsTab(config, observations, contentWidth);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;

    (async () => {
      setLoading(true);
      try {
        const [factsData, obsData] = await Promise.all([
          getFacts(config, 200),
          getObservations(config, 100),
        ]);
        setFacts(factsData.facts || []);
        setObservations(obsData.observations || []);
      } catch (e) {
        setError(`Failed to load: ${e}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [config]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "1") { setActiveTab("facts"); return; }
      if (key.name === "2") { setActiveTab("observations"); return; }
      if (key.name === "3") { setActiveTab("stats"); return; }

      if (key.name === "escape" || key.name === "q") {
        if (activeTab === "stats") { setActiveTab("facts"); return; }
        if (activeTab === "observations") {
          if (obsTab.focusPane === "details") {
            obsTab.setFocusPane("list");
            obsTab.resetDetailState();
            return;
          }
          if (obsTab.searchQuery) {
            obsTab.setSearchQuery("");
            obsTab.setSelectedIndex(0);
            return;
          }
          setActiveTab("facts");
          return;
        }
        if (factsTab.focusPane === "details") {
          factsTab.setFocusPane("list");
          factsTab.resetDetailState();
          return;
        }
        if (factsTab.searchQuery) {
          factsTab.setSearchQuery("");
          factsTab.setSelectedIndex(0);
          return;
        }
        onClose();
        return;
      }

      if (activeTab === "stats") return;
      if (activeTab === "observations") { obsTab.handleKeys(key); return; }
      factsTab.handleKeys(key);
    },
    [activeTab, factsTab, obsTab, onClose]
  );

  useKeypress(handleKeypress, { isActive: true });

  if (loading) return <Loading message="Loading memory..." />;

  if (error) {
    return (
      <Panel title="MEMORY" width={contentWidth}>
        <Text color={colors.text.muted}>{error}</Text>
        <Footer>Esc: close</Footer>
      </Panel>
    );
  }

  const footerText = {
    facts: `1-3: tabs │ ↑↓: navigate │ Tab: ${factsTab.focusPane === "list" ? "details" : "list"} │ ${factsTab.focusPane === "details" ? "Enter: expand" : "Type: search"} │ Esc: close`,
    observations: `1-3: tabs │ ↑↓: navigate │ Tab: ${obsTab.focusPane === "list" ? "details" : "list"} │ ${obsTab.focusPane === "details" ? "Enter: expand" : "Type: search"} │ Esc: back`,
    stats: "1-3: tabs │ Esc: back",
  };

  return (
    <Panel title="MEMORY" width={contentWidth}>
      <Tabs
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        labels={{ facts: "Facts", observations: "Observations", stats: "Stats" }}
      />

      {activeTab === "facts" && (
        <FactsSection
          facts={factsTab.filteredFacts}
          selectedIndex={factsTab.selectedIndex}
          factDetails={factsTab.factDetails}
          detailsLoading={factsTab.detailsLoading}
          searchQuery={factsTab.searchQuery}
          focusPane={factsTab.focusPane}
          visibleLines={viewHeight}
          width={contentWidth}
          detailSection={factsTab.detailSection}
          textExpanded={factsTab.textExpanded}
          textScrollOffset={factsTab.textScrollOffset}
          entitiesIndex={factsTab.entitiesIndex}
          linkedIndex={factsTab.linkedIndex}
        />
      )}

      {activeTab === "observations" && (
        <ObservationsSection
          observations={obsTab.filteredObservations}
          selectedIndex={obsTab.selectedIndex}
          obsDetails={obsTab.obsDetails}
          detailsLoading={obsTab.detailsLoading}
          searchQuery={obsTab.searchQuery}
          focusPane={obsTab.focusPane}
          visibleLines={viewHeight}
          width={contentWidth}
          detailSection={obsTab.detailSection}
          textExpanded={obsTab.textExpanded}
          textScrollOffset={obsTab.textScrollOffset}
          factsIndex={obsTab.factsIndex}
        />
      )}

      {activeTab === "stats" && (
        <Box height={viewHeight + 2} marginY={1}>
          <StatsView config={config} width={contentWidth} />
        </Box>
      )}

      <Divider width={contentWidth - 2} />
      <Footer>{footerText[activeTab]}</Footer>
    </Panel>
  );
}
