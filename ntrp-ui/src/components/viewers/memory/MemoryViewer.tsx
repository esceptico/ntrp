import React, { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../../../types.js";
import { useKeypress, useTextInput, type Key } from "../../../hooks/index.js";
import { useFactsTab } from "../../../hooks/useFactsTab.js";
import { useObservationsTab } from "../../../hooks/useObservationsTab.js";
import { useDreamsTab } from "../../../hooks/useDreamsTab.js";
import {
  getFacts,
  getObservations,
  getDreams,
  updateFact,
  deleteFact,
  updateObservation,
  deleteObservation,
  deleteDream,
  type Fact,
  type Observation,
  type Dream,
} from "../../../api/client.js";
import { Dialog, Loading, Tabs, colors, Hints } from "../../ui/index.js";
import { FactsSection } from "./FactsSection.js";
import { ObservationsSection } from "./ObservationsSection.js";
import { DreamsSection } from "./DreamsSection.js";

const TABS = ["facts", "observations", "dreams"] as const;
type TabType = (typeof TABS)[number];

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<TabType>("facts");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [dreams, setDreams] = useState<Dream[]>([]);
  const [saving, setSaving] = useState(false);

  const loadedRef = useRef(false);

  const factsTab = useFactsTab(config, facts, 80);
  const obsTab = useObservationsTab(config, observations, 80);
  const dreamsTab = useDreamsTab(config, dreams, 80);

  const factsTextInput = useTextInput({
    text: factsTab.editText,
    cursorPos: factsTab.cursorPos,
    setText: factsTab.setEditText,
    setCursorPos: factsTab.setCursorPos,
  });

  const obsTextInput = useTextInput({
    text: obsTab.editText,
    cursorPos: obsTab.cursorPos,
    setText: obsTab.setEditText,
    setCursorPos: obsTab.setCursorPos,
  });

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;

    (async () => {
      setLoading(true);
      try {
        const [factsData, obsData, dreamsData] = await Promise.all([
          getFacts(config, 200),
          getObservations(config, 100),
          getDreams(config, 50),
        ]);
        setFacts(factsData.facts || []);
        setObservations(obsData.observations || []);
        setDreams(dreamsData.dreams || []);
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
        const [factsData, obsData, dreamsData] = await Promise.all([
          getFacts(config, 200),
          getObservations(config, 100),
          getDreams(config, 50),
        ]);
        setFacts(factsData.facts || []);
        setObservations(obsData.observations || []);
        setDreams(dreamsData.dreams || []);
      } catch (e) {
        setError(`Failed to load: ${e}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [config]);

  const handleKeypress = useCallback(
    (key: Key) => {
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
          if (factsTextInput.handleKey(key)) {
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
          if (obsTextInput.handleKey(key)) {
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

      // Dreams tab — delete only (no edit)
      if (activeTab === "dreams" && dreamsTab.focusPane === "details" && dreamsTab.dreamDetails) {
        if (dreamsTab.confirmDelete) {
          if (key.name === "y") {
            setSaving(true);
            deleteDream(config, dreamsTab.dreamDetails.dream.id)
              .then(() => {
                setDreams((prev) => prev.filter((d) => d.id !== dreamsTab.dreamDetails?.dream.id));
                dreamsTab.setConfirmDelete(false);
                dreamsTab.setFocusPane("list");
                dreamsTab.resetDetailState();
              })
              .catch((e) => setError(`Delete failed: ${e}`))
              .finally(() => setSaving(false));
          } else {
            dreamsTab.setConfirmDelete(false);
          }
          return;
        }

        if (key.name === "d" || key.name === "delete") {
          dreamsTab.setConfirmDelete(true);
          return;
        }
      }

      if (activeTab === "dreams" && dreamsTab.focusPane === "list" && dreamsTab.filteredDreams.length > 0) {
        if (key.name === "d" || key.name === "delete") {
          dreamsTab.setFocusPane("details");
          dreamsTab.setConfirmDelete(true);
          return;
        }
      }

      if (key.name === "1") { setActiveTab("facts"); return; }
      if (key.name === "2") { setActiveTab("observations"); return; }
      if (key.name === "3") { setActiveTab("dreams"); return; }
      if (key.name === "r") { reload(); return; }

      if (key.name === "escape" || key.name === "q") {
        const tab = activeTab === "facts" ? factsTab : activeTab === "observations" ? obsTab : dreamsTab;
        if (tab.searchMode) {
          tab.handleKeys(key);
          return;
        }
        if (tab.focusPane === "details") {
          tab.setFocusPane("list");
          tab.resetDetailState();
          return;
        }
        if (tab.searchQuery) {
          tab.setSearchQuery("");
          tab.setSelectedIndex(0);
          return;
        }
        onClose();
        return;
      }

      if (activeTab === "dreams") { dreamsTab.handleKeys(key); return; }
      if (activeTab === "observations") { obsTab.handleKeys(key); return; }
      factsTab.handleKeys(key);
    },
    [activeTab, factsTab, obsTab, dreamsTab, onClose, reload, config, factsTextInput, obsTextInput, setSaving, setFacts, setObservations, setDreams, setError]
  );

  useKeypress(handleKeypress, { isActive: true });

  const getFooter = (): React.ReactNode => {
    if (activeTab === "dreams") {
      if (dreamsTab.confirmDelete) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
      if (dreamsTab.focusPane === "details") {
        return <Hints items={[["↑↓", "navigate"], ["tab", "list"], ["enter", "expand"], ["d", "del"]]} />;
      }
      if (dreamsTab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
      return <Hints items={[["↑↓", "navigate"], ["tab", "details"], ["/", "search"], ["d", "del"], ["o", "sort"]]} />;
    }

    const tab = activeTab === "facts" ? factsTab : obsTab;

    if (tab.editMode) return <Hints items={[["^S", "save"], ["esc", "cancel"], ["←→", "cursor"]]} />;
    if (tab.confirmDelete) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
    if (tab.focusPane === "details") {
      return <Hints items={[["↑↓", "navigate"], ["tab", "list"], ["enter", "expand"], ["e", "edit"], ["d", "del"]]} />;
    }
    if (tab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
    const listHints: [string, string][] = [
      ["↑↓", "navigate"],
      ["tab", "details"],
      ["/", "search"],
      ["e", "edit"],
      ["d", "del"],
      ...(activeTab === "facts" ? [["s", "source"] as [string, string]] : []),
      ["o", "sort"],
    ];
    return <Hints items={listHints} />;
  };

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
      footer={getFooter()}
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
              />
            )}

          </>
        );
      }}
    </Dialog>
  );
}
