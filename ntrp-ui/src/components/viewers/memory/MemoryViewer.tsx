import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import {
  getFacts,
  getFactDetails,
  getObservations,
  getObservationDetails,
  type Fact,
  type FactDetails,
  type Observation,
  type ObservationDetails,
} from "../../../api/client.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Divider, Footer, Loading, Tabs, colors, getTextMaxScroll } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";
import { StatsView } from "./StatsView.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import {
  FACT_SECTIONS,
  type FactDetailSection,
  getFactSectionMaxIndex,
} from "./FactDetailsView.js";
import {
  OBS_SECTIONS,
  type ObsDetailSection,
  getObsSectionMaxIndex,
} from "./ObservationDetailsView.js";

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

  // Facts state
  const [facts, setFacts] = useState<Fact[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [factDetails, setFactDetails] = useState<FactDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [focusPane, setFocusPane] = useState<"list" | "details">("list");

  // Facts detail section state
  const [detailSection, setDetailSection] = useState<FactDetailSection>(FACT_SECTIONS.TEXT);
  const [textExpanded, setTextExpanded] = useState(false);
  const [textScrollOffset, setTextScrollOffset] = useState(0);
  const [entitiesIndex, setEntitiesIndex] = useState(0);
  const [linkedIndex, setLinkedIndex] = useState(0);

  // Observations state
  const [observations, setObservations] = useState<Observation[]>([]);
  const [obsSelectedIndex, setObsSelectedIndex] = useState(0);
  const [obsDetails, setObsDetails] = useState<ObservationDetails | null>(null);
  const [obsDetailsLoading, setObsDetailsLoading] = useState(false);
  const [obsSearchQuery, setObsSearchQuery] = useState("");
  const [obsFocusPane, setObsFocusPane] = useState<"list" | "details">("list");

  // Observations detail section state
  const [obsDetailSection, setObsDetailSection] = useState<ObsDetailSection>(OBS_SECTIONS.TEXT);
  const [obsTextExpanded, setObsTextExpanded] = useState(false);
  const [obsTextScrollOffset, setObsTextScrollOffset] = useState(0);
  const [obsFactsIndex, setObsFactsIndex] = useState(0);

  const loadedRef = useRef(false);

  const filteredFacts = useMemo(
    () =>
      searchQuery
        ? facts.filter((f) => f.text.toLowerCase().includes(searchQuery.toLowerCase()))
        : facts,
    [facts, searchQuery]
  );

  const filteredObservations = useMemo(
    () =>
      obsSearchQuery
        ? observations.filter((o) => o.summary.toLowerCase().includes(obsSearchQuery.toLowerCase()))
        : observations,
    [observations, obsSearchQuery]
  );

  const selectedFactId = filteredFacts[selectedIndex]?.id;
  const selectedObsId = filteredObservations[obsSelectedIndex]?.id;

  // Reset detail section state when selection changes
  const resetFactDetailState = useCallback(() => {
    setDetailSection(FACT_SECTIONS.TEXT);
    setTextExpanded(false);
    setTextScrollOffset(0);
    setEntitiesIndex(0);
    setLinkedIndex(0);
  }, []);

  const resetObsDetailState = useCallback(() => {
    setObsDetailSection(OBS_SECTIONS.TEXT);
    setObsTextExpanded(false);
    setObsTextScrollOffset(0);
    setObsFactsIndex(0);
  }, []);

  // Load initial data
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

  // Load fact details when selection changes
  useEffect(() => {
    if (!selectedFactId) {
      setFactDetails(null);
      return;
    }
    setDetailsLoading(true);
    resetFactDetailState();
    getFactDetails(config, selectedFactId)
      .then(setFactDetails)
      .catch(() => setFactDetails(null))
      .finally(() => setDetailsLoading(false));
  }, [selectedFactId, config, resetFactDetailState]);

  // Load observation details when selection changes
  useEffect(() => {
    if (!selectedObsId) {
      setObsDetails(null);
      return;
    }
    setObsDetailsLoading(true);
    resetObsDetailState();
    getObservationDetails(config, selectedObsId)
      .then(setObsDetails)
      .catch(() => setObsDetails(null))
      .finally(() => setObsDetailsLoading(false));
  }, [selectedObsId, config, resetObsDetailState]);

  const handleKeypress = useCallback(
    (key: Key) => {
      // Tab shortcuts
      if (key.name === "1") {
        setActiveTab("facts");
        return;
      }
      if (key.name === "2") {
        setActiveTab("observations");
        return;
      }
      if (key.name === "3") {
        setActiveTab("stats");
        return;
      }

      // Escape/back handling
      if (key.name === "escape" || key.name === "q") {
        if (activeTab === "stats") {
          setActiveTab("facts");
          return;
        }
        if (activeTab === "observations") {
          if (obsFocusPane === "details") {
            setObsFocusPane("list");
            resetObsDetailState();
            return;
          }
          if (obsSearchQuery) {
            setObsSearchQuery("");
            setObsSelectedIndex(0);
            return;
          }
          setActiveTab("facts");
          return;
        }
        if (focusPane === "details") {
          setFocusPane("list");
          resetFactDetailState();
          return;
        }
        if (searchQuery) {
          setSearchQuery("");
          setSelectedIndex(0);
          return;
        }
        onClose();
        return;
      }

      if (activeTab === "stats") return;

      // Observations tab keys
      if (activeTab === "observations") {
        if (key.name === "tab") {
          setObsFocusPane((p) => (p === "list" ? "details" : "list"));
          if (obsFocusPane === "list") {
            resetObsDetailState();
          }
          return;
        }
        if (obsFocusPane === "details") {
          // Enter toggles text expansion
          if (key.name === "return" && obsDetailSection === OBS_SECTIONS.TEXT) {
            setObsTextExpanded((e) => !e);
            setObsTextScrollOffset(0);
            return;
          }
          // Navigation within details
          if (key.name === "up" || key.name === "k") {
            if (obsDetailSection === OBS_SECTIONS.TEXT) {
              if (obsTextExpanded && obsTextScrollOffset > 0) {
                setObsTextScrollOffset((s) => s - 1);
              }
              return;
            }
            if (obsDetailSection === OBS_SECTIONS.FACTS) {
              if (obsFactsIndex > 0) {
                setObsFactsIndex((i) => i - 1);
              } else {
                // Move to previous section
                setObsDetailSection(OBS_SECTIONS.TEXT);
              }
              return;
            }
          }
          if (key.name === "down" || key.name === "j") {
            if (obsDetailSection === OBS_SECTIONS.TEXT) {
              if (obsTextExpanded && obsDetails) {
                const listWidth = Math.min(45, Math.max(30, Math.floor(contentWidth * 0.4)));
                const detailWidth = Math.max(0, contentWidth - listWidth - 1) - 2;
                const maxScroll = getTextMaxScroll(obsDetails.observation.summary, detailWidth, 5);
                if (obsTextScrollOffset < maxScroll) {
                  setObsTextScrollOffset((s) => s + 1);
                  return;
                }
              }
              // Move to facts section
              setObsDetailSection(OBS_SECTIONS.FACTS);
              setObsFactsIndex(0);
              return;
            }
            if (obsDetailSection === OBS_SECTIONS.FACTS) {
              const maxIndex = getObsSectionMaxIndex(obsDetails, OBS_SECTIONS.FACTS);
              if (obsFactsIndex < maxIndex) {
                setObsFactsIndex((i) => i + 1);
              }
              return;
            }
          }
          return;
        }
        // List pane focused
        if (key.name === "backspace") {
          setObsSearchQuery((q) => q.slice(0, -1));
          setObsSelectedIndex(0);
          return;
        }
        if (key.name === "up" || key.name === "k") {
          setObsSelectedIndex((i) => Math.max(0, i - 1));
          return;
        }
        if (key.name === "down" || key.name === "j") {
          setObsSelectedIndex((i) => Math.min(filteredObservations.length - 1, i + 1));
          return;
        }
        if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
          const char = key.name === "space" ? " " : key.sequence;
          setObsSearchQuery((q) => q + char);
          setObsSelectedIndex(0);
        }
        return;
      }

      // Facts tab keys
      if (key.name === "tab") {
        setFocusPane((p) => (p === "list" ? "details" : "list"));
        if (focusPane === "list") {
          resetFactDetailState();
        }
        return;
      }
      if (focusPane === "details") {
        // Enter toggles text expansion
        if (key.name === "return" && detailSection === FACT_SECTIONS.TEXT) {
          setTextExpanded((e) => !e);
          setTextScrollOffset(0);
          return;
        }
        // Navigation within details
        if (key.name === "up" || key.name === "k") {
          if (detailSection === FACT_SECTIONS.TEXT) {
            if (textExpanded && textScrollOffset > 0) {
              setTextScrollOffset((s) => s - 1);
            }
            return;
          }
          if (detailSection === FACT_SECTIONS.ENTITIES) {
            if (entitiesIndex > 0) {
              setEntitiesIndex((i) => i - 1);
            } else {
              setDetailSection(FACT_SECTIONS.TEXT);
            }
            return;
          }
          if (detailSection === FACT_SECTIONS.LINKED) {
            if (linkedIndex > 0) {
              setLinkedIndex((i) => i - 1);
            } else {
              setDetailSection(FACT_SECTIONS.ENTITIES);
              const maxEntities = getFactSectionMaxIndex(factDetails, FACT_SECTIONS.ENTITIES);
              setEntitiesIndex(maxEntities);
            }
            return;
          }
        }
        if (key.name === "down" || key.name === "j") {
          if (detailSection === FACT_SECTIONS.TEXT) {
            if (textExpanded && factDetails) {
              const listWidth = Math.min(45, Math.max(30, Math.floor(contentWidth * 0.4)));
              const detailWidth = Math.max(0, contentWidth - listWidth - 1) - 2;
              const maxScroll = getTextMaxScroll(factDetails.fact.text, detailWidth, 5);
              if (textScrollOffset < maxScroll) {
                setTextScrollOffset((s) => s + 1);
                return;
              }
            }
            setDetailSection(FACT_SECTIONS.ENTITIES);
            setEntitiesIndex(0);
            return;
          }
          if (detailSection === FACT_SECTIONS.ENTITIES) {
            const maxIndex = getFactSectionMaxIndex(factDetails, FACT_SECTIONS.ENTITIES);
            if (entitiesIndex < maxIndex) {
              setEntitiesIndex((i) => i + 1);
            } else {
              setDetailSection(FACT_SECTIONS.LINKED);
              setLinkedIndex(0);
            }
            return;
          }
          if (detailSection === FACT_SECTIONS.LINKED) {
            const maxIndex = getFactSectionMaxIndex(factDetails, FACT_SECTIONS.LINKED);
            if (linkedIndex < maxIndex) {
              setLinkedIndex((i) => i + 1);
            }
            return;
          }
        }
        return;
      }
      // List pane focused
      if (key.name === "backspace") {
        setSearchQuery((q) => q.slice(0, -1));
        setSelectedIndex(0);
        return;
      }
      if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(filteredFacts.length - 1, i + 1));
        return;
      }
      if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
        const char = key.name === "space" ? " " : key.sequence;
        setSearchQuery((q) => q + char);
        setSelectedIndex(0);
      }
    },
    [
      activeTab,
      focusPane,
      obsFocusPane,
      searchQuery,
      obsSearchQuery,
      filteredFacts.length,
      filteredObservations.length,
      onClose,
      detailSection,
      textExpanded,
      textScrollOffset,
      entitiesIndex,
      linkedIndex,
      factDetails,
      obsDetailSection,
      obsTextExpanded,
      obsTextScrollOffset,
      obsFactsIndex,
      obsDetails,
      contentWidth,
      resetFactDetailState,
      resetObsDetailState,
    ]
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
    facts: `1-3: tabs │ ↑↓: navigate │ Tab: ${focusPane === "list" ? "details" : "list"} │ ${focusPane === "details" ? "Enter: expand" : "Type: search"} │ Esc: close`,
    observations: `1-3: tabs │ ↑↓: navigate │ Tab: ${obsFocusPane === "list" ? "details" : "list"} │ ${obsFocusPane === "details" ? "Enter: expand" : "Type: search"} │ Esc: back`,
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
          facts={filteredFacts}
          selectedIndex={selectedIndex}
          factDetails={factDetails}
          detailsLoading={detailsLoading}
          searchQuery={searchQuery}
          focusPane={focusPane}
          visibleLines={viewHeight}
          width={contentWidth}
          detailSection={detailSection}
          textExpanded={textExpanded}
          textScrollOffset={textScrollOffset}
          entitiesIndex={entitiesIndex}
          linkedIndex={linkedIndex}
        />
      )}

      {activeTab === "observations" && (
        <ObservationsSection
          observations={filteredObservations}
          selectedIndex={obsSelectedIndex}
          obsDetails={obsDetails}
          detailsLoading={obsDetailsLoading}
          searchQuery={obsSearchQuery}
          focusPane={obsFocusPane}
          visibleLines={viewHeight}
          width={contentWidth}
          detailSection={obsDetailSection}
          textExpanded={obsTextExpanded}
          textScrollOffset={obsTextScrollOffset}
          factsIndex={obsFactsIndex}
        />
      )}

      {activeTab === "stats" && (
        <Box height={viewHeight + 2} marginY={1}>
          <StatsView
            config={config}
            width={contentWidth}
            height={viewHeight}
            isActive={true}
            onClose={() => setActiveTab("facts")}
          />
        </Box>
      )}

      <Divider width={contentWidth - 2} />
      <Footer>{footerText[activeTab]}</Footer>
    </Panel>
  );
}
