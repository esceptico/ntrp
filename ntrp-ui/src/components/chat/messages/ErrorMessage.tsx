import React, { memo } from "react";
import { Box, Text } from "ink";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";

interface ErrorMessageProps {
  content: string;
}

export const ErrorMessage = memo(function ErrorMessage({ content }: ErrorMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <Box flexDirection="row" width={terminalWidth} overflow="hidden">
      <Box width={2} flexShrink={0}>
        <Text color={colors.status.error}>✗ </Text>
      </Box>
      <Box width={contentWidth} flexGrow={1} overflow="hidden">
        <Text color={colors.status.error}>{truncateText(content, contentWidth)}</Text>
      </Box>
    </Box>
  );
});
