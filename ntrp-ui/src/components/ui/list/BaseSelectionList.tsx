import React from "react";
import { Box, Text } from "ink";
import { useScrollOffset } from "../../../hooks/useScrollOffset.js";
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
  showIndicator?: boolean;
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
  showIndicator = true,
  emptyMessage = "No items",
  getKey,
  width,
  indicator,
}: BaseSelectionListProps<T>) {
  const contentWidth = useContentWidth();
  const effectiveWidth = width ?? contentWidth;

  const { scrollOffset, canScrollUp, canScrollDown } = useScrollOffset(
    selectedIndex, items.length, visibleLines
  );

  const visibleItems = items.slice(scrollOffset, scrollOffset + visibleLines);
  const numberWidth = String(items.length).length;

  if (items.length === 0) {
    return <Text color={colors.text.muted}>{emptyMessage}</Text>;
  }

  return (
    <Box flexDirection="column" width={effectiveWidth} overflow="hidden">
      {visibleItems.map((item, i) => {
        const actualIndex = scrollOffset + i;
        const isSelected = actualIndex === selectedIndex;
        const key = getKey ? getKey(item, actualIndex) : actualIndex;
        const isFirst = i === 0;
        const isLast = i === visibleItems.length - 1;

        let indicatorText = "  ";
        let indicatorColor: string = colors.text.disabled;
        if (isSelected) {
          indicatorText = `${indicator ?? BULLET}`;
          indicatorColor = colors.selection.active;
        } else if (showScrollArrows && isFirst && canScrollUp) {
          indicatorText = "▲ ";
          indicatorColor = colors.list.scrollArrow;
        } else if (showScrollArrows && isLast && canScrollDown) {
          indicatorText = "▼ ";
          indicatorColor = colors.list.scrollArrow;
        }

        const context: RenderItemContext = {
          isSelected,
          index: actualIndex,
          colors: {
            text: isSelected ? colors.selection.active : colors.text.primary,
            indicator: indicatorColor,
          },
        };

        return (
          <Box key={key}>
            {showIndicator && <Text color={indicatorColor}>{indicatorText}</Text>}
            {showNumbers && (
              <Text color={context.colors.indicator}>
                {String(actualIndex + 1).padStart(numberWidth)}.{" "}
              </Text>
            )}
            {renderItem(item, context)}
          </Box>
        );
      })}

      {showCount && items.length > 0 && (
        <Box marginTop={1}>
          <Text color={colors.text.muted}>
            {items.length <= visibleLines
              ? `${items.length} item${items.length !== 1 ? "s" : ""}`
              : `${scrollOffset + 1}-${Math.min(scrollOffset + visibleLines, items.length)} of ${items.length}`}
          </Text>
        </Box>
      )}
    </Box>
  );
}
