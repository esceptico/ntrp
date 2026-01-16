import React from "react";
import { Box, Text } from "ink";
import { useDimensions } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface SplitViewProps {
  sidebarWidth: number;
  sidebar: React.ReactNode;
  main: React.ReactNode;
  divider?: boolean;
}

export function SplitView({ sidebarWidth, sidebar, main, divider = true }: SplitViewProps) {
  const { width: terminalWidth } = useDimensions();
  const dividerWidth = divider ? 1 : 0;
  const mainWidth = Math.max(0, terminalWidth - sidebarWidth - dividerWidth - 2);

  return (
    <Box flexDirection="row" width={terminalWidth}>
      <Box width={sidebarWidth} flexShrink={0} overflow="hidden">
        {sidebar}
      </Box>
      {divider && (
        <Box width={1} flexShrink={0}>
          <Text color={colors.divider}>│</Text>
        </Box>
      )}
      <Box width={mainWidth} flexGrow={1} overflow="hidden">
        {main}
      </Box>
    </Box>
  );
}
