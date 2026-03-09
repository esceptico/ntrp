import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import { getDreamDetails, type Dream, type DreamDetails } from "../api/client.js";
import { DREAM_SECTIONS, type DreamDetailSection, getDreamSectionMaxIndex } from "../components/viewers/memory/DreamDetailsView.js";
import { useListDetail, type SortOrder } from "./useListDetail.js";

export type { SortOrder };

const filterDream = (d: Dream, q: string) =>
  d.insight.toLowerCase().includes(q) || d.bridge.toLowerCase().includes(q);

export interface DreamsTabState {
  filteredDreams: Dream[];
  selectedIndex: number;
  dreamDetails: DreamDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  detailSection: DreamDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
  confirmDelete: boolean;
  sortOrder: SortOrder;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: (i: number) => void;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
}

export function useDreamsTab(
  config: Config,
  dreams: Dream[],
  contentWidth: number
): DreamsTabState {
  const detailsRef = useRef<DreamDetails | null>(null);

  const ld = useListDetail({
    items: dreams,
    filterFn: filterDream,
    sectionCount: 2,
    getSectionMaxIndex: (section: number) => getDreamSectionMaxIndex(detailsRef.current, section as DreamDetailSection),
    getScrollText: (): string | undefined => detailsRef.current?.dream.insight,
    contentWidth,
    hasEdit: false,
  });

  const currentId = ld.filtered[ld.selectedIndex]?.id;

  const { data: dreamDetails = null, isLoading: detailsLoading } = useQuery({
    queryKey: ["dreamDetails", currentId],
    queryFn: ({ signal }) => getDreamDetails(config, currentId!, signal),
    enabled: !!currentId,
  });
  detailsRef.current = dreamDetails;

  return {
    filteredDreams: ld.filtered,
    selectedIndex: ld.selectedIndex,
    dreamDetails,
    detailsLoading,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    detailSection: ld.detailSection as DreamDetailSection,
    textExpanded: ld.textExpanded,
    textScrollOffset: ld.textScrollOffset,
    factsIndex: ld.sectionIndices[DREAM_SECTIONS.FACTS],
    confirmDelete: ld.confirmDelete,
    sortOrder: ld.sortOrder,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
    setConfirmDelete: ld.setConfirmDelete,
  };
}
