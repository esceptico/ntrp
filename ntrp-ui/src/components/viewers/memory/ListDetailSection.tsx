import React, { type ReactNode } from "react";
import {
  SplitView,
  BaseSelectionList,
  colors,
  type RenderItemContext,
} from "../../ui/index.js";

interface ListDetailSectionProps<T> {
  items: T[];
  selectedIndex: number;
  renderItem: (item: T, ctx: RenderItemContext) => ReactNode;
  getKey: (item: T) => string | number;
  emptyMessage: string;
  searchQuery: string;
  searchMode: boolean;
  height: number;
  width: number;
  details: ReactNode;
  focusPane?: "list" | "details";
  itemHeight?: number;
}

export function ListDetailSection<T>({
  items,
  selectedIndex,
  renderItem,
  getKey,
  emptyMessage,
  searchQuery,
  searchMode,
  height,
  width,
  details,
  focusPane = "list",
  itemHeight = 1,
}: ListDetailSectionProps<T>) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const availableLines = Math.max(1, height - 4);
  const visibleLines = Math.max(1, Math.floor(availableLines / itemHeight));

  let searchDisplay = " ";
  if (searchMode) {
    searchDisplay = `/${searchQuery}\u2588`;
  } else if (searchQuery) {
    searchDisplay = `/${searchQuery}`;
  }

  const sidebar = (
    <box flexDirection="column">
      <box marginBottom={1}>
        <text>
          <span fg={searchMode ? colors.text.primary : searchQuery ? colors.text.muted : colors.text.disabled}>
            {searchDisplay}
          </span>
        </text>
      </box>
      <BaseSelectionList
        items={items}
        selectedIndex={selectedIndex}
        renderItem={renderItem}
        visibleLines={visibleLines}
        getKey={getKey}
        emptyMessage={emptyMessage}
        showScrollArrows
        width={listWidth}
        indicator={"\u25B6"}
      />
      {items.length > 0 && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.muted}>
              {selectedIndex + 1}/{items.length}
            </span>
          </text>
        </box>
      )}
    </box>
  );

  return (
    <SplitView sidebarWidth={listWidth} sidebar={sidebar} main={details} width={width} height={height} />
  );
}
