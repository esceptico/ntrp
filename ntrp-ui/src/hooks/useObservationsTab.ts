import { useState, useEffect, useCallback, useMemo } from "react";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import {
  getObservationDetails,
  type Observation,
  type ObservationDetails,
} from "../api/client.js";
import { getTextMaxScroll } from "../components/ui/index.js";
import {
  OBS_SECTIONS,
  type ObsDetailSection,
  getObsSectionMaxIndex,
} from "../components/viewers/memory/ObservationDetailsView.js";

export interface ObservationsTabState {
  filteredObservations: Observation[];
  selectedIndex: number;
  obsDetails: ObservationDetails | null;
  detailsLoading: boolean;
  searchQuery: string;
  focusPane: "list" | "details";
  detailSection: ObsDetailSection;
  textExpanded: boolean;
  textScrollOffset: number;
  factsIndex: number;
  editMode: boolean;
  editText: string;
  confirmDelete: boolean;
  handleKeys: (key: Key) => void;
  setSearchQuery: (q: string) => void;
  setSelectedIndex: (i: number) => void;
  setFocusPane: (p: "list" | "details") => void;
  resetDetailState: () => void;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
}

export function useObservationsTab(
  config: Config,
  observations: Observation[],
  contentWidth: number
): ObservationsTabState {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [obsDetails, setObsDetails] = useState<ObservationDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [focusPane, setFocusPane] = useState<"list" | "details">("list");

  const [detailSection, setDetailSection] = useState<ObsDetailSection>(OBS_SECTIONS.TEXT);
  const [textExpanded, setTextExpanded] = useState(false);
  const [textScrollOffset, setTextScrollOffset] = useState(0);
  const [factsIndex, setFactsIndex] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const filteredObservations = useMemo(
    () =>
      searchQuery
        ? observations.filter((o) => o.summary.toLowerCase().includes(searchQuery.toLowerCase()))
        : observations,
    [observations, searchQuery]
  );

  const selectedObsId = filteredObservations[selectedIndex]?.id;

  const resetDetailState = useCallback(() => {
    setDetailSection(OBS_SECTIONS.TEXT);
    setTextExpanded(false);
    setTextScrollOffset(0);
    setFactsIndex(0);
    setEditMode(false);
    setEditText("");
    setConfirmDelete(false);
  }, []);

  useEffect(() => {
    if (!selectedObsId) {
      setObsDetails(null);
      return;
    }
    setDetailsLoading(true);
    resetDetailState();
    getObservationDetails(config, selectedObsId)
      .then(setObsDetails)
      .catch(() => setObsDetails(null))
      .finally(() => setDetailsLoading(false));
  }, [selectedObsId, config, resetDetailState]);

  const handleKeys = useCallback(
    (key: Key) => {
      if (key.name === "tab") {
        setFocusPane((p) => (p === "list" ? "details" : "list"));
        if (focusPane === "list") {
          resetDetailState();
        }
        return;
      }
      if (focusPane === "details") {
        if (key.name === "return" && detailSection === OBS_SECTIONS.TEXT) {
          setTextExpanded((e) => !e);
          setTextScrollOffset(0);
          return;
        }
        if (key.name === "up" || key.name === "k") {
          if (detailSection === OBS_SECTIONS.TEXT) {
            if (textExpanded && textScrollOffset > 0) {
              setTextScrollOffset((s) => s - 1);
            }
            return;
          }
          if (detailSection === OBS_SECTIONS.FACTS) {
            if (factsIndex > 0) {
              setFactsIndex((i) => i - 1);
            } else {
              setDetailSection(OBS_SECTIONS.TEXT);
            }
            return;
          }
        }
        if (key.name === "down" || key.name === "j") {
          if (detailSection === OBS_SECTIONS.TEXT) {
            if (textExpanded && obsDetails) {
              const listWidth = Math.min(45, Math.max(30, Math.floor(contentWidth * 0.4)));
              const detailWidth = Math.max(0, contentWidth - listWidth - 1) - 2;
              const maxScroll = getTextMaxScroll(obsDetails.observation.summary, detailWidth, 5);
              if (textScrollOffset < maxScroll) {
                setTextScrollOffset((s) => s + 1);
                return;
              }
            }
            setDetailSection(OBS_SECTIONS.FACTS);
            setFactsIndex(0);
            return;
          }
          if (detailSection === OBS_SECTIONS.FACTS) {
            const maxIndex = getObsSectionMaxIndex(obsDetails, OBS_SECTIONS.FACTS);
            if (factsIndex < maxIndex) {
              setFactsIndex((i) => i + 1);
            }
            return;
          }
        }
        return;
      }
      // List pane focused
      if (key.name === "backspace") {
        setSearchQuery((q) => q.slice(0, -1));
        setSelectedIndex(0);
        return;
      }
      if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(filteredObservations.length - 1, i + 1));
        return;
      }
      if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
        const char = key.name === "space" ? " " : key.sequence;
        setSearchQuery((q) => q + char);
        setSelectedIndex(0);
      }
    },
    [
      focusPane,
      detailSection,
      textExpanded,
      textScrollOffset,
      factsIndex,
      obsDetails,
      filteredObservations.length,
      contentWidth,
      resetDetailState,
    ]
  );

  return {
    filteredObservations,
    selectedIndex,
    obsDetails,
    detailsLoading,
    searchQuery,
    focusPane,
    detailSection,
    textExpanded,
    textScrollOffset,
    factsIndex,
    editMode,
    editText,
    confirmDelete,
    handleKeys,
    setSearchQuery,
    setSelectedIndex,
    setFocusPane,
    resetDetailState,
    setEditMode,
    setEditText,
    setConfirmDelete,
  };
}
