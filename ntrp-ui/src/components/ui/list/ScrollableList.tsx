import React, { useMemo } from "react";
import { Box, Text } from "ink";
import { computeScrollWindow } from "../../../lib/utils.js";
import { useContentWidth } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface ScrollableListProps<T> {
  items: T[];
  selectedIndex: number;
  renderItem: (item: T, index: number, selected: boolean) => React.ReactNode;
  visibleLines?: number;
  emptyMessage?: string;
  showScrollArrows?: boolean;
  showCount?: boolean;
  width?: number;
}

export function ScrollableList<T>({
  items,
  selectedIndex,
  renderItem,
  visibleLines = 10,
  emptyMessage = "No items",
  showScrollArrows = false,
  showCount = false,
  width,
}: ScrollableListProps<T>) {
  const contentWidth = useContentWidth();
  const effectiveWidth = width ?? contentWidth;

  // Reserve space for scroll arrows if needed
  const needsScroll = items.length > visibleLines;
  const actualVisibleLines = showScrollArrows && needsScroll
    ? Math.max(1, visibleLines - 2) // Reserve 2 lines for arrows
    : visibleLines;

  const { scrollOffset, canScrollUp, canScrollDown } = useMemo(
    () => computeScrollWindow(selectedIndex, items.length, actualVisibleLines),
    [items.length, selectedIndex, actualVisibleLines]
  );

  const visibleItems = items.slice(scrollOffset, scrollOffset + actualVisibleLines);

  const countDisplay = useMemo(() => {
    if (!showCount || items.length === 0) return null;
    const start = scrollOffset + 1;
    const end = Math.min(scrollOffset + visibleLines, items.length);
    if (items.length <= visibleLines) {
      return `${items.length} item${items.length !== 1 ? "s" : ""}`;
    }
    return `${start}-${end} of ${items.length}`;
  }, [showCount, items.length, scrollOffset, visibleLines]);

  if (items.length === 0) {
    return <Text color={colors.text.muted}>{emptyMessage}</Text>;
  }

  return (
    <Box flexDirection="column" width={effectiveWidth} overflow="hidden">
      {showScrollArrows && canScrollUp && (
        <Text color={colors.list.scrollArrow}>▲ more above</Text>
      )}

      {visibleItems.map((item, i) => {
        const actualIndex = scrollOffset + i;
        const isSelected = actualIndex === selectedIndex;
        return (
          <Box key={actualIndex}>
            {renderItem(item, actualIndex, isSelected)}
          </Box>
        );
      })}

      {showScrollArrows && canScrollDown && (
        <Text color={colors.list.scrollArrow}>▼ more below</Text>
      )}

      {countDisplay && (
        <Box marginTop={1}>
          <Text color={colors.text.muted}>{countDisplay}</Text>
        </Box>
      )}
    </Box>
  );
}
