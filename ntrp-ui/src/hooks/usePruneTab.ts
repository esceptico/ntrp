import { useCallback, type Dispatch, type SetStateAction } from "react";
import type { Key } from "./useKeypress.js";
import { useListDetail, type SortOrder } from "./useListDetail.js";
import type { MemoryPruneCandidate } from "../api/client.js";

export type { SortOrder };

const filterCandidate = (candidate: MemoryPruneCandidate, q: string) =>
  candidate.summary.toLowerCase().includes(q) ||
  candidate.reason.toLowerCase().includes(q) ||
  String(candidate.id).includes(q);

export interface PruneTabState {
  filteredCandidates: MemoryPruneCandidate[];
  selectedIndex: number;
  selectedCandidate: MemoryPruneCandidate | null;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  sortOrder: SortOrder;
  textExpanded: boolean;
  textScrollOffset: number;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: Dispatch<SetStateAction<number>>;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
}

export function usePruneTab(
  candidates: MemoryPruneCandidate[],
  contentWidth: number
): PruneTabState {
  const getSectionMaxIndex = useCallback(() => 0, []);
  const getScrollText = useCallback(
    (): string | undefined => undefined,
    [],
  );

  const ld = useListDetail({
    items: candidates,
    filterFn: filterCandidate,
    sectionCount: 1,
    getSectionMaxIndex,
    getScrollText,
    contentWidth,
    hasEdit: false,
  });

  return {
    filteredCandidates: ld.filtered,
    selectedIndex: ld.selectedIndex,
    selectedCandidate: ld.filtered[ld.selectedIndex] ?? null,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    sortOrder: ld.sortOrder,
    textExpanded: ld.textExpanded,
    textScrollOffset: ld.textScrollOffset,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
  };
}
