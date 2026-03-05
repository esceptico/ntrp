import { useState, useCallback } from "react";
import { useKeypress, type Key } from "./useKeypress.js";
import { useTextInput } from "./useTextInput.js";
import type { Config } from "../types.js";
import type { FactsTabState } from "./useFactsTab.js";
import type { ObservationsTabState } from "./useObservationsTab.js";
import type { DreamsTabState } from "./useDreamsTab.js";
import {
  updateFact,
  deleteFact,
  updateObservation,
  deleteObservation,
  deleteDream,
  type Fact,
  type Observation,
  type Dream,
} from "../api/client.js";

type TabType = "facts" | "observations" | "dreams";

interface UseMemoryKeypressOptions {
  activeTab: TabType;
  setActiveTab: React.Dispatch<React.SetStateAction<TabType>>;
  factsTab: FactsTabState;
  obsTab: ObservationsTabState;
  dreamsTab: DreamsTabState;
  config: Config;
  setFacts: React.Dispatch<React.SetStateAction<Fact[]>>;
  setObservations: React.Dispatch<React.SetStateAction<Observation[]>>;
  setDreams: React.Dispatch<React.SetStateAction<Dream[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  reload: () => void;
  onClose: () => void;
}

interface UseMemoryKeypressResult {
  saving: boolean;
}

export function useMemoryKeypress({
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
}: UseMemoryKeypressOptions): UseMemoryKeypressResult {
  const [saving, setSaving] = useState(false);

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

  const handleKeypress = useCallback(
    (key: Key) => {
      if (activeTab === "facts" && factsTab.focusPane === "details" && factsTab.factDetails) {
        if (factsTab.confirmDelete) {
          if (key.name === "y") {
            setSaving(true);
            deleteFact(config, factsTab.factDetails.fact.id)
              .then(() => {
                setFacts((prev: Fact[]) => prev.filter((f) => f.id !== factsTab.factDetails?.fact.id));
                factsTab.setConfirmDelete(false);
                factsTab.setFocusPane("list");
                factsTab.resetDetailState();
              })
              .catch((e: unknown) => setError(`Delete failed: ${e}`))
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
                setFacts((prev: Fact[]) =>
                  prev.map((f) => (f.id === result.fact.id ? { ...f, text: result.fact.text } : f))
                );
                factsTab.setEditMode(false);
                factsTab.setEditText("");
                factsTab.setCursorPos(0);
                reload();
              })
              .catch((e: unknown) => setError(`Save failed: ${e}`))
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
                setObservations((prev: Observation[]) => prev.filter((o) => o.id !== obsTab.obsDetails?.observation.id));
                obsTab.setConfirmDelete(false);
                obsTab.setFocusPane("list");
                obsTab.resetDetailState();
              })
              .catch((e: unknown) => setError(`Delete failed: ${e}`))
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
                setObservations((prev: Observation[]) =>
                  prev.map((o) => (o.id === result.id ? { ...o, summary: result.summary } : o))
                );
                obsTab.setEditMode(false);
                obsTab.setEditText("");
                obsTab.setCursorPos(0);
                reload();
              })
              .catch((e: unknown) => setError(`Save failed: ${e}`))
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
                setDreams((prev: Dream[]) => prev.filter((d) => d.id !== dreamsTab.dreamDetails?.dream.id));
                dreamsTab.setConfirmDelete(false);
                dreamsTab.setFocusPane("list");
                dreamsTab.resetDetailState();
              })
              .catch((e: unknown) => setError(`Delete failed: ${e}`))
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

  return { saving };
}
