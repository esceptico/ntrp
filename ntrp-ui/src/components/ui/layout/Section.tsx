import React from "react";
import { Box, Text } from "ink";
import { colors } from "../colors.js";

interface SectionProps {
  title: string;
  count?: { current: number; total: number };
  children: React.ReactNode;
}

export function Section({ title, count, children }: SectionProps) {
  const countText = count ? ` [${count.current}/${count.total}]` : '';

  return (
    <Box flexDirection="column" marginY={1}>
      <Text color={colors.panel.title} bold>
        {title}{countText}
      </Text>
      {children}
    </Box>
  );
}
