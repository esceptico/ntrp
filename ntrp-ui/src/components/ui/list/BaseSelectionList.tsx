import React, { useMemo } from "react";
import { Box, Text } from "ink";
import { computeScrollWindow } from "../../../lib/utils.js";
import { useContentWidth } from "../../../contexts/index.js";
import { colors } from "../colors.js";
import { BULLET } from "../../../lib/constants.js";

export interface RenderItemContext {
  isSelected: boolean;
  index: number;
  colors: {
    text: string;
    indicator: string;
  };
}

interface BaseSelectionListProps<T> {
  items: T[];
  selectedIndex: number;
  renderItem: (item: T, context: RenderItemContext) => React.ReactNode;
  visibleLines?: number;
  showNumbers?: boolean;
  showScrollArrows?: boolean;
  showCount?: boolean;
  emptyMessage?: string;
  getKey?: (item: T, index: number) => string | number;
  width?: number;
  indicator?: string;
}

export function BaseSelectionList<T>({
  items,
  selectedIndex,
  renderItem,
  visibleLines = 10,
  showNumbers = false,
  showScrollArrows = false,
  showCount = false,
  emptyMessage = "No items",
  getKey,
  width,
  indicator,
}: BaseSelectionListProps<T>) {
  const contentWidth = useContentWidth();
  const effectiveWidth = width ?? contentWidth;

  const { scrollOffset, canScrollUp, canScrollDown } = useMemo(
    () => computeScrollWindow(selectedIndex, items.length, visibleLines),
    [items.length, selectedIndex, visibleLines]
  );

  const visibleItems = items.slice(scrollOffset, scrollOffset + visibleLines);
  const numberWidth = String(items.length).length;

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
        <Text color={colors.list.scrollArrow}>▲</Text>
      )}

      {visibleItems.map((item, i) => {
        const actualIndex = scrollOffset + i;
        const isSelected = actualIndex === selectedIndex;
        const key = getKey ? getKey(item, actualIndex) : actualIndex;

        const context: RenderItemContext = {
          isSelected,
          index: actualIndex,
          colors: {
            text: isSelected ? colors.selection.active : colors.text.primary,
            indicator: isSelected ? colors.selection.active : colors.text.disabled,
          },
        };

        return (
          <Box key={key}>
            <Text color={context.colors.indicator}>
              {isSelected ? `${indicator ?? BULLET} ` : "  "}
            </Text>
            {showNumbers && (
              <Text color={context.colors.indicator}>
                {String(actualIndex + 1).padStart(numberWidth)}.{" "}
              </Text>
            )}
            {renderItem(item, context)}
          </Box>
        );
      })}

      {showScrollArrows && canScrollDown && (
        <Text color={colors.list.scrollArrow}>▼</Text>
      )}

      {countDisplay && (
        <Box marginTop={1}>
          <Text color={colors.text.muted}>{countDisplay}</Text>
        </Box>
      )}
    </Box>
  );
}
