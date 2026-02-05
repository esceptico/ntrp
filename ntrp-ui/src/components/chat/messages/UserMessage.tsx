import React, { memo } from "react";
import { Box, Text } from "ink";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";

interface UserMessageProps {
  content: string;
}

export const UserMessage = memo(function UserMessage({ content }: UserMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);
  const lines = content.split("\n");

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      {lines.map((line, i) => (
        <Text key={i}>
          <Text color={colors.status.warning} bold>{i === 0 ? "> " : "  "}</Text>
          <Text>{truncateText(line, contentWidth)}</Text>
        </Text>
      ))}
    </Box>
  );
});
