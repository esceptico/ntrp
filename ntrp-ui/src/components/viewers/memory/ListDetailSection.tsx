import { type ReactNode } from "react";
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
  listWidth?: number;
  itemHeight?: number;
  onItemClick?: (index: number) => void;
  totalCount?: number;
}

const MIN_DETAIL_WIDTH = 24;

function splitDetailWidth(width: number, listWidth: number): number {
  return Math.max(0, width - listWidth - 1);
}

export function memoryDetailWidth(width: number, listWidth: number): number {
  const splitWidth = splitDetailWidth(width, listWidth);
  return splitWidth < MIN_DETAIL_WIDTH ? width : splitWidth;
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
  listWidth: providedListWidth,
  itemHeight = 1,
  onItemClick,
  totalCount,
}: ListDetailSectionProps<T>) {
  const listWidth = providedListWidth ?? Math.min(45, Math.max(30, Math.floor(width * 0.4)));
  const compact = splitDetailWidth(width, listWidth) < MIN_DETAIL_WIDTH;
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
        onItemClick={onItemClick ? (index) => onItemClick(index) : undefined}
      />
      {items.length > 0 && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.muted}>
              {selectedIndex + 1}/{items.length}
              {totalCount !== undefined && totalCount !== items.length ? ` of ${totalCount}` : ""}
            </span>
          </text>
        </box>
      )}
    </box>
  );

  const main = (
    <box flexDirection="column">
      {details}
    </box>
  );

  if (compact) {
    return (
      <box width={width} height={height} overflow="hidden">
        {focusPane === "details" ? main : sidebar}
      </box>
    );
  }

  return (
    <SplitView sidebarWidth={listWidth} sidebar={sidebar} main={main} width={width} height={height} />
  );
}
