import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { LearningCandidate, LearningEvent } from "../api/client.js";
import { learningLane, type LearningLaneFilter } from "../lib/memoryLearning.js";
import type { Key } from "./useKeypress.js";
import { useListDetail, type ListKeyHelpers, type SortOrder } from "./useListDetail.js";

export type { SortOrder };

type LearningStatusFilter = "all" | "proposed" | "approved" | "applied" | "rejected" | "reverted";
export type LearningStatusUpdate = "approved" | "applied" | "rejected" | "reverted";

const STATUS_FILTERS: LearningStatusFilter[] = ["all", "proposed", "approved", "applied", "rejected", "reverted"];
const LANE_FILTERS: LearningLaneFilter[] = ["all", "memory", "runtime", "skill", "automation"];

const filterCandidate = (candidate: LearningCandidate, q: string) => {
  const fields = [
    learningLane(candidate.change_type, candidate.target_key),
    candidate.status,
    candidate.change_type,
    candidate.target_key,
    candidate.proposal,
    candidate.rationale,
    candidate.expected_metric ?? "",
    candidate.policy_version,
    JSON.stringify(candidate.details),
  ];
  return fields.some((field) => field.toLowerCase().includes(q));
};

export interface LearningTabState {
  filteredCandidates: LearningCandidate[];
  selectedIndex: number;
  selectedCandidate: LearningCandidate | null;
  selectedEvents: LearningEvent[];
  confirmStatus: LearningStatusUpdate | null;
  confirmProposalScan: boolean;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  sortOrder: SortOrder;
  statusFilter: LearningStatusFilter;
  laneFilter: LearningLaneFilter;
  changeTypeFilter: string | undefined;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: Dispatch<SetStateAction<number>>;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setConfirmStatus: Dispatch<SetStateAction<LearningStatusUpdate | null>>;
  setConfirmProposalScan: Dispatch<SetStateAction<boolean>>;
}

export function useLearningTab(
  candidates: LearningCandidate[],
  events: LearningEvent[],
  contentWidth: number,
): LearningTabState {
  const [statusFilter, setStatusFilter] = useState<LearningStatusFilter>("all");
  const [laneFilter, setLaneFilter] = useState<LearningLaneFilter>("all");
  const [changeTypeFilter, setChangeTypeFilter] = useState<string | undefined>(undefined);
  const [confirmStatus, setConfirmStatus] = useState<LearningStatusUpdate | null>(null);
  const [confirmProposalScan, setConfirmProposalScan] = useState(false);

  const changeTypeFilters = useMemo(
    () => [undefined, ...Array.from(new Set(candidates.map((candidate) => candidate.change_type))).sort()],
    [candidates],
  );

  const filteredByControls = useMemo(
    () => candidates.filter((candidate) =>
      (statusFilter === "all" || candidate.status === statusFilter) &&
      (laneFilter === "all" || learningLane(candidate.change_type, candidate.target_key) === laneFilter) &&
      (changeTypeFilter === undefined || candidate.change_type === changeTypeFilter)
    ),
    [candidates, statusFilter, laneFilter, changeTypeFilter],
  );

  const cycle = useCallback(<T,>(values: T[], current: T): T => {
    const idx = values.indexOf(current);
    return values[(idx + 1) % values.length];
  }, []);

  const onListKey = useCallback((key: Key, { setSelectedIndex }: ListKeyHelpers) => {
    if (key.name === "s") {
      setStatusFilter((current) => cycle(STATUS_FILTERS, current));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "v") {
      setChangeTypeFilter((current) => cycle(changeTypeFilters, current));
      setSelectedIndex(0);
      return true;
    }
    if (key.name === "l") {
      setLaneFilter((current) => cycle(LANE_FILTERS, current));
      setSelectedIndex(0);
      return true;
    }
    return false;
  }, [changeTypeFilters, cycle]);

  const getSectionMaxIndex = useCallback(() => 0, []);
  const getScrollText = useCallback((): string | undefined => undefined, []);

  const ld = useListDetail({
    items: filteredByControls,
    filterFn: filterCandidate,
    sectionCount: 1,
    getSectionMaxIndex,
    getScrollText,
    contentWidth,
    hasEdit: false,
    onListKey,
  });

  const selectedCandidate = ld.filtered[ld.selectedIndex] ?? null;
  const selectedCandidateId = selectedCandidate?.id;
  useEffect(() => {
    setConfirmStatus(null);
    setConfirmProposalScan(false);
  }, [selectedCandidateId]);

  const eventById = new Map(events.map((event) => [event.id, event]));
  const selectedEvents = selectedCandidate
    ? selectedCandidate.evidence_event_ids
      .map((id) => eventById.get(id))
      .filter((event): event is LearningEvent => event !== undefined)
    : [];

  return {
    filteredCandidates: ld.filtered,
    selectedIndex: ld.selectedIndex,
    selectedCandidate,
    selectedEvents,
    confirmStatus,
    confirmProposalScan,
    searchQuery: ld.searchQuery,
    searchMode: ld.searchMode,
    focusPane: ld.focusPane,
    sortOrder: ld.sortOrder,
    statusFilter,
    laneFilter,
    changeTypeFilter,
    handleKeys: ld.handleKeys,
    setSearchQuery: ld.setSearchQuery,
    setSelectedIndex: ld.setSelectedIndex,
    setFocusPane: ld.setFocusPane,
    resetDetailState: ld.resetDetailState,
    setConfirmStatus,
    setConfirmProposalScan,
  };
}
