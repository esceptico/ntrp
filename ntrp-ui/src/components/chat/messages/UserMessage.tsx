import React, { memo } from "react";
import { Box, Text } from "ink";
import { useDimensions } from "../../../contexts/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { truncateText } from "../../ui/index.js";

interface UserMessageProps {
  content: string;
}

export const UserMessage = memo(function UserMessage({ content }: UserMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const contentWidth = Math.max(0, terminalWidth - 4);
  const lines = content.split("\n");

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      {lines.map((line, i) => (
        <Text key={i}>
          <Text color={accentValue} bold>{i === 0 ? "> " : "  "}</Text>
          <Text>{truncateText(line, contentWidth)}</Text>
        </Text>
      ))}
    </Box>
  );
});
