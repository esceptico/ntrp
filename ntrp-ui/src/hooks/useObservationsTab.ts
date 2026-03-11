import { useRef, useCallback, type Dispatch, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import { getObservationDetails, type Observation, type ObservationDetails } from "../api/client.js";
import { OBS_SECTIONS, type ObsDetailSection, getObsSectionMaxIndex } from "../components/viewers/memory/ObservationDetailsView.js";
import { useListDetail, type SortOrder } from "./useListDetail.js";

export type { SortOrder };

const filterObs = (o: Observation, q: string) => o.summary.toLowerCase().includes(q);

export interface ObservationsTabState {
  filteredObservations: Observation[];
  selectedIndex: number;
  obsDetails: ObservationDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  detailSection: ObsDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  confirmDelete: boolean;
  sortOrder: SortOrder;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: Dispatch<SetStateAction<number>>;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setEditMode: Dispatch<SetStateAction<boolean>>;
  setEditText: Dispatch<SetStateAction<string>>;
  setCursorPos: Dispatch<SetStateAction<number>>;
  setConfirmDelete: Dispatch<SetStateAction<boolean>>;
}

export function useObservationsTab(
  config: Config,
  observations: Observation[],
  contentWidth: number
): ObservationsTabState {
  const detailsRef = useRef<ObservationDetails | null>(null);

  const getSectionMaxIndex = useCallback(
    (section: number) => getObsSectionMaxIndex(detailsRef.current, section as ObsDetailSection),
    [],
  );
  const getScrollText = useCallback(
    (): string | undefined => detailsRef.current?.observation.summary,
    [],
  );

  const ld = useListDetail({
    items: observations,
    filterFn: filterObs,
    sectionCount: 2,
    getSectionMaxIndex,
    getScrollText,
    contentWidth,
  });

  const currentId = ld.filtered[ld.selectedIndex]?.id;

  const { data: obsDetails = null, isLoading: detailsLoading } = useQuery({
    queryKey: ["obsDetails", currentId],
    queryFn: ({ signal }) => getObservationDetails(config, currentId!, signal),
    enabled: !!currentId,
    staleTime: 60_000,
  });
  detailsRef.current = obsDetails;

  return {
    filteredObservations: ld.filtered,
    selectedIndex: ld.selectedIndex,
    obsDetails,
    detailsLoading,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    detailSection: ld.detailSection as ObsDetailSection,
    textExpanded: ld.textExpanded,
    textScrollOffset: ld.textScrollOffset,
    factsIndex: ld.sectionIndices[OBS_SECTIONS.FACTS],
    editMode: ld.editMode,
    editText: ld.editText,
    cursorPos: ld.cursorPos,
    confirmDelete: ld.confirmDelete,
    sortOrder: ld.sortOrder,
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
