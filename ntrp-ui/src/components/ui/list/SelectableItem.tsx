import React from "react";
import { Text } from "ink";
import { colors } from "../colors.js";

interface SelectableItemProps {
  selected: boolean;
  children: React.ReactNode;
}

export function SelectableItem({ selected, children }: SelectableItemProps) {
  return (
    <Text color={selected ? colors.selection.active : undefined} bold={selected}>
      {selected ? '> ' : '  '}{children}
    </Text>
  );
}
