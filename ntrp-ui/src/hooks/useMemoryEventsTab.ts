import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { MemoryEvent } from "../api/client.js";
import type { Key } from "./useKeypress.js";
import { useListDetail, type ListKeyHelpers, type SortOrder } from "./useListDetail.js";

export type { SortOrder };

type EventActorFilter = "all" | "user" | "backend" | "automation";
type EventTargetFilter = "all" | "fact" | "observation" | "dream" | "fact_batch" | "observation_batch";

const filterEvent = (event: MemoryEvent, q: string) => {
  const fields = [
    event.actor,
    event.action,
    event.target_type,
    event.target_id === null ? "" : String(event.target_id),
    event.source_type ?? "",
    event.source_ref ?? "",
    event.reason ?? "",
    event.policy_version,
    JSON.stringify(event.details),
  ];
  return fields.some((field) => field.toLowerCase().includes(q));
};

export interface MemoryEventsTabState {
  filteredEvents: MemoryEvent[];
  selectedIndex: number;
  selectedEvent: MemoryEvent | null;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  sortOrder: SortOrder;
  textExpanded: boolean;
  textScrollOffset: number;
  actorFilter: EventActorFilter;
  targetFilter: EventTargetFilter;
  actionFilter: string | undefined;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: Dispatch<SetStateAction<number>>;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
}

const ACTOR_FILTERS: EventActorFilter[] = ["all", "user", "backend", "automation"];
const TARGET_FILTERS: EventTargetFilter[] = ["all", "fact", "observation", "dream", "fact_batch", "observation_batch"];

export function useMemoryEventsTab(events: MemoryEvent[], contentWidth: number): MemoryEventsTabState {
  const [actorFilter, setActorFilter] = useState<EventActorFilter>("all");
  const [targetFilter, setTargetFilter] = useState<EventTargetFilter>("all");
  const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);

  const actionFilters = useMemo(
    () => [undefined, ...Array.from(new Set(events.map((event) => event.action))).sort()],
    [events],
  );

  const filteredByControls = useMemo(
    () => events.filter((event) =>
      (actorFilter === "all" || event.actor === actorFilter) &&
      (targetFilter === "all" || event.target_type === targetFilter) &&
      (actionFilter === undefined || event.action === actionFilter)
    ),
    [events, actorFilter, targetFilter, actionFilter],
  );

  const cycle = useCallback(<T,>(values: T[], current: T): T => {
    const idx = values.indexOf(current);
    return values[(idx + 1) % values.length];
  }, []);

  const onListKey = useCallback((key: Key, { setSelectedIndex }: ListKeyHelpers) => {
    if (key.name === "x") {
      setTargetFilter((current) => cycle(TARGET_FILTERS, current));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "u") {
      setActorFilter((current) => cycle(ACTOR_FILTERS, current));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "v") {
      setActionFilter((current) => cycle(actionFilters, current));
      setSelectedIndex(0);
      return true;
    }
    return false;
  }, [actionFilters, cycle]);

  const getSectionMaxIndex = useCallback(() => 0, []);
  const getScrollText = useCallback((): string | undefined => undefined, []);

  const ld = useListDetail({
    items: filteredByControls,
    filterFn: filterEvent,
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
    actorFilter,
    targetFilter,
    actionFilter,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
  };
}
