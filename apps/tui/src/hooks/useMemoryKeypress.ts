import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useKeypress, type Key } from "./useKeypress.js";
import { useTextInput } from "./useTextInput.js";
import type { Config } from "../types.js";
import type { FactsTabState } from "./useFactsTab.js";
import type { ObservationsTabState } from "./useObservationsTab.js";
import { OBS_SECTIONS } from "../components/viewers/memory/ObservationDetailsView.js";
import type { PruneTabState } from "./usePruneTab.js";
import type { MemoryEventsTabState } from "./useMemoryEventsTab.js";
import type { MemoryAccessTabState } from "./useMemoryAccessTab.js";
import type { RecallInspectTabState } from "./useRecallInspectTab.js";
import {
  updateFact,
  deleteFact,
  updateObservation,
  deleteObservation,
  applyMemoryPrune,
  type Fact,
  type FactDetails,
  type Observation,
  type ObservationDetails,
  type MemoryPruneDryRun,
} from "../api/client.js";
import { MEMORY_TABS, type MemoryTabType } from "../lib/memoryTabs.js";

interface UseMemoryKeypressOptions {
  activeTab: MemoryTabType;
  setActiveTab: React.Dispatch<React.SetStateAction<MemoryTabType>>;
  recallTab: RecallInspectTabState;
  factsTab: FactsTabState;
  obsTab: ObservationsTabState;
  pruneTab: PruneTabState;
  pruneDryRun: MemoryPruneDryRun | null;
  accessTab: MemoryAccessTabState;
  eventsTab: MemoryEventsTabState;
  config: Config;
  setFacts: React.Dispatch<React.SetStateAction<Fact[]>>;
  setObservations: React.Dispatch<React.SetStateAction<Observation[]>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  reload: () => void;
  onClose: () => void;
}

interface UseMemoryKeypressResult {
  saving: boolean;
}

function isUpperA(key: Key): boolean {
  return key.sequence === "A" || (key.name === "a" && key.shift);
}

type SearchModeTab = { searchMode: boolean; handleKeys: (key: Key) => void };

