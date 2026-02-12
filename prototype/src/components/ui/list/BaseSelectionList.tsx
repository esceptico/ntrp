import React from "react";
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
  items: readonly T[];
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
    return <text><span fg={colors.text.muted}>{emptyMessage}</span></text>;
  }

  return (
    <box flexDirection="column" width={effectiveWidth} overflow="hidden">
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
          indicatorText = "\u25B2 ";
          indicatorColor = colors.list.scrollArrow;
        } else if (showScrollArrows && isLast && canScrollDown) {
          indicatorText = "\u25BC ";
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
          <box flexDirection="row" key={key}>
            {showIndicator && (
              <box width={2} flexShrink={0}>
                <text><span fg={indicatorColor}>{indicatorText}</span></text>
              </box>
            )}
            {showNumbers && (
              <text>
                <span fg={context.colors.indicator}>
                  {String(actualIndex + 1).padStart(numberWidth)}.{" "}
                </span>
              </text>
            )}
            {renderItem(item, context)}
          </box>
        );
      })}

      {showCount && items.length > 0 && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.muted}>
              {items.length <= visibleLines
                ? `${items.length} item${items.length !== 1 ? "s" : ""}`
                : `${scrollOffset + 1}-${Math.min(scrollOffset + visibleLines, items.length)} of ${items.length}`}
            </span>
          </text>
        </box>
      )}
    </box>
  );
}
