/**
 * Hook for managing keyboard navigation in selection lists.
 * Inspired by Gemini CLI's useSelectionList pattern.
 */

import { useState, useCallback, useEffect } from "react";
import { useKeypress, type Key } from "./useKeypress.js";

export interface UseSelectionListOptions<T> {
  items: T[];
  initialIndex?: number;
  onSelect?: (item: T, index: number) => void;
  onHighlight?: (item: T, index: number) => void;
  isActive?: boolean;
  loop?: boolean;
  pageSize?: number;
}

export interface UseSelectionListReturn {
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
  scrollOffset: number;
  visibleRange: { start: number; end: number };
  canScrollUp: boolean;
  canScrollDown: boolean;
}

export function useSelectionList<T>({
  items,
  initialIndex = 0,
  onSelect,
  onHighlight,
  isActive = true,
  loop = false,
  pageSize = 10,
}: UseSelectionListOptions<T>): UseSelectionListReturn {
  const [selectedIndex, setSelectedIndex] = useState(initialIndex);
  const [scrollOffset, setScrollOffset] = useState(0);

  // Clamp selection when items change
  useEffect(() => {
    if (items.length === 0) {
      setSelectedIndex(0);
      setScrollOffset(0);
    } else if (selectedIndex >= items.length) {
      setSelectedIndex(items.length - 1);
    }
  }, [items.length, selectedIndex]);

  // Update scroll offset to keep selection visible
  useEffect(() => {
    if (items.length <= pageSize) {
      setScrollOffset(0);
      return;
    }

    // Keep selection in view with padding
    const padding = Math.floor(pageSize / 3);
    
    if (selectedIndex < scrollOffset + padding) {
      setScrollOffset(Math.max(0, selectedIndex - padding));
    } else if (selectedIndex >= scrollOffset + pageSize - padding) {
      setScrollOffset(Math.min(
        items.length - pageSize,
        selectedIndex - pageSize + padding + 1
      ));
    }
  }, [selectedIndex, items.length, pageSize, scrollOffset]);

  // Notify on highlight change
  useEffect(() => {
    if (onHighlight && items[selectedIndex]) {
      onHighlight(items[selectedIndex], selectedIndex);
    }
  }, [selectedIndex, items, onHighlight]);

  const moveSelection = useCallback((delta: number) => {
    setSelectedIndex(current => {
      let next = current + delta;
      
      if (loop) {
        if (next < 0) next = items.length - 1;
        if (next >= items.length) next = 0;
      } else {
        next = Math.max(0, Math.min(items.length - 1, next));
      }
      
      return next;
    });
  }, [items.length, loop]);

  const handleKeypress = useCallback((key: Key) => {
    if (!isActive || items.length === 0) return;

    // Navigation
    if (key.name === "up" || key.name === "k") {
      moveSelection(-1);
      return;
    }
    if (key.name === "down" || key.name === "j") {
      moveSelection(1);
      return;
    }
    if (key.name === "home") {
      setSelectedIndex(0);
      return;
    }
    if (key.name === "end") {
      setSelectedIndex(items.length - 1);
      return;
    }

    // Selection
    if (key.name === "return" && onSelect) {
      onSelect(items[selectedIndex], selectedIndex);
      return;
    }

    // Number keys for quick selection (1-9)
    if (key.insertable && key.sequence && /^[1-9]$/.test(key.sequence)) {
      const num = parseInt(key.sequence, 10) - 1;
      const targetIndex = scrollOffset + num;
      if (targetIndex < items.length) {
        setSelectedIndex(targetIndex);
        if (onSelect) {
          onSelect(items[targetIndex], targetIndex);
        }
      }
    }
  }, [isActive, items, selectedIndex, moveSelection, pageSize, onSelect, scrollOffset]);

  useKeypress(handleKeypress, { isActive });

  const visibleEnd = Math.min(scrollOffset + pageSize, items.length);

  return {
    selectedIndex,
    setSelectedIndex,
    scrollOffset,
    visibleRange: { start: scrollOffset, end: visibleEnd },
    canScrollUp: scrollOffset > 0,
    canScrollDown: scrollOffset + pageSize < items.length,
  };
}
