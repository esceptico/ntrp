import React, { type ReactNode } from "react";
import { Box, Text } from "ink";
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
  visibleLines: number;
  width: number;
  details: ReactNode;
}

export function ListDetailSection<T>({
  items,
  selectedIndex,
  renderItem,
  getKey,
  emptyMessage,
  searchQuery,
  visibleLines,
  width,
  details,
}: ListDetailSectionProps<T>) {
  const listWidth = Math.min(45, Math.max(30, Math.floor(width * 0.4)));

  const sidebar = (
    <Box flexDirection="column">
      {searchQuery && (
        <Box marginBottom={1}>
          <Text color={colors.text.muted}>/{searchQuery}</Text>
        </Box>
      )}
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
        <Box marginTop={1}>
          <Text color={colors.text.muted}>
            {selectedIndex + 1}/{items.length}
          </Text>
        </Box>
      )}
    </Box>
  );

  return (
    <Box marginY={1} height={visibleLines + 3}>
      <SplitView sidebarWidth={listWidth} sidebar={sidebar} main={details} />
    </Box>
  );
}
