import { useState, useEffect, useCallback, useMemo } from "react";
import type { Key } from "./useKeypress.js";
import { getTextMaxScroll } from "../components/ui/index.js";

export type SortOrder = "recent" | "oldest";

export interface UseListDetailOptions<T> {
  items: T[];
  filterFn: (item: T, query: string) => boolean;
  sectionCount: number;
  getSectionMaxIndex: (section: number) => number;
  getScrollText: () => string | undefined;
  contentWidth: number;
  hasEdit?: boolean;
  onListKey?: (key: Key, helpers: ListKeyHelpers) => boolean;
}

export interface ListKeyHelpers {
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setSortOrder: React.Dispatch<React.SetStateAction<SortOrder>>;
}

export interface ListDetailState<T> {
  filtered: T[];
  selectedIndex: number;
  searchQuery: string;
  searchMode: boolean;
  focusPane: "list" | "details";
  sortOrder: SortOrder;
  detailSection: number;
  textExpanded: boolean;
  textScrollOffset: number;
  sectionIndices: number[];
  editMode: boolean;
  editText: string;
  cursorPos: number;
  confirmDelete: boolean;
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

export function useListDetail<T>({
  items,
  filterFn,
  sectionCount,
  getSectionMaxIndex,
  getScrollText,
  contentWidth,
  hasEdit = true,
  onListKey,
}: UseListDetailOptions<T>): ListDetailState<T> {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [focusPane, setFocusPane] = useState<"list" | "details">("list");
  const [sortOrder, setSortOrder] = useState<SortOrder>("recent");

  const [detailSection, setDetailSection] = useState(0);
  const [textExpanded, setTextExpanded] = useState(false);
  const [textScrollOffset, setTextScrollOffset] = useState(0);
  const [sectionIndices, setSectionIndices] = useState<number[]>(() => new Array(sectionCount).fill(0));
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [cursorPos, setCursorPos] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const filtered = useMemo(() => {
    let result = items;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter((item) => filterFn(item, q));
    }
    if (sortOrder === "oldest") {
      result = [...result].reverse();
    }
    return result;
  }, [items, searchQuery, sortOrder, filterFn]);

  const resetDetailState = useCallback(() => {
    setDetailSection(0);
    setTextExpanded(false);
    setTextScrollOffset(0);
    setSectionIndices(new Array(sectionCount).fill(0));
    if (hasEdit) {
      setEditMode(false);
      setEditText("");
      setCursorPos(0);
    }
    setConfirmDelete(false);
  }, [sectionCount, hasEdit]);

  const selectedId = (filtered[selectedIndex] as { id?: number })?.id;
  useEffect(() => { resetDetailState(); }, [selectedId, resetDetailState]);

  const handleKeys = useCallback(
    (key: Key) => {
      // Tab: switch focus pane
      if (key.name === "tab") {
        const nextPane = focusPane === "list" ? "details" : "list";
        setFocusPane(nextPane);
        if (nextPane === "details") resetDetailState();
        return;
      }

      // Detail pane navigation
      if (focusPane === "details") {
        const isText = detailSection === 0;

        // Return on text section → toggle expand
        if (key.name === "return" && isText) {
          setTextExpanded((e) => !e);
          setTextScrollOffset(0);
          return;
        }

        if (key.name === "up" || key.name === "k") {
          if (isText) {
            if (textExpanded && textScrollOffset > 0) {
              setTextScrollOffset((s) => s - 1);
            }
            return;
          }
          // List section: decrement or go to prev section
          const idx = sectionIndices[detailSection];
          if (idx > 0) {
            setSectionIndices((prev) => {
              const next = [...prev];
              next[detailSection] = idx - 1;
              return next;
            });
          } else {
            const prevSection = detailSection - 1;
            setDetailSection(prevSection);
            if (prevSection > 0) {
              const maxIdx = getSectionMaxIndex(prevSection);
              setSectionIndices((prev) => {
                const next = [...prev];
                next[prevSection] = maxIdx;
                return next;
              });
            }
          }
          return;
        }

        if (key.name === "down" || key.name === "j") {
          if (isText) {
            if (textExpanded) {
              const scrollText = getScrollText();
              if (scrollText) {
                const listWidth = Math.min(45, Math.max(30, Math.floor(contentWidth * 0.4)));
                const detailWidth = Math.max(0, contentWidth - listWidth - 1) - 2;
                const maxScroll = getTextMaxScroll(scrollText, detailWidth, 10);
                if (textScrollOffset < maxScroll) {
                  setTextScrollOffset((s) => s + 1);
                  return;
                }
              }
            }
            // Move to first list section
            if (sectionCount > 1) {
              setDetailSection(1);
              setSectionIndices((prev) => {
                const next = [...prev];
                next[1] = 0;
                return next;
              });
            }
            return;
          }
          // List section: increment or go to next section
          const idx = sectionIndices[detailSection];
          const maxIdx = getSectionMaxIndex(detailSection);
          if (idx < maxIdx) {
            setSectionIndices((prev) => {
              const next = [...prev];
              next[detailSection] = idx + 1;
              return next;
            });
          } else if (detailSection < sectionCount - 1) {
            const nextSection = detailSection + 1;
            setDetailSection(nextSection);
            setSectionIndices((prev) => {
              const next = [...prev];
              next[nextSection] = 0;
              return next;
            });
          }
          return;
        }
        return;
      }

      // List pane: search mode
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

      // List pane: normal mode — tab-specific keys first
      if (onListKey?.(key, { setSelectedIndex, setSortOrder })) return;

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
        setSelectedIndex((i) => Math.min(filtered.length - 1, i + 1));
        return;
      }
    },
    [
      focusPane,
      detailSection,
      textExpanded,
      textScrollOffset,
      sectionIndices,
      filtered.length,
      contentWidth,
      resetDetailState,
      searchMode,
      searchQuery,
      sectionCount,
      getSectionMaxIndex,
      getScrollText,
      onListKey,
    ]
  );

  return {
    filtered,
    selectedIndex,
    searchQuery,
    searchMode,
    focusPane,
    sortOrder,
    detailSection,
    textExpanded,
    textScrollOffset,
    sectionIndices,
    editMode,
    editText,
    cursorPos,
    confirmDelete,
    handleKeys,
    setSearchQuery,
    setSelectedIndex,
    setFocusPane,
    resetDetailState,
    setEditMode,
    setEditText,
    setCursorPos,
    setConfirmDelete,
  };
}
