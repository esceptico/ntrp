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
  height: number;
  width: number;
  details: ReactNode;
  focusPane?: "list" | "details";
}

export function ListDetailSection<T>({
  items,
  selectedIndex,
  renderItem,
  getKey,
  emptyMessage,
  searchQuery,
  height,
  width,
  details,
  focusPane = "list",
}: ListDetailSectionProps<T>) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const visibleLines = Math.max(1, height - 4);

  const sidebar = (
    <box flexDirection="column">
      <box marginBottom={1}>
        <text>
          <span fg={searchQuery ? colors.text.muted : colors.text.disabled}>
            {searchQuery ? `/${searchQuery}` : focusPane === "list" ? "type to search" : " "}
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
