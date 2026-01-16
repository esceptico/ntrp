import React, { memo } from "react";
import { Box, Text } from "ink";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";

interface StatusMessageProps {
  content: string;
}

export const StatusMessage = memo(function StatusMessage({ content }: StatusMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <Box marginLeft={2} width={contentWidth} overflow="hidden">
      <Text color={colors.text.muted} italic>
        {truncateText(content, contentWidth)}
      </Text>
    </Box>
  );
});
