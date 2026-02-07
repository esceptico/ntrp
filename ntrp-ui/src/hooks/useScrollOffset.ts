import { useRef } from "react";
import type { ScrollWindow } from "../lib/utils.js";

export function useScrollOffset(
  selectedIndex: number,
  totalItems: number,
  visibleLines: number
): ScrollWindow {
  const offsetRef = useRef(0);

  if (totalItems <= visibleLines) {
    offsetRef.current = 0;
    return { scrollOffset: 0, canScrollUp: false, canScrollDown: false };
  }

  let offset = offsetRef.current;

  // Only scroll when selection goes beyond the visible window
  if (selectedIndex < offset) {
    offset = selectedIndex;
  } else if (selectedIndex >= offset + visibleLines) {
    offset = selectedIndex - visibleLines + 1;
  }

  // Clamp to valid range
  offset = Math.max(0, Math.min(totalItems - visibleLines, offset));
  offsetRef.current = offset;

  return {
    scrollOffset: offset,
    canScrollUp: offset > 0,
    canScrollDown: offset + visibleLines < totalItems,
  };
}
