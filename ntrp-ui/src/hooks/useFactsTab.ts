import { useState, useCallback, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import { getFactDetails, type Fact, type FactDetails } from "../api/client.js";
import { FACT_SECTIONS, type FactDetailSection, getFactSectionMaxIndex } from "../components/viewers/memory/FactDetailsView.js";
import { useListDetail, type SortOrder, type ListKeyHelpers } from "./useListDetail.js";

export type { SortOrder };

const filterFact = (f: Fact, q: string) => f.text.toLowerCase().includes(q);

export interface FactsTabState {
  filteredFacts: Fact[];
  selectedIndex: number;
  factDetails: FactDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  detailSection: FactDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  entitiesIndex: number;
  linkedIndex: number;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  confirmDelete: boolean;
  sourceFilter: string;
  sortOrder: SortOrder;
  availableSources: string[];
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: (i: number) => void;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setCursorPos: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
}

export function useFactsTab(
  config: Config,
  facts: Fact[],
  contentWidth: number
): FactsTabState {
  const [sourceFilter, setSourceFilter] = useState("all");
  const detailsRef = useRef<FactDetails | null>(null);

  const availableSources = useMemo(() => {
    const sources = new Set(facts.map((f) => f.source_type));
    return ["all", ...Array.from(sources).sort()];
  }, [facts]);

  const sourceFiltered = useMemo(() => {
    if (sourceFilter === "all") return facts;
    return facts.filter((f) => f.source_type === sourceFilter);
  }, [facts, sourceFilter]);

  const onListKey = useCallback((key: Key, { setSelectedIndex }: ListKeyHelpers) => {
    if (key.name === "s") {
      setSourceFilter((current) => {
        const idx = availableSources.indexOf(current);
        return availableSources[(idx + 1) % availableSources.length];
      });
      setSelectedIndex(0);
      return true;
    }
    return false;
  }, [availableSources]);

  const ld = useListDetail({
    items: sourceFiltered,
    filterFn: filterFact,
    sectionCount: 3,
    getSectionMaxIndex: (section: number) => getFactSectionMaxIndex(detailsRef.current, section as FactDetailSection),
    getScrollText: (): string | undefined => detailsRef.current?.fact.text,
    contentWidth,
    onListKey,
  });

  const currentId = ld.filtered[ld.selectedIndex]?.id;

  const { data: factDetails = null, isLoading: detailsLoading } = useQuery({
    queryKey: ["factDetails", currentId],
    queryFn: ({ signal }) => getFactDetails(config, currentId!, signal),
    enabled: !!currentId,
  });
  detailsRef.current = factDetails;

  return {
    filteredFacts: ld.filtered,
    selectedIndex: ld.selectedIndex,
    factDetails,
    detailsLoading,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    detailSection: ld.detailSection as FactDetailSection,
    textExpanded: ld.textExpanded,
    textScrollOffset: ld.textScrollOffset,
    entitiesIndex: ld.sectionIndices[FACT_SECTIONS.ENTITIES],
    linkedIndex: ld.sectionIndices[FACT_SECTIONS.LINKED],
    editMode: ld.editMode,
    editText: ld.editText,
    cursorPos: ld.cursorPos,
    confirmDelete: ld.confirmDelete,
    sourceFilter,
    sortOrder: ld.sortOrder,
    availableSources,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
    setEditMode: ld.setEditMode,
    setEditText: ld.setEditText,
    setCursorPos: ld.setCursorPos,
    setConfirmDelete: ld.setConfirmDelete,
  };
}
