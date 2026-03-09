import { useRef } from "react";
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
  setSelectedIndex: (i: number) => void;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setCursorPos: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
}

export function useObservationsTab(
  config: Config,
  observations: Observation[],
  contentWidth: number
): ObservationsTabState {
  const detailsRef = useRef<ObservationDetails | null>(null);

  const ld = useListDetail({
    items: observations,
    filterFn: filterObs,
    sectionCount: 2,
    getSectionMaxIndex: (section: number) => getObsSectionMaxIndex(detailsRef.current, section as ObsDetailSection),
    getScrollText: (): string | undefined => detailsRef.current?.observation.summary,
    contentWidth,
  });

  const currentId = ld.filtered[ld.selectedIndex]?.id;

  const { data: obsDetails = null, isLoading: detailsLoading } = useQuery({
    queryKey: ["obsDetails", currentId],
    queryFn: ({ signal }) => getObservationDetails(config, currentId!, signal),
    enabled: !!currentId,
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
