import { useState, useEffect, useCallback, useMemo } from "react";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import {
  getDreamDetails,
  type Dream,
  type DreamDetails,
} from "../api/client.js";
import { getTextMaxScroll } from "../components/ui/index.js";
import {
  DREAM_SECTIONS,
  type DreamDetailSection,
  getDreamSectionMaxIndex,
} from "../components/viewers/memory/DreamDetailsView.js";

export type SortOrder = "recent" | "oldest";

interface DreamsTabState {
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
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [dreamDetails, setDreamDetails] = useState<DreamDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [focusPane, setFocusPane] = useState<"list" | "details">("list");
  const [sortOrder, setSortOrder] = useState<SortOrder>("recent");

  const [detailSection, setDetailSection] = useState<DreamDetailSection>(DREAM_SECTIONS.TEXT);
  const [textExpanded, setTextExpanded] = useState(false);
  const [textScrollOffset, setTextScrollOffset] = useState(0);
  const [factsIndex, setFactsIndex] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const filteredDreams = useMemo(() => {
    let result = dreams;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (d) =>
          d.insight.toLowerCase().includes(q) ||
          d.bridge.toLowerCase().includes(q)
      );
    }
    if (sortOrder === "oldest") {
      result = [...result].reverse();
    }
    return result;
  }, [dreams, searchQuery, sortOrder]);

  const selectedDreamId = filteredDreams[selectedIndex]?.id;

  const resetDetailState = useCallback(() => {
    setDetailSection(DREAM_SECTIONS.TEXT);
    setTextExpanded(false);
    setTextScrollOffset(0);
    setFactsIndex(0);
    setConfirmDelete(false);
  }, []);

  useEffect(() => {
    if (!selectedDreamId) {
      setDreamDetails(null);
      return;
    }
    setDetailsLoading(true);
    resetDetailState();
    getDreamDetails(config, selectedDreamId)
      .then(setDreamDetails)
      .catch(() => setDreamDetails(null))
      .finally(() => setDetailsLoading(false));
  }, [selectedDreamId, config, resetDetailState]);

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
        if (key.name === "return" && detailSection === DREAM_SECTIONS.TEXT) {
          setTextExpanded((e) => !e);
          setTextScrollOffset(0);
          return;
        }
        if (key.name === "up" || key.name === "k") {
          if (detailSection === DREAM_SECTIONS.TEXT) {
            if (textExpanded && textScrollOffset > 0) {
              setTextScrollOffset((s) => s - 1);
            }
            return;
          }
          if (detailSection === DREAM_SECTIONS.FACTS) {
            if (factsIndex > 0) {
              setFactsIndex((i) => i - 1);
            } else {
              setDetailSection(DREAM_SECTIONS.TEXT);
            }
            return;
          }
        }
        if (key.name === "down" || key.name === "j") {
          if (detailSection === DREAM_SECTIONS.TEXT) {
            if (textExpanded && dreamDetails) {
              const listWidth = Math.min(45, Math.max(30, Math.floor(contentWidth * 0.4)));
              const detailWidth = Math.max(0, contentWidth - listWidth - 1) - 2;
              const maxScroll = getTextMaxScroll(dreamDetails.dream.insight, detailWidth, 10);
              if (textScrollOffset < maxScroll) {
                setTextScrollOffset((s) => s + 1);
                return;
              }
            }
            setDetailSection(DREAM_SECTIONS.FACTS);
            setFactsIndex(0);
            return;
          }
          if (detailSection === DREAM_SECTIONS.FACTS) {
            const maxIndex = getDreamSectionMaxIndex(dreamDetails, DREAM_SECTIONS.FACTS);
            if (factsIndex < maxIndex) {
              setFactsIndex((i) => i + 1);
            }
            return;
          }
        }
        return;
      }
      // List pane focused — search mode
      if (searchMode) {
        if (key.name === "escape") {
          if (searchQuery) {
            setSearchQuery("");
            setSelectedIndex(0);
          } else {
            setSearchMode(false);
          }
          return;
        }
        if (key.name === "backspace") {
          setSearchQuery((q) => q.slice(0, -1));
          setSelectedIndex(0);
          return;
        }
        if (key.name === "return") {
          setSearchMode(false);
          return;
        }
        if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
          const char = key.name === "space" ? " " : key.sequence;
          setSearchQuery((q) => q + char);
          setSelectedIndex(0);
        }
        return;
      }
      // List pane focused — normal mode
      if (key.sequence === "/") {
        setSearchMode(true);
        return;
      }
      if (key.name === "o") {
        setSortOrder((current) => (current === "recent" ? "oldest" : "recent"));
        setSelectedIndex(0);
        return;
      }
      if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(filteredDreams.length - 1, i + 1));
        return;
      }
    },
    [
      focusPane,
      detailSection,
      textExpanded,
      textScrollOffset,
      factsIndex,
      dreamDetails,
      filteredDreams.length,
      contentWidth,
      resetDetailState,
      searchMode,
      searchQuery,
    ]
  );

  return {
    filteredDreams,
    selectedIndex,
    dreamDetails,
    detailsLoading,
    searchQuery,
    searchMode,
    focusPane,
    detailSection,
    textExpanded,
    textScrollOffset,
    factsIndex,
    confirmDelete,
    sortOrder,
    handleKeys,
    setSearchQuery,
    setSelectedIndex,
    setFocusPane,
    resetDetailState,
    setConfirmDelete,
  };
}
