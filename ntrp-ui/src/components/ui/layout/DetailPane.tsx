import React from "react";
import { Box, Text } from "ink";
import { colors } from "../colors.js";

interface DetailPaneProps {
  lines: string[];
  scrollOffset: number;
  visibleLines: number;
  width: number;
  isFocused?: boolean;
  emptyMessage?: string;
}

export function DetailPane({
  lines,
  scrollOffset,
  visibleLines,
  width,
  isFocused = false,
  emptyMessage = "Nothing selected",
}: DetailPaneProps) {
  if (lines.length === 0) {
    return <Text color={colors.text.muted}>{emptyMessage}</Text>;
  }

  const maxScroll = Math.max(0, lines.length - visibleLines);
  const safeScroll = Math.min(scrollOffset, maxScroll);
  const visible = lines.slice(safeScroll, safeScroll + visibleLines);
  const textColor = isFocused ? colors.text.primary : colors.text.secondary;

  return (
    <Box flexDirection="column" width={width}>
      {visible.map((line, i) => (
        <Text key={i} color={textColor}>
          {line}
        </Text>
      ))}
      {maxScroll > 0 && (
        <Text color={colors.text.muted}>
          {safeScroll > 0 ? "▲ " : "  "}
          {safeScroll < maxScroll ? "▼" : ""}
        </Text>
      )}
    </Box>
  );
}
