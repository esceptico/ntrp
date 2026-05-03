import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { MemoryAccessEvent } from "../api/client.js";
import type { Key } from "./useKeypress.js";
import { useListDetail, type ListKeyHelpers, type SortOrder } from "./useListDetail.js";

export type { SortOrder };

type AccessSourceFilter = "all" | "chat_prompt" | "operator_prompt" | "recall_tool";

const SOURCE_FILTERS: AccessSourceFilter[] = ["all", "chat_prompt", "operator_prompt", "recall_tool"];

const filterAccessEvent = (event: MemoryAccessEvent, q: string) => {
  const fields = [
    event.source,
    event.query ?? "",
    event.policy_version,
    event.retrieved_fact_ids.join(","),
    event.retrieved_observation_ids.join(","),
    event.injected_fact_ids.join(","),
    event.injected_observation_ids.join(","),
    event.bundled_fact_ids.join(","),
    JSON.stringify(event.details),
  ];
  return fields.some((field) => field.toLowerCase().includes(q));
};

export interface MemoryAccessTabState {
  filteredEvents: MemoryAccessEvent[];
  selectedIndex: number;
  selectedEvent: MemoryAccessEvent | null;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  sortOrder: SortOrder;
  textExpanded: boolean;
  textScrollOffset: number;
  sourceFilter: AccessSourceFilter;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: Dispatch<SetStateAction<number>>;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
}

export function useMemoryAccessTab(events: MemoryAccessEvent[], contentWidth: number): MemoryAccessTabState {
  const [sourceFilter, setSourceFilter] = useState<AccessSourceFilter>("all");

  const filteredByControls = useMemo(
    () => events.filter((event) => sourceFilter === "all" || event.source === sourceFilter),
    [events, sourceFilter],
  );

  const cycleSource = useCallback(() => {
    setSourceFilter((current) => SOURCE_FILTERS[(SOURCE_FILTERS.indexOf(current) + 1) % SOURCE_FILTERS.length]);
  }, []);

  const onListKey = useCallback((key: Key, { setSelectedIndex }: ListKeyHelpers) => {
    if (key.name !== "s") return false;
    cycleSource();
    setSelectedIndex(0);
    return true;
  }, [cycleSource]);

  const getSectionMaxIndex = useCallback(() => 0, []);
  const getScrollText = useCallback((): string | undefined => undefined, []);

  const ld = useListDetail({
    items: filteredByControls,
    filterFn: filterAccessEvent,
    sectionCount: 1,
    getSectionMaxIndex,
    getScrollText,
    contentWidth,
    hasEdit: false,
    onListKey,
  });

  return {
    filteredEvents: ld.filtered,
    selectedIndex: ld.selectedIndex,
    selectedEvent: ld.filtered[ld.selectedIndex] ?? null,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    sortOrder: ld.sortOrder,
    textExpanded: ld.textExpanded,
    textScrollOffset: ld.textScrollOffset,
    sourceFilter,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
  };
}
