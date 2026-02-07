import { useState, useEffect, useRef, useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import {
  getFacts,
  getObservations,
  updateFact,
  deleteFact,
  updateObservation,
  deleteObservation,
  type Fact,
  type Observation,
} from "../../../api/client.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Divider, Footer, Loading, Tabs, colors } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";
import { StatsView } from "./StatsView.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";

const TABS = ["facts", "observations", "stats"] as const;
type TabType = (typeof TABS)[number];

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
  const [saving, setSaving] = useState(false);

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

  const reload = useCallback(() => {
    loadedRef.current = false;
    setLoading(true);
    (async () => {
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
      // Handle facts tab editing/deleting
      if (activeTab === "facts" && factsTab.focusPane === "details" && factsTab.factDetails) {
        if (factsTab.confirmDelete) {
          if (key.name === "y") {
            setSaving(true);
            deleteFact(config, factsTab.factDetails.fact.id)
              .then(() => {
                setFacts((prev) => prev.filter((f) => f.id !== factsTab.factDetails?.fact.id));
                factsTab.setConfirmDelete(false);
                factsTab.setFocusPane("list");
                factsTab.resetDetailState();
              })
              .catch((e) => setError(`Delete failed: ${e}`))
              .finally(() => setSaving(false));
          } else {
            factsTab.setConfirmDelete(false);
          }
          return;
        }

        if (factsTab.editMode) {
          if (key.ctrl && key.name === "s") {
            setSaving(true);
            updateFact(config, factsTab.factDetails.fact.id, factsTab.editText)
              .then((result) => {
                setFacts((prev) =>
                  prev.map((f) => (f.id === result.fact.id ? { ...f, text: result.fact.text } : f))
                );
                factsTab.setEditMode(false);
                factsTab.setEditText("");
                factsTab.setCursorPos(0);
                reload();
              })
              .catch((e) => setError(`Save failed: ${e}`))
              .finally(() => setSaving(false));
            return;
          }
          if (key.name === "escape") {
            factsTab.setEditMode(false);
            factsTab.setEditText("");
            factsTab.setCursorPos(0);
            return;
          }
          if (key.name === "left") {
            factsTab.setCursorPos((pos) => Math.max(0, pos - 1));
            return;
          }
          if (key.name === "right") {
            factsTab.setCursorPos((pos) => Math.min(factsTab.editText.length, pos + 1));
            return;
          }
          if (key.name === "home") {
            factsTab.setCursorPos(0);
            return;
          }
          if (key.name === "end") {
            factsTab.setCursorPos(factsTab.editText.length);
            return;
          }
          if (key.name === "backspace") {
            if (factsTab.cursorPos > 0) {
              factsTab.setEditText((prev) => prev.slice(0, factsTab.cursorPos - 1) + prev.slice(factsTab.cursorPos));
              factsTab.setCursorPos((pos) => pos - 1);
            }
            return;
          }
          if (key.name === "delete") {
            if (factsTab.cursorPos < factsTab.editText.length) {
              factsTab.setEditText((prev) => prev.slice(0, factsTab.cursorPos) + prev.slice(factsTab.cursorPos + 1));
            }
            return;
          }
          if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
            const char = key.name === "return" ? "\n" : key.name === "space" ? " " : key.sequence;
            factsTab.setEditText((prev) => prev.slice(0, factsTab.cursorPos) + char + prev.slice(factsTab.cursorPos));
            factsTab.setCursorPos((pos) => pos + 1);
            return;
          }
          return;
        }

        if (key.name === "e") {
          factsTab.setEditMode(true);
          factsTab.setEditText(factsTab.factDetails.fact.text);
          factsTab.setCursorPos(factsTab.factDetails.fact.text.length);
          return;
        }
        if (key.name === "d" || key.name === "delete") {
          factsTab.setConfirmDelete(true);
          return;
        }
      }

      // Handle edit/delete from list view
      if (activeTab === "facts" && factsTab.focusPane === "list" && factsTab.filteredFacts.length > 0) {
        const selectedFact = factsTab.filteredFacts[factsTab.selectedIndex];
        if (selectedFact) {
          if (key.name === "e") {
            factsTab.setFocusPane("details");
            factsTab.setEditMode(true);
            factsTab.setEditText(selectedFact.text);
            factsTab.setCursorPos(selectedFact.text.length);
            return;
          }
          if (key.name === "d" || key.name === "delete") {
            factsTab.setFocusPane("details");
            factsTab.setConfirmDelete(true);
            return;
          }
        }
      }

      // Handle observations tab editing/deleting
      if (activeTab === "observations" && obsTab.focusPane === "details" && obsTab.obsDetails) {
        if (obsTab.confirmDelete) {
          if (key.name === "y") {
            setSaving(true);
            deleteObservation(config, obsTab.obsDetails.observation.id)
              .then(() => {
                setObservations((prev) => prev.filter((o) => o.id !== obsTab.obsDetails?.observation.id));
                obsTab.setConfirmDelete(false);
                obsTab.setFocusPane("list");
                obsTab.resetDetailState();
              })
              .catch((e) => setError(`Delete failed: ${e}`))
              .finally(() => setSaving(false));
          } else {
            obsTab.setConfirmDelete(false);
          }
          return;
        }

        if (obsTab.editMode) {
          if (key.ctrl && key.name === "s") {
            setSaving(true);
            updateObservation(config, obsTab.obsDetails.observation.id, obsTab.editText)
              .then((result) => {
                setObservations((prev) =>
                  prev.map((o) => (o.id === result.id ? { ...o, summary: result.summary } : o))
                );
                obsTab.setEditMode(false);
                obsTab.setEditText("");
                obsTab.setCursorPos(0);
                reload();
              })
              .catch((e) => setError(`Save failed: ${e}`))
              .finally(() => setSaving(false));
            return;
          }
          if (key.name === "escape") {
            obsTab.setEditMode(false);
            obsTab.setEditText("");
            obsTab.setCursorPos(0);
            return;
          }
          if (key.name === "left") {
            obsTab.setCursorPos((pos) => Math.max(0, pos - 1));
            return;
          }
          if (key.name === "right") {
            obsTab.setCursorPos((pos) => Math.min(obsTab.editText.length, pos + 1));
            return;
          }
          if (key.name === "home") {
            obsTab.setCursorPos(0);
            return;
          }
          if (key.name === "end") {
            obsTab.setCursorPos(obsTab.editText.length);
            return;
          }
          if (key.name === "backspace") {
            if (obsTab.cursorPos > 0) {
              obsTab.setEditText((prev) => prev.slice(0, obsTab.cursorPos - 1) + prev.slice(obsTab.cursorPos));
              obsTab.setCursorPos((pos) => pos - 1);
            }
            return;
          }
          if (key.name === "delete") {
            if (obsTab.cursorPos < obsTab.editText.length) {
              obsTab.setEditText((prev) => prev.slice(0, obsTab.cursorPos) + prev.slice(obsTab.cursorPos + 1));
            }
            return;
          }
          if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
            const char = key.name === "return" ? "\n" : key.name === "space" ? " " : key.sequence;
            obsTab.setEditText((prev) => prev.slice(0, obsTab.cursorPos) + char + prev.slice(obsTab.cursorPos));
            obsTab.setCursorPos((pos) => pos + 1);
            return;
          }
          return;
        }

        if (key.name === "e") {
          obsTab.setEditMode(true);
          obsTab.setEditText(obsTab.obsDetails.observation.summary);
          obsTab.setCursorPos(obsTab.obsDetails.observation.summary.length);
          return;
        }
        if (key.name === "d" || key.name === "delete") {
          obsTab.setConfirmDelete(true);
          return;
        }
      }

      // Handle edit/delete from list view
      if (activeTab === "observations" && obsTab.focusPane === "list" && obsTab.filteredObservations.length > 0) {
        const selectedObs = obsTab.filteredObservations[obsTab.selectedIndex];
        if (selectedObs) {
          if (key.name === "e") {
            obsTab.setFocusPane("details");
            obsTab.setEditMode(true);
            obsTab.setEditText(selectedObs.summary);
            obsTab.setCursorPos(selectedObs.summary.length);
            return;
          }
          if (key.name === "d" || key.name === "delete") {
            obsTab.setFocusPane("details");
            obsTab.setConfirmDelete(true);
            return;
          }
        }
      }

      if (key.name === "1") { setActiveTab("facts"); return; }
      if (key.name === "2") { setActiveTab("observations"); return; }
      if (key.name === "3") { setActiveTab("stats"); return; }
      if (key.name === "r") { reload(); return; }

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
          onClose();
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
    [activeTab, factsTab, obsTab, onClose, reload, config]
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

  const getFooterText = (): string => {
    if (activeTab === "stats") return "1-3: tabs │ Esc: back";

    if (activeTab === "facts") {
      if (factsTab.editMode) return "Ctrl+S: save │ Esc: cancel │ ←→: move cursor │ Home/End: start/end";
      if (factsTab.confirmDelete) return "y: confirm │ any key: cancel";
      if (factsTab.focusPane === "details") {
        return "1-3: tabs │ ↑↓: navigate │ Tab: list │ Enter: expand │ e: edit │ d: delete │ Esc: back";
      }
      return "1-3: tabs │ ↑↓: navigate │ Tab: details │ e: edit │ d: delete │ Type: search │ Esc: close";
    }

    if (activeTab === "observations") {
      if (obsTab.editMode) return "Ctrl+S: save │ Esc: cancel │ ←→: move cursor │ Home/End: start/end";
      if (obsTab.confirmDelete) return "y: confirm │ any key: cancel";
      if (obsTab.focusPane === "details") {
        return "1-3: tabs │ ↑↓: navigate │ Tab: list │ Enter: expand │ e: edit │ d: delete │ Esc: back";
      }
      return "1-3: tabs │ ↑↓: navigate │ Tab: details │ e: edit │ d: delete │ Type: search │ Esc: close";
    }

    return "";
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
          editMode={factsTab.editMode}
          editText={factsTab.editText}
          cursorPos={factsTab.cursorPos}
          confirmDelete={factsTab.confirmDelete}
          saving={saving}
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
          editMode={obsTab.editMode}
          editText={obsTab.editText}
          cursorPos={obsTab.cursorPos}
          confirmDelete={obsTab.confirmDelete}
          saving={saving}
        />
      )}

      {activeTab === "stats" && (
        <Box height={viewHeight + 4} marginY={1}>
          <StatsView config={config} width={contentWidth} />
        </Box>
      )}

      <Divider width={contentWidth - 2} />
      <Footer>{getFooterText()}</Footer>
    </Panel>
  );
}