export function useMemoryKeypress({
  activeTab,
  setActiveTab,
  recallTab,
  factsTab,
  obsTab,
  pruneTab,
  pruneDryRun,
  accessTab,
  eventsTab,
  config,
  setFacts,
  setObservations,
  setError,
  reload,
  onClose,
}: UseMemoryKeypressOptions): UseMemoryKeypressResult {
  const [saving, setSaving] = useState(false);
  const queryClient = useQueryClient();

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
      const activeFactTab = activeTab === "facts" ? factsTab : null;
      const setActiveFacts = setFacts;
      const openFact = (fact: Fact) => {
        setFacts((prev) => [fact, ...prev.filter((candidate) => candidate.id !== fact.id)]);
        factsTab.setSearchQuery("");
        factsTab.setSortOrder("recent");
        factsTab.setSelectedIndex(0);
        factsTab.resetDetailState();
        factsTab.setFocusPane("details");
        setActiveTab("facts");
      };
      const activeSearchTab: SearchModeTab | null =
        activeTab === "context" ? accessTab :
        activeTab === "facts" ? factsTab :
        activeTab === "observations" ? obsTab :
        activeTab === "prune" ? pruneTab :
        activeTab === "events" ? eventsTab :
        null;

      if (activeTab === "recall" && recallTab.inputActive) {
        recallTab.handleKeys(key);
        return;
      }

      if (activeSearchTab?.searchMode) {
        activeSearchTab.handleKeys(key);
        return;
      }

      if (activeFactTab?.focusPane === "details" && activeFactTab.factDetails) {
        if (activeFactTab.confirmDelete) {
          if (key.name === "y") {
            setSaving(true);
            deleteFact(config, activeFactTab.factDetails.fact.id)
              .then(() => {
                setActiveFacts((prev: Fact[]) => prev.filter((f) => f.id !== activeFactTab.factDetails?.fact.id));
                activeFactTab.setConfirmDelete(false);
                activeFactTab.setFocusPane("list");
                activeFactTab.resetDetailState();
                reload();
              })
              .catch((e: unknown) => setError(`Delete failed: ${e}`))
              .finally(() => setSaving(false));
          } else {
            activeFactTab.setConfirmDelete(false);
          }
          return;
        }

        if (activeFactTab.editMode) {
          if (key.ctrl && key.name === "s") {
            setSaving(true);
            updateFact(config, activeFactTab.factDetails.fact.id, activeFactTab.editText)
              .then((result) => {
                setActiveFacts((prev: Fact[]) =>
                  prev.map((f) => (f.id === result.fact.id ? result.fact : f))
                );
                queryClient.setQueryData<FactDetails>(["factDetails", result.fact.id], (prev) =>
                  prev ? { ...prev, fact: result.fact } : prev
                );
                activeFactTab.setEditMode(false);
                activeFactTab.setEditText("");
                activeFactTab.setCursorPos(0);
                reload();
              })
              .catch((e: unknown) => setError(`Save failed: ${e}`))
              .finally(() => setSaving(false));
            return;
          }
          if (key.name === "escape") {
            activeFactTab.setEditMode(false);
            activeFactTab.setEditText("");
            activeFactTab.setCursorPos(0);
            return;
          }
          if (factsTextInput.handleKey(key)) {
            return;
          }
          return;
        }

        if (key.name === "e") {
          activeFactTab.setEditMode(true);
          activeFactTab.setEditText(activeFactTab.factDetails.fact.text);
          activeFactTab.setCursorPos(activeFactTab.factDetails.fact.text.length);
          return;
        }
        if (key.name === "d" || key.name === "delete") {
          activeFactTab.setConfirmDelete(true);
          return;
        }
      }

      if (activeFactTab?.focusPane === "list" && activeFactTab.filteredFacts.length > 0) {
        const selectedFact = activeFactTab.filteredFacts[activeFactTab.selectedIndex];
        if (selectedFact) {
          if (key.name === "e") {
            activeFactTab.setFocusPane("details");
            activeFactTab.setEditMode(true);
            activeFactTab.setEditText(selectedFact.text);
            activeFactTab.setCursorPos(selectedFact.text.length);
            return;
          }
          if ((key.name === "d" || key.name === "delete") && activeFactTab.factDetails) {
            activeFactTab.setFocusPane("details");
            activeFactTab.setConfirmDelete(true);
            return;
          }
        }
      }

      if (activeTab === "observations" && obsTab.focusPane === "details" && obsTab.obsDetails) {
        if (key.name === "return" && obsTab.detailSection === OBS_SECTIONS.FACTS) {
          const fact = obsTab.obsDetails.supporting_facts[obsTab.factsIndex];
          if (fact) {
            openFact(fact);
            return;
          }
        }

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
                  prev.map((o) => (o.id === result.observation.id ? result.observation : o))
                );
                queryClient.setQueryData<ObservationDetails>(["obsDetails", result.observation.id], (prev) =>
                  prev ? { ...prev, observation: result.observation } : prev
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
          if ((key.name === "d" || key.name === "delete") && obsTab.obsDetails) {
            obsTab.setFocusPane("details");
            obsTab.setConfirmDelete(true);
            return;
          }
        }
      }

      if (activeTab === "prune" && !pruneTab.searchMode) {
        if (pruneTab.confirmApply) {
          const candidate = pruneTab.selectedCandidate;
          if (key.name === "y" && pruneDryRun) {
            const archiveAll = pruneTab.confirmApply === "all";
            const observationIds = archiveAll ? [] : candidate ? [candidate.id] : [];
            if (!archiveAll && observationIds.length === 0) {
              pruneTab.setConfirmApply(null);
              return;
            }
            setSaving(true);
            applyMemoryPrune(
              config,
              observationIds,
              {
                older_than_days: pruneDryRun.criteria.older_than_days,
                max_sources: pruneDryRun.criteria.max_sources,
              },
              archiveAll,
            )
              .then((result) => {
                pruneTab.setConfirmApply(null);
                if (result.archived === 0) {
                  setError("Prune skipped: candidate no longer matches review criteria");
                }
                reload();
              })
              .catch((e: unknown) => setError(`Prune failed: ${e}`))
              .finally(() => setSaving(false));
          } else {
            pruneTab.setConfirmApply(null);
          }
          return;
        }

        if (isUpperA(key) && pruneDryRun?.summary.total) {
          pruneTab.setConfirmApply("all");
          return;
        }
        if (key.name === "a" && pruneTab.selectedCandidate) {
          pruneTab.setConfirmApply("selected");
          return;
        }
      }

      const numericTab = Number(key.name);
      if (Number.isInteger(numericTab) && numericTab >= 1 && numericTab <= MEMORY_TABS.length) {
        setActiveTab(MEMORY_TABS[numericTab - 1]);
        return;
      }

      if (activeTab === "recall") {
        if (key.name === "escape") {
          onClose();
          return;
        }
        recallTab.handleKeys(key);
        return;
      }

      if (key.name === "r") { reload(); return; }

      if (key.name === "escape" || key.name === "q") {
        const tab = activeTab === "context" ? accessTab : activeTab === "facts" ? factsTab : activeTab === "observations" ? obsTab : activeTab === "prune" ? pruneTab : eventsTab;
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

      if (activeTab === "context") { accessTab.handleKeys(key); return; }
      if (activeTab === "events") { eventsTab.handleKeys(key); return; }
      if (activeTab === "prune") { pruneTab.handleKeys(key); return; }
      if (activeTab === "observations") { obsTab.handleKeys(key); return; }
      factsTab.handleKeys(key);
    },
    [activeTab, setActiveTab, recallTab, factsTab, obsTab, pruneTab, pruneDryRun, accessTab, eventsTab, onClose, reload, config, factsTextInput, obsTextInput, setSaving, setFacts, setObservations, setError, queryClient]
  );

  useKeypress(handleKeypress, { isActive: true });

  return { saving };
}
