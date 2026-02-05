import React from "react";
import { Text } from "ink";
import { colors } from "../colors.js";
import { SelectionIndicator } from "../SelectionIndicator.js";

interface MenuItemProps {
  selected: boolean;
  accent?: string;
  children: React.ReactNode;
}

export function MenuItem({ selected, accent, children }: MenuItemProps) {
  return (
    <Text>
      <SelectionIndicator selected={selected} accent={accent} />
      <Text color={selected ? colors.text.primary : colors.text.secondary}>
        {children}
      </Text>
    </Text>
  );
}
