import { useState, useEffect, useCallback, useRef, type Dispatch, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import {
  getFactDetails,
  type Fact,
  type FactAccessed,
  type FactDetails,
  type FactFilters,
  type FactKind,
  type FactMetadataSuggestion,
  type FactStatus,
  type SourceType,
} from "../api/client.js";
import { FACT_SECTIONS, type FactDetailSection, getFactSectionMaxIndex } from "../components/viewers/memory/FactDetailsView.js";
import { useListDetail, type SortOrder, type ListKeyHelpers } from "./useListDetail.js";

export type { SortOrder };

const filterFact = (f: Fact, q: string) => f.text.toLowerCase().includes(q);

const KIND_FILTERS: Array<FactKind | undefined> = [
  undefined,
  "note",
  "identity",
  "preference",
  "relationship",
  "decision",
  "project",
  "event",
  "artifact",
  "procedure",
  "constraint",
  "temporary",
];
const SOURCE_FILTERS: Array<SourceType | undefined> = [undefined, "chat", "explicit"];
const STATUS_FILTERS: FactStatus[] = ["active", "all", "archived", "superseded", "expired", "temporary", "pinned"];
const ACCESSED_FILTERS: Array<FactAccessed | undefined> = [undefined, "never", "used"];

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
  filters: FactFilters;
  factTotal: number;
  metadataSuggestion: FactMetadataSuggestion | null;
  suggestionLoading: boolean;
  suggestionError: string | null;
  sortOrder: SortOrder;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: Dispatch<SetStateAction<number>>;
  setSortOrder: Dispatch<SetStateAction<SortOrder>>;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setEditMode: Dispatch<SetStateAction<boolean>>;
  setEditText: Dispatch<SetStateAction<string>>;
  setCursorPos: Dispatch<SetStateAction<number>>;
  setConfirmDelete: Dispatch<SetStateAction<boolean>>;
  setMetadataSuggestion: Dispatch<SetStateAction<FactMetadataSuggestion | null>>;
  setSuggestionLoading: Dispatch<SetStateAction<boolean>>;
  setSuggestionError: Dispatch<SetStateAction<string | null>>;
}

export function useFactsTab(
  config: Config,
  facts: Fact[],
  contentWidth: number,
  filters: FactFilters,
  setFilters: Dispatch<SetStateAction<FactFilters>>,
  factTotal: number
): FactsTabState {
  const [metadataSuggestion, setMetadataSuggestion] = useState<FactMetadataSuggestion | null>(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const detailsRef = useRef<FactDetails | null>(null);

  const cycle = useCallback(<T,>(values: T[], current: T): T => {
    const idx = values.indexOf(current);
    return values[(idx + 1) % values.length];
  }, []);

  const onListKey = useCallback((key: Key, { setSelectedIndex }: ListKeyHelpers) => {
    if (key.name === "s") {
      setFilters((current) => ({ ...current, sourceType: cycle(SOURCE_FILTERS, current.sourceType) }));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "m") {
      setFilters((current) => ({ ...current, kind: cycle(KIND_FILTERS, current.kind) }));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "x") {
      setFilters((current) => ({ ...current, status: cycle(STATUS_FILTERS, current.status ?? "active") }));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "u") {
      setFilters((current) => ({ ...current, accessed: cycle(ACCESSED_FILTERS, current.accessed) }));
      setSelectedIndex(0);
      return true;
    }
    return false;
  }, [cycle, setFilters]);

  const getSectionMaxIndex = useCallback(
    (section: number) => getFactSectionMaxIndex(detailsRef.current, section as FactDetailSection),
    [],
  );
  const getScrollText = useCallback(
    (): string | undefined => detailsRef.current?.fact.text,
    [],
  );

  const ld = useListDetail({
    items: facts,
    filterFn: filterFact,
    sectionCount: 3,
    getSectionMaxIndex,
    getScrollText,
    contentWidth,
    onListKey,
  });

  const currentId = ld.filtered[ld.selectedIndex]?.id;

  useEffect(() => {
    setMetadataSuggestion(null);
    setSuggestionError(null);
    setSuggestionLoading(false);
  }, [currentId]);

  const { data: factDetails = null, isLoading: detailsLoading } = useQuery({
    queryKey: ["factDetails", currentId],
    queryFn: ({ signal }) => getFactDetails(config, currentId!, signal),
    enabled: !!currentId,
    staleTime: 60_000,
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
    filters,
    factTotal,
    metadataSuggestion,
    suggestionLoading,
    suggestionError,
    sortOrder: ld.sortOrder,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setSortOrder: ld.setSortOrder,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
    setEditMode: ld.setEditMode,
    setEditText: ld.setEditText,
    setCursorPos: ld.setCursorPos,
    setConfirmDelete: ld.setConfirmDelete,
    setMetadataSuggestion,
    setSuggestionLoading,
    setSuggestionError,
  };
}
