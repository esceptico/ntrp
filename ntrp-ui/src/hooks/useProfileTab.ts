import { useCallback, useRef, type Dispatch, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import {
  getProfileEntryDetails,
  type ProfileEntry,
  type ProfileEntryDetails,
} from "../api/client.js";
import {
  PROFILE_SECTIONS,
  type ProfileDetailSection,
  getProfileSectionMaxIndex,
} from "../components/viewers/memory/ProfileDetailsView.js";
import { useListDetail, type SortOrder } from "./useListDetail.js";

export type { SortOrder };

const filterProfileEntry = (entry: ProfileEntry, query: string) =>
  entry.summary.toLowerCase().includes(query) || entry.kind.includes(query);

export interface ProfileTabState {
  filteredEntries: ProfileEntry[];
  selectedIndex: number;
  entryDetails: ProfileEntryDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  detailSection: ProfileDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  observationsIndex: number;
  factsIndex: number;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  confirmDelete: boolean;
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
}

export function useProfileTab(
  config: Config,
  entries: ProfileEntry[],
  contentWidth: number,
): ProfileTabState {
  const detailsRef = useRef<ProfileEntryDetails | null>(null);

  const getSectionMaxIndex = useCallback(
    (section: number) => getProfileSectionMaxIndex(detailsRef.current, section as ProfileDetailSection),
    [],
  );

  const getScrollText = useCallback(
    (): string | undefined => detailsRef.current?.entry.summary,
    [],
  );

  const ld = useListDetail({
    items: entries,
    filterFn: filterProfileEntry,
    sectionCount: 3,
    getSectionMaxIndex,
    getScrollText,
    contentWidth,
  });

  const currentId = ld.filtered[ld.selectedIndex]?.id;
  const { data: entryDetails = null, isLoading: detailsLoading } = useQuery({
    queryKey: ["profileEntryDetails", currentId],
    queryFn: ({ signal }) => getProfileEntryDetails(config, currentId!, signal),
    enabled: !!currentId,
    staleTime: 60_000,
  });
  detailsRef.current = entryDetails;

  return {
    filteredEntries: ld.filtered,
    selectedIndex: ld.selectedIndex,
    entryDetails,
    detailsLoading,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    detailSection: ld.detailSection as ProfileDetailSection,
    textExpanded: ld.textExpanded,
    textScrollOffset: ld.textScrollOffset,
    observationsIndex: ld.sectionIndices[PROFILE_SECTIONS.OBSERVATIONS],
    factsIndex: ld.sectionIndices[PROFILE_SECTIONS.FACTS],
    editMode: ld.editMode,
    editText: ld.editText,
    cursorPos: ld.cursorPos,
    confirmDelete: ld.confirmDelete,
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
  };
}
