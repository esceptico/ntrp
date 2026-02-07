import { useState, useEffect, useCallback, useMemo } from "react";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import {
  getFactDetails,
  type Fact,
  type FactDetails,
} from "../api/client.js";
import { getTextMaxScroll } from "../components/ui/index.js";
import {
  FACT_SECTIONS,
  type FactDetailSection,
  getFactSectionMaxIndex,
} from "../components/viewers/memory/FactDetailsView.js";

export interface FactsTabState {
  filteredFacts: Fact[];
  selectedIndex: number;
  factDetails: FactDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  focusPane: "list" | "details";
  detailSection: FactDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  entitiesIndex: number;
  linkedIndex: number;
  editMode: boolean;
  editText: string;
  confirmDelete: boolean;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: (i: number) => void;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
}

export function useFactsTab(
  config: Config,
  facts: Fact[],
  contentWidth: number
): FactsTabState {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [factDetails, setFactDetails] = useState<FactDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [focusPane, setFocusPane] = useState<"list" | "details">("list");

  const [detailSection, setDetailSection] = useState<FactDetailSection>(FACT_SECTIONS.TEXT);
  const [textExpanded, setTextExpanded] = useState(false);
  const [textScrollOffset, setTextScrollOffset] = useState(0);
  const [entitiesIndex, setEntitiesIndex] = useState(0);
  const [linkedIndex, setLinkedIndex] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const filteredFacts = useMemo(
    () =>
      searchQuery
        ? facts.filter((f) => f.text.toLowerCase().includes(searchQuery.toLowerCase()))
        : facts,
    [facts, searchQuery]
  );

  const selectedFactId = filteredFacts[selectedIndex]?.id;

  const resetDetailState = useCallback(() => {
    setDetailSection(FACT_SECTIONS.TEXT);
    setTextExpanded(false);
    setTextScrollOffset(0);
    setEntitiesIndex(0);
    setLinkedIndex(0);
    setEditMode(false);
    setEditText("");
    setConfirmDelete(false);
  }, []);

  useEffect(() => {
    if (!selectedFactId) {
      setFactDetails(null);
      return;
    }
    setDetailsLoading(true);
    resetDetailState();
    getFactDetails(config, selectedFactId)
      .then(setFactDetails)
      .catch(() => setFactDetails(null))
      .finally(() => setDetailsLoading(false));
  }, [selectedFactId, config, resetDetailState]);

  const handleKeys = useCallback(
    (key: Key) => {
      if (key.name === "tab") {
        setFocusPane((p) => (p === "list" ? "details" : "list"));
        if (focusPane === "list") {
          resetDetailState();
        }
        return;
      }
      if (focusPane === "details") {
        if (key.name === "return" && detailSection === FACT_SECTIONS.TEXT) {
          setTextExpanded((e) => !e);
          setTextScrollOffset(0);
          return;
        }
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
      focusPane,
      detailSection,
      textExpanded,
      textScrollOffset,
      entitiesIndex,
      linkedIndex,
      factDetails,
      filteredFacts.length,
      contentWidth,
      resetDetailState,
    ]
  );

  return {
    filteredFacts,
    selectedIndex,
    factDetails,
    detailsLoading,
    searchQuery,
    focusPane,
    detailSection,
    textExpanded,
    textScrollOffset,
    entitiesIndex,
    linkedIndex,
    editMode,
    editText,
    confirmDelete,
    handleKeys,
    setSearchQuery,
    setSelectedIndex,
    setFocusPane,
    resetDetailState,
    setEditMode,
    setEditText,
    setConfirmDelete,
  };
}
