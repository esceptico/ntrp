import React from "react";
import { Box, Text } from "ink";
import { colors } from "./colors.js";

interface TabsProps<T extends string> {
  tabs: readonly T[];
  activeTab: T;
  onTabChange: (tab: T) => void;
  labels?: Record<T, string>;
}

export function Tabs<T extends string>({ tabs, activeTab, labels }: TabsProps<T>) {
  return (
    <Box marginBottom={1}>
      {tabs.map((tab, i) => {
        const isActive = tab === activeTab;
        const label = labels?.[tab] || tab.charAt(0).toUpperCase() + tab.slice(1);

        return (
          <Box key={tab} marginRight={1}>
            <Text
              color={isActive ? colors.tabs.active : colors.tabs.inactive}
              bold={isActive}
              inverse={isActive}
            >
              {" "}{label.toUpperCase()}{" "}
            </Text>
            {i < tabs.length - 1 && <Text color={colors.tabs.separator}>│</Text>}
          </Box>
        );
      })}
    </Box>
  );
}
