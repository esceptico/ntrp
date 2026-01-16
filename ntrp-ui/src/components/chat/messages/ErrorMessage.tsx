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
  const contentWidth = Math.max(0, terminalWidth - 6);

  return (
    <Box marginLeft={2} width={contentWidth} overflow="hidden">
      <Text color={colors.status.error}>✗ {truncateText(content, contentWidth)}</Text>
    </Box>
  );
});
