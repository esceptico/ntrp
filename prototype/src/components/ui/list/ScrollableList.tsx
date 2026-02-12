import React, { useCallback } from "react";
import { BaseSelectionList, type RenderItemContext } from "./BaseSelectionList.js";

interface ScrollableListProps<T> {
  items: T[];
  selectedIndex: number;
  renderItem: (item: T, index: number, selected: boolean) => React.ReactNode;
  visibleLines?: number;
  emptyMessage?: string;
  showCount?: boolean;
  width?: number;
}

export function ScrollableList<T>({
  renderItem,
  ...props
}: ScrollableListProps<T>) {
  const wrappedRenderItem = useCallback(
    (item: T, ctx: RenderItemContext) => renderItem(item, ctx.index, ctx.isSelected),
    [renderItem]
  );

  return <BaseSelectionList {...props} renderItem={wrappedRenderItem} showIndicator={false} />;
}
